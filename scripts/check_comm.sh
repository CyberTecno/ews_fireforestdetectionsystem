#!/bin/bash
# =============================================================================
# EWS Communication Check (check_comm.sh)
# =============================================================================
# Tujuan: verifikasi end-to-end jalur komunikasi EFWS — bukan sekadar cek
# apakah ews_network_setup.sh sukses, tapi:
#
#   1. ModemManager: modem SIM7600 terdeteksi, state & primary port
#   2. nmcli: profil EWS-4G aktif dan interface wwan0 punya IP
#   3. Default route: traffic ke internet keluar via interface GSM
#   4. Tailscale: tidak menggeser default route atau meng-hijack DNS
#   5. Reachability nyata ke EFWS_API_URL (DNS resolve + HTTP)
#
# Tidak lagi memanggil sim_detector.py atau kode Python apapun.
# Bisa dijalankan kapan saja tanpa harus stop efws.service.
#
# Usage:
#   sudo /home/uwfadmin/ews/scripts/check_comm.sh
# =============================================================================

set -u

PROJECT_DIR="/home/uwfadmin/ews"
CONNECTION_NAME="EWS-4G"

pass=0; warn=0; fail=0

log()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m[OK]\033[0m   %s\n' "$*";   pass=$((pass+1)); }
w()    { printf '  \033[1;33m[WARN]\033[0m %s\n' "$*";   warn=$((warn+1)); }
f()    { printf '  \033[1;31m[FAIL]\033[0m %s\n' "$*";   fail=$((fail+1)); }
info() { printf '  %s\n' "$*"; }

# =============================================================================
# 1. ModemManager: modem SIM7600 terdeteksi?
# =============================================================================
log "1. ModemManager & SIM7600"

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
if [ -z "$MODEM_ID" ]; then
    f "mmcli tidak menemukan modem sama sekali. Cek 'lsusb' dan 'ls /dev/ttyUSB*'."
else
    ok "Modem terdeteksi ModemManager, ID=$MODEM_ID"
    MM_INFO=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null)

    MODEL=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.model\s*:\s*\K.*' || true)
    STATE=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.state\s*:\s*\K.*' | tr -d '[:space:]' || true)
    PRIMARY_PORT=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.primary-port\s*:\s*\K.*' | tr -d '[:space:]' || true)
    SIM_STATUS=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.sim-status\s*:\s*\K.*' | tr -d '[:space:]' || true)

    info "Model         : ${MODEL:-unknown}"
    info "State         : ${STATE:-unknown}"
    info "Primary port  : ${PRIMARY_PORT:-unknown}"
    info "SIM status    : ${SIM_STATUS:-unknown}"

    case "$STATE" in
        connected)   ok "Modem sudah dalam state 'connected'." ;;
        registered)  ok "Modem sudah registrasi ke jaringan (belum connected — mungkin bearernya belum aktif)." ;;
        searching)   w  "Modem sedang mencari jaringan. Tunggu beberapa saat." ;;
        locked)      f  "Modem berstatus 'locked' — SIM butuh PIN. Nonaktifkan PIN SIM." ;;
        disabled)    w  "Modem berstatus 'disabled'." ;;
        *)           info "State modem: ${STATE:-tidak diketahui}" ;;
    esac

    # Signal quality
    SIG=$(mmcli -m "$MODEM_ID" --signal-get 2>/dev/null \
        | grep -oP 'rssi\s*:\s*\K[0-9.-]+' | head -n1 || true)
    if [ -n "$SIG" ]; then
        info "Signal RSSI   : ${SIG} dBm"
    else
        # Fallback ke CSQ via AT command jika signal-get kosong
        CSQ_LINE=$(mmcli -m "$MODEM_ID" 2>/dev/null \
            | grep -i "signal" | head -n1 || true)
        [ -n "$CSQ_LINE" ] && info "Signal info   : $CSQ_LINE"
    fi

    # cek apakah /dev/ttyUSB2 ada (AT command port SIM7600)
    if [ -e "/dev/ttyUSB2" ]; then
        ok "Port AT /dev/ttyUSB2 tersedia."
    else
        w "/dev/ttyUSB2 tidak ditemukan — pastikan SIM7600 sudah terpasang dan driver QMI/CDC loaded."
        info "Cek: ls /dev/ttyUSB* && lsusb"
    fi
fi

# =============================================================================
# 2. nmcli: profil EWS-4G & interface GSM
# =============================================================================
log "2. nmcli — Profil $CONNECTION_NAME & Interface GSM"

if ! nmcli connection show "$CONNECTION_NAME" &>/dev/null; then
    f "Profil nmcli '$CONNECTION_NAME' tidak ditemukan. Jalankan 'sudo systemctl start gsm-connect' atau buat manual."
else
    ok "Profil nmcli '$CONNECTION_NAME' ada."

    CONN_STATE=$(nmcli -t -f GENERAL.STATE connection show --active "$CONNECTION_NAME" 2>/dev/null \
        | cut -d: -f2 || true)
    CONN_APN=$(nmcli -t -g gsm.apn connection show "$CONNECTION_NAME" 2>/dev/null || true)

    info "APN profil    : ${CONN_APN:-tidak diketahui}"
    info "State aktif   : ${CONN_STATE:-tidak aktif}"

    if nmcli connection show --active "$CONNECTION_NAME" &>/dev/null; then
        ok "Profil '$CONNECTION_NAME' sedang AKTIF."
    else
        f "Profil '$CONNECTION_NAME' ADA tapi tidak AKTIF. Coba: sudo nmcli connection up $CONNECTION_NAME"
    fi
fi

# Cek IP di interface GSM (wwan0, cdc-wdm0, usb0)
GSM_IFACE=""
for iface in wwan0 cdc-wdm0 usb0; do
    if ip addr show "$iface" 2>/dev/null | grep -q "inet "; then
        GSM_IFACE="$iface"
        break
    fi
done

if [ -n "$GSM_IFACE" ]; then
    GSM_IP=$(ip addr show "$GSM_IFACE" | grep "inet " | awk '{print $2}' | head -n1)
    ok "Interface GSM $GSM_IFACE mendapat IP: $GSM_IP"
else
    w "Tidak ada IP di wwan0/cdc-wdm0/usb0. Cek: 'ip addr show wwan0' dan 'journalctl -u ews-gsm -n 30'."
fi

# =============================================================================
# 3. Default route — keluar via interface GSM?
# =============================================================================
log "3. Default Route & Internet Path"

ROUTE_INFO=$(ip route get 8.8.8.8 2>&1 || true)
info "$ROUTE_INFO"
ACTIVE_IFACE=$(echo "$ROUTE_INFO" | grep -oP 'dev \K[^ ]+' | head -n1 || true)
info "Interface aktif untuk internet saat ini: ${ACTIVE_IFACE:-tidak diketahui}"

if echo "$ACTIVE_IFACE" | grep -qE "wwan|cdc-wdm|usb"; then
    ok "Default route keluar via interface GSM ($ACTIVE_IFACE) — sesuai yang diinginkan."
elif [ -n "$ACTIVE_IFACE" ]; then
    w "Default route via '$ACTIVE_IFACE' (bukan GSM). Kalau GSM juga tersambung, cek ulang route metric-nya."
    info "Cek: 'ip route show' dan 'nmcli connection show $CONNECTION_NAME | grep metric'"
else
    f "Tidak ada default route. Koneksi internet belum tersedia."
fi

# =============================================================================
# 4. Tailscale — pastikan tidak menggeser default route atau DNS
# =============================================================================
log "4. Tailscale"

if ! command -v tailscale > /dev/null 2>&1; then
    info "Tailscale tidak terinstall di sistem ini — dilewati."
else
    if ! systemctl is-active --quiet tailscaled; then
        w "tailscaled terinstall tapi tidak aktif."
    else
        ok "tailscaled aktif."

        TS_PREFS=$(tailscale debug prefs 2>/dev/null || true)

        if echo "$TS_PREFS" | grep -qi '"RouteAll": *true\|"AcceptRoutes": *true'; then
            w "Tailscale AcceptRoutes aktif — bisa menggeser default route jika ada exit node di tailnet."
        else
            ok "AcceptRoutes tidak aktif — default route GSM tidak terganggu Tailscale."
        fi

        if echo "$TS_PREFS" | grep -qi '"ExitNodeID": *""' || \
           ! echo "$TS_PREFS" | grep -qi '"ExitNodeID"'; then
            ok "Tidak sedang memakai Tailscale exit node."
        else
            w "Sedang memakai Tailscale exit node — SEMUA traffic keluar via tailnet, bukan GSM langsung."
        fi

        if command -v resolvectl > /dev/null 2>&1; then
            RESOLV_INFO=$(resolvectl status 2>/dev/null || true)
            if echo "$RESOLV_INFO" | grep -q "100.100.100.100"; then
                w "Tailscale MagicDNS aktif sebagai DNS server. Kalau DNS lambat/gagal, coba: sudo tailscale set --accept-dns=false"
            else
                ok "Tailscale tidak mengambil alih DNS resolver global."
            fi
        fi
    fi
fi

# =============================================================================
# 5. DNS resolve + reachability nyata ke EFWS_API_URL
# =============================================================================
log "5. DNS & Reachability ke EFWS_API_URL"

# Ambil EFWS_API_URL dari .env project
API_URL=$(grep -m1 '^EFWS_API_URL=' "$PROJECT_DIR/.env" 2>/dev/null \
    | cut -d= -f2- \
    | sed -e 's/\r$//' -e "s/^['\"]//;s/['\"]$//" \
    || true)

if [ -z "$API_URL" ]; then
    w "Tidak menemukan EFWS_API_URL di $PROJECT_DIR/.env — lewati tes reachability."
else
    API_HOST=$(echo "$API_URL" | sed -E 's#^[a-zA-Z]+://##; s#[/:].*$##')
    info "Endpoint dari .env : $API_URL"
    info "Host               : $API_HOST"

    if command -v getent > /dev/null 2>&1; then
        DNS_RESULT=$(getent hosts "$API_HOST" 2>&1 || true)
        if [ -n "$DNS_RESULT" ] && ! echo "$DNS_RESULT" | grep -qi "failed\|not found\|error"; then
            ok "DNS resolve sukses: $DNS_RESULT"
        else
            f "DNS resolve GAGAL untuk '$API_HOST'. Cek 'resolvectl status' atau APN operator."
        fi
    fi

    if command -v curl > /dev/null 2>&1; then
        HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_URL" 2>&1 || true)
        if [ -n "$HTTP_CODE" ] && [ "$HTTP_CODE" != "000" ]; then
            ok "Endpoint dapat dihubungi (HTTP $HTTP_CODE) via interface $ACTIVE_IFACE."
        else
            f "Gagal reach $API_URL (curl/HTTP: $HTTP_CODE). Cek koneksi & firewall APN."
        fi
    fi
fi

# =============================================================================
# Ringkasan
# =============================================================================
log "Ringkasan"
info "OK=$pass  WARN=$warn  FAIL=$fail"
if [ "$fail" -gt 0 ]; then
    info "Ada kegagalan yang perlu ditindaklanjuti."
    info "Mulai dari: journalctl -u ews-gsm -n 50"
elif [ "$warn" -gt 0 ]; then
    info "Tidak ada kegagalan fatal, ada beberapa hal untuk diperiksa manual."
else
    info "Semua pengecekan lolos — jalur komunikasi sehat."
fi
