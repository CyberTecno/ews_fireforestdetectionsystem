#!/bin/bash
# =============================================================================
# EWS Communication Check (check_comm.sh)
# =============================================================================
# Tujuan: verifikasi end-to-end jalur komunikasi EFWS -- BUKAN cuma cek
# apakah nmcli/gsm-connect sukses, tapi:
#
#   1. Jalankan detect_sim() ASLI dari komunikasi/sim_detector.py (kode
#      produksi Anda sendiri) untuk memastikan modul A7670E atau SIM7600
#      benar-benar terbaca, sinyalnya berapa, dan sudah registrasi ke
#      jaringan atau belum.
#   2. Cek apakah ModemManager & profil GSM sudah pakai interface yang
#      benar (cdc-wdm, bukan port serial yang dipakai app).
#   3. Cek status Tailscale -- apakah accept-routes/exit-node aktif
#      (yang bisa geser default route) dan apakah DNS di-takeover.
#   4. Tes resolusi DNS + reachability nyata ke EFWS_API_URL, sekaligus
#      tunjukkan lewat interface mana traffic itu benar-benar keluar.
#
# PENTING: Jalankan skrip ini SAAT efws.service SEDANG BERHENTI.
# Kenapa: sim_detector.py membuka /dev/ttyUSB* secara eksklusif via
# pyserial. Kalau efws.service masih jalan dan sudah pegang port itu,
# skrip ini akan gagal buka port yang sama (port busy) -- itu BUKAN
# berarti modemnya rusak, cuma karena dua proses rebutan port yang sama.
#
# Usage:
#   sudo systemctl stop efws
#   /home/uwfadmin/ews/scripts/check_comm.sh
#   sudo systemctl start efws
# =============================================================================

set -u

PROJECT_DIR="/home/uwfadmin/ews"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
CONNECTION_NAME="EWS-4G"

pass=0; warn=0; fail=0

log()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m[OK]\033[0m   %s\n' "$*";   pass=$((pass+1)); }
w()    { printf '  \033[1;33m[WARN]\033[0m %s\n' "$*";   warn=$((warn+1)); }
f()    { printf '  \033[1;31m[FAIL]\033[0m %s\n' "$*";   fail=$((fail+1)); }
info() { printf '  %s\n' "$*"; }

# =============================================================================
# 0. Guard: pastikan efws.service tidak sedang pegang port serial
# =============================================================================
log "0. Cek status efws.service"
if systemctl is-active --quiet efws; then
    w "efws.service SEDANG JALAN. Ini bisa bikin sim_detector.py di bawah gagal buka port (busy)."
    info "Disarankan: sudo systemctl stop efws   (lalu start lagi setelah selesai diagnostik)"
else
    ok "efws.service tidak sedang berjalan -- aman untuk tes port serial."
fi

# =============================================================================
# 1. ModemManager: modem terdeteksi? primary port apa?
# =============================================================================
log "1. ModemManager & primary port modem"

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
if [ -z "$MODEM_ID" ]; then
    f "mmcli tidak menemukan modem sama sekali. Cek 'lsusb' dan 'ls /dev/ttyUSB*'."
else
    ok "Modem terdeteksi ModemManager, ID=$MODEM_ID"
    MM_INFO=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null)

    PRIMARY_PORT=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.primary-port\s*:\s*\K.*' | tr -d '[:space:]' || true)
    MODEL=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.model\s*:\s*\K.*' || true)
    STATE=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.state\s*:\s*\K.*' | tr -d '[:space:]' || true)

    info "Model         : ${MODEL:-unknown}"
    info "Primary port  : ${PRIMARY_PORT:-unknown}"
    info "Modem state   : ${STATE:-unknown}"

    case "$PRIMARY_PORT" in
        cdc-wdm*) ok "Primary port pakai cdc-wdm (QMI) -- terpisah dari port serial AT, aman dari bentrok dengan app." ;;
        "")       w "Tidak bisa baca primary-port dari mmcli." ;;
        *)        f "Primary port ($PRIMARY_PORT) BUKAN cdc-wdm. Kemungkinan modem mode PPP/AT -- risiko rebutan port dengan sim_detector.py TINGGI." ;;
    esac

    if [ "$STATE" = "locked" ]; then
        f "Modem berstatus 'locked' -- SIM kemungkinan butuh PIN."
    fi

    # Profil koneksi GSM: cek ifname yang sebenarnya dipakai
    CONN_IFACE=$(nmcli -g connection.interface-name connection show "$CONNECTION_NAME" 2>/dev/null || true)
    if [ -n "$CONN_IFACE" ]; then
        info "Profil '$CONNECTION_NAME' pakai interface-name: ${CONN_IFACE:-<auto/any>}"
        if [ -n "$PRIMARY_PORT" ] && [ "$CONN_IFACE" != "$PRIMARY_PORT" ] && [ "$CONN_IFACE" != "*" ] && [ -n "$CONN_IFACE" ]; then
            w "Interface profil ($CONN_IFACE) beda dengan primary-port modem ($PRIMARY_PORT) -- cek konfigurasi gsm_connect.sh."
        fi
    fi
fi

# =============================================================================
# 2. Jalankan detect_sim() ASLI dari kode aplikasi -- ini benar-benar
#    menjalankan "bagian communication"-nya, bukan simulasi.
# =============================================================================
log "2. Jalankan communication/sim_detector.py (detect_sim, force_scan)"

if [ ! -x "$VENV_PYTHON" ]; then
    f "Tidak menemukan venv python di $VENV_PYTHON -- sesuaikan PROJECT_DIR di atas skrip ini."
else
    cd "$PROJECT_DIR" || exit 1
    DETECT_OUTPUT=$("$VENV_PYTHON" - <<'PYEOF' 2>&1
import sys, json
sys.path.insert(0, ".")
try:
    from communication.sim_detector import detect_sim
    from config import settings
    if settings.RUN_MODE == "mock":
        print("RESULT::MOCK_MODE")
        sys.exit(0)
    sim = detect_sim(force_scan=True)
    reg = sim.network_registration()
    csq = sim.signal_quality()
    print(f"RESULT::OK::module={sim.module}::port={sim.port}")
    print(f"REGISTRATION::{reg.strip()}")
    print(f"SIGNAL::{csq.strip()}")
    sim.close()
except Exception as e:
    print(f"RESULT::ERROR::{type(e).__name__}: {e}")
    sys.exit(1)
PYEOF
)
    RC=$?
    echo "$DETECT_OUTPUT" | sed 's/^/  /'

    if echo "$DETECT_OUTPUT" | grep -q "RESULT::MOCK_MODE"; then
        w "EFWS_RUN_MODE=mock di .env -- sim_detector tidak dites ke hardware asli. Set EFWS_RUN_MODE=hardware untuk tes ini."
    elif echo "$DETECT_OUTPUT" | grep -q "RESULT::OK"; then
        ok "detect_sim() berhasil -- modul dan port terbaca."
        if echo "$DETECT_OUTPUT" | grep -qi "REGISTRATION::.*+CREG: [0-9],1\|REGISTRATION::.*+CREG: [0-9],5"; then
            ok "Modem sudah registrasi ke jaringan (home/roaming)."
        else
            w "Status registrasi tidak menunjukkan home/roaming -- cek sinyal/APN/SIM."
        fi
    else
        f "detect_sim() gagal. Lihat pesan error di atas (kemungkinan port busy kalau efws.service masih jalan, atau modem memang tidak terdeteksi)."
    fi
fi

# =============================================================================
# 3. Tailscale: pastikan tidak menggeser default route, cek status DNS
# =============================================================================
log "3. Tailscale"

if ! command -v tailscale >/dev/null 2>&1; then
    info "Tailscale tidak terinstall di sistem ini -- lewati pengecekan."
else
    if ! systemctl is-active --quiet tailscaled; then
        w "tailscaled terinstall tapi tidak aktif."
    else
        ok "tailscaled aktif."
        TS_STATUS=$(tailscale status --json 2>/dev/null || true)

        if echo "$TS_STATUS" | grep -q '"ExitNodeStatus"'; then
            EXIT_NODE=$(echo "$TS_STATUS" | grep -oP '"ExitNodeStatus"\s*:\s*\K[^,}]*' || true)
        fi

        # Cek prefs: AcceptRoutes / ExitNodeID lewat 'tailscale debug prefs' kalau tersedia
        TS_PREFS=$(tailscale debug prefs 2>/dev/null || true)
        if echo "$TS_PREFS" | grep -qi '"RouteAll": *true\|"AcceptRoutes": *true'; then
            w "Tailscale AcceptRoutes aktif -- kalau salah satu tailnet peer advertise 0.0.0.0/0 (exit node), ini BISA menggeser default route menjauh dari GSM/WiFi. Pastikan ini memang disengaja."
        else
            ok "AcceptRoutes tidak terindikasi aktif -- default route GSM/WiFi tidak terganggu Tailscale."
        fi

        if echo "$TS_PREFS" | grep -qi '"ExitNodeID": *""' || ! echo "$TS_PREFS" | grep -qi '"ExitNodeID"'; then
            ok "Tidak sedang memakai exit node -- default route aman."
        else
            w "Tampaknya sedang memakai Tailscale exit node -- SEMUA traffic (termasuk ke EFWS_API_URL) akan lewat tailnet, bukan lewat GSM langsung."
        fi

        # DNS takeover check
        if command -v resolvectl >/dev/null 2>&1; then
            RESOLV_INFO=$(resolvectl status 2>/dev/null || true)
            if echo "$RESOLV_INFO" | grep -q "100.100.100.100"; then
                info "Tailscale MagicDNS (100.100.100.100) aktif sebagai salah satu DNS server."
                w "Kalau resolusi hostname EFWS_API_URL tiba-tiba lambat/gagal padahal koneksi GSM sehat, coba: sudo tailscale set --accept-dns=false lalu tes ulang."
            else
                ok "Tailscale tidak mengambil alih DNS resolver global."
            fi
        fi
    fi
fi

# =============================================================================
# 4. Default route + DNS + reachability nyata ke EFWS_API_URL
# =============================================================================
log "4. Default route, DNS, dan reachability ke EFWS_API_URL"

ROUTE_INFO=$(ip route get 8.8.8.8 2>&1 || true)
info "$ROUTE_INFO"
ACTIVE_IFACE=$(echo "$ROUTE_INFO" | grep -oP 'dev \K[^ ]+' | head -n1 || true)
info "Interface aktif untuk internet saat ini: ${ACTIVE_IFACE:-tidak diketahui}"

if [ "$ACTIVE_IFACE" = "cdc-wdm0" ] || echo "$ACTIVE_IFACE" | grep -q "wwan\|cdc-wdm"; then
    ok "Default route lewat modem GSM (sesuai prioritas yang diinginkan)."
elif [ -n "$ACTIVE_IFACE" ]; then
    w "Default route saat ini lewat '$ACTIVE_IFACE' (bukan GSM). Kalau GSM sedang tersambung juga, cek ulang route-metric-nya."
fi

# Ambil EFWS_API_URL dari .env project untuk tes langsung
API_URL=$(grep -m1 '^EFWS_API_URL=' "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2- | sed -e 's/\r$//' -e "s/^['\"]//" -e "s/['\"]$//")
if [ -z "$API_URL" ]; then
    w "Tidak menemukan EFWS_API_URL di $PROJECT_DIR/.env -- lewati tes reachability endpoint."
else
    API_HOST=$(echo "$API_URL" | sed -E 's#^[a-zA-Z]+://##; s#[/:].*$##')
    info "Endpoint dari .env : $API_URL"
    info "Host yang di-resolve: $API_HOST"

    if command -v getent >/dev/null 2>&1; then
        DNS_RESULT=$(getent hosts "$API_HOST" 2>&1 || true)
        if [ -n "$DNS_RESULT" ]; then
            ok "DNS resolve sukses: $DNS_RESULT"
        else
            f "DNS resolve GAGAL untuk $API_HOST. Cek resolver aktif (resolvectl status) atau APN operator."
        fi
    fi

    if command -v curl >/dev/null 2>&1; then
        HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_URL" 2>&1 || true)
        if [ -n "$HTTP_CODE" ] && [ "$HTTP_CODE" != "000" ]; then
            ok "Endpoint dapat dihubungi (HTTP $HTTP_CODE) lewat interface $ACTIVE_IFACE."
        else
            f "Gagal reach $API_URL (curl exit/HTTP: $HTTP_CODE). Cek koneksi & firewall APN."
        fi
    fi
fi

# =============================================================================
# Ringkasan
# =============================================================================
log "Ringkasan"
info "OK=$pass  WARN=$warn  FAIL=$fail"
if [ "$fail" -gt 0 ]; then
    info "Ada kegagalan yang perlu ditindaklanjuti sebelum yakin jalur komunikasi sehat."
elif [ "$warn" -gt 0 ]; then
    info "Tidak ada kegagalan fatal, tapi ada beberapa hal untuk diperiksa manual (lihat WARN di atas)."
else
    info "Semua pengecekan lolos."
fi
