#!/bin/bash
# =============================================================================
# EWS GSM Auto Connect (v2)
# =============================================================================
# Perubahan utama dari versi sebelumnya:
#   1. Menunggu modem BENAR-BENAR teregistrasi ke jaringan operator (3GPP
#      attach), bukan cuma menunggu modem terdeteksi oleh ModemManager.
#   2. `nmcli connection up` dicoba beberapa kali (retry+backoff), dan
#      setiap percobaan diverifikasi dengan mengecek default route benar2
#      lewat interface modem -- bukan asal exit 0.
#   3. Semua langkah kritikal dicatat dengan status jelas (OK/WARN/FAIL)
#      dan timestamp, tidak ada lagi `|| true` yang membungkam kegagalan.
#   4. Dicek juga status SIM (locked/PIN) supaya kalau SIM ke-lock, itu
#      langsung kelihatan di log alih-alih diam-diam gagal connect.
#   5. Exit code skrip TETAP selalu 0 di akhir (lihat bagian "EXIT POLICY"
#      di bawah) -- ini SENGAJA dipertahankan sama seperti versi lama,
#      supaya efws.service (yang memakai Requires=gsm-connect.service)
#      tetap start walau GSM gagal total, dan EFWS bisa jalan pakai
#      offline queue / WiFi backup. Yang berubah bukan exit code-nya,
#      tapi APAKAH GSM benar-benar connect atau tidak sekarang tercatat
#      jelas di journal (journalctl -u gsm-connect).
# =============================================================================

set -u

CONNECTION_NAME="EWS-4G"
DEFAULT_APN="internet"
MODEM_METRIC=50
WIFI_METRIC=600

MODEM_WAIT_ATTEMPTS=30       # tunggu modem terdeteksi: 30 x 2s = 60s
REGISTRATION_WAIT_ATTEMPTS=30 # tunggu attach ke jaringan: 30 x 2s = 60s
CONNECT_ATTEMPTS=4            # percobaan nmcli connection up
CONNECT_RETRY_DELAY=5         # jeda antar percobaan (detik)

# -----------------------------------------------------------------------
# Logging helper -- semua log punya timestamp + level, masuk ke journald
# lewat StandardOutput=journal di service file, jadi bisa dilihat dengan:
#   journalctl -u gsm-connect -b
# -----------------------------------------------------------------------
log() {
    local level="$1"; shift
    printf '[EWS-GSM][%s] %s: %s\n' "$(date '+%H:%M:%S')" "$level" "$*"
}

log INFO "Starting GSM auto connect..."

systemctl is-active --quiet ModemManager || systemctl start ModemManager
systemctl is-active --quiet NetworkManager || systemctl start NetworkManager

nmcli radio wwan on || log WARN "Gagal mengaktifkan radio wwan (mungkin sudah on)"

# Create GSM connection profile if not exists
if ! nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
    log INFO "Membuat profil GSM baru: $CONNECTION_NAME"
    if ! nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$DEFAULT_APN"; then
        log FAIL "Gagal membuat profil GSM. Cek apakah plugin NetworkManager-gsm terpasang."
    fi
fi

# -----------------------------------------------------------------------
# STEP 1: Tunggu modem terdeteksi oleh ModemManager
# -----------------------------------------------------------------------
MODEM_ID=""
for i in $(seq 1 "$MODEM_WAIT_ATTEMPTS"); do
    MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
    if [ -n "$MODEM_ID" ]; then
        log INFO "Modem terdeteksi: ID=$MODEM_ID (percobaan $i)"
        break
    fi
    log INFO "Menunggu modem terdeteksi... ($i/$MODEM_WAIT_ATTEMPTS)"
    sleep 2
done

if [ -z "$MODEM_ID" ]; then
    log FAIL "Modem TIDAK terdeteksi setelah $((MODEM_WAIT_ATTEMPTS*2))s. Cek koneksi USB/serial modem."
    log WARN "Melanjutkan tanpa GSM -- sistem akan bergantung pada WiFi (jika ada)."
fi

APN="$DEFAULT_APN"
PROVIDER="Unknown"
REGISTERED=false

if [ -n "$MODEM_ID" ]; then

    if ! mmcli -m "$MODEM_ID" --enable >/dev/null 2>&1; then
        log WARN "mmcli --enable gagal atau modem sudah enabled, lanjut cek status."
    fi
    sleep 3

    # -- Cek status SIM (locked / missing) supaya kegagalan SIM tidak
    #    ketutup diam-diam seperti sebelumnya.
    SIM_STATUS=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.generic.state" | cut -d= -f2 | tr -d ' ' || true)
    if [ "$SIM_STATUS" = "locked" ]; then
        log FAIL "Modem dalam status 'locked' -- kemungkinan SIM butuh PIN. GSM tidak akan bisa connect sampai ini dibereskan manual (mmcli -m $MODEM_ID --pin=XXXX)."
    fi

    OPERATOR_CODE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.operator-code" | cut -d= -f2 | tr -d ' ' || true)

    case "$OPERATOR_CODE" in
        "51010") PROVIDER="Telkomsel / by.U"; APN="internet" ;;
        "51011") PROVIDER="XL / AXIS";        APN="internet" ;;
        "51001") PROVIDER="Indosat";          APN="internet" ;;
        "51021") PROVIDER="Indosat / IM3";    APN="internet" ;;
        "51089") PROVIDER="Tri";              APN="3data"    ;;
        *)       PROVIDER="Default";          APN="$DEFAULT_APN" ;;
    esac

    log INFO "Provider terdeteksi : $PROVIDER (operator-code: ${OPERATOR_CODE:-unknown})"
    log INFO "APN yang dipakai    : $APN"

    # -------------------------------------------------------------------
    # STEP 2: Tunggu modem BENAR-BENAR attach ke jaringan operator.
    # Ini bagian yang HILANG di versi lama -- versi lama cuma menunggu
    # modem "terdeteksi", lalu langsung nmcli connection up. Padahal
    # antara "modem terdeteksi" dan "modem attach ke jaringan seluler"
    # (registration-state = home/roaming) bisa butuh 10-40 detik lagi,
    # terutama kalau sinyal lemah. Kalau nmcli up dipanggil sebelum ini
    # selesai, ia gampang timeout -- dan versi lama membungkam error itu
    # dengan `|| true` sehingga kelihatan "berhasil" padahal tidak.
    # -------------------------------------------------------------------
    for i in $(seq 1 "$REGISTRATION_WAIT_ATTEMPTS"); do
        REG_STATE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.registration-state" | cut -d= -f2 | tr -d ' ' || true)
        if [ "$REG_STATE" = "home" ] || [ "$REG_STATE" = "roaming" ]; then
            log INFO "Modem teregistrasi ke jaringan operator (state: $REG_STATE), percobaan $i"
            REGISTERED=true
            break
        fi
        log INFO "Menunggu registrasi ke jaringan seluler... state saat ini: ${REG_STATE:-unknown} ($i/$REGISTRATION_WAIT_ATTEMPTS)"
        sleep 2
    done

    if [ "$REGISTERED" = false ]; then
        log FAIL "Modem tidak berhasil attach ke jaringan operator dalam $((REGISTRATION_WAIT_ATTEMPTS*2))s. Sinyal mungkin lemah atau SIM bermasalah."
    fi
fi

# -----------------------------------------------------------------------
# Configure GSM connection profile (metric rendah = prioritas utama)
# -----------------------------------------------------------------------
nmcli connection modify "$CONNECTION_NAME" \
    gsm.apn "$APN" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    ipv4.method auto \
    ipv4.route-metric "$MODEM_METRIC" \
    ipv6.method ignore \
    || log FAIL "Gagal memodifikasi profil koneksi $CONNECTION_NAME"

# -----------------------------------------------------------------------
# Configure WiFi as backup (metric tinggi = prioritas rendah, TAPI tetap
# auto-connect supaya dipakai kalau GSM gagal total). Bagian ini TIDAK
# butuh WiFi untuk ada -- kalau tidak ada profil WiFi tersimpan, loop di
# bawah cuma jalan atas daftar kosong dan tidak melakukan apa-apa. Jadi
# ketiadaan WiFi TIDAK menghalangi langkah-langkah GSM di atas maupun di
# bawah sama sekali.
# -----------------------------------------------------------------------
WIFI_CONNECTIONS=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 || true)

if [ -z "$WIFI_CONNECTIONS" ]; then
    log INFO "Tidak ada profil WiFi tersimpan -- lanjut hanya dengan GSM."
else
    echo "$WIFI_CONNECTIONS" | while read -r WIFI_NAME; do
        if [ -n "$WIFI_NAME" ]; then
            log INFO "Set WiFi sebagai backup: $WIFI_NAME"
            nmcli connection modify "$WIFI_NAME" \
                connection.autoconnect yes \
                connection.autoconnect-priority 0 \
                ipv4.route-metric "$WIFI_METRIC" \
                ipv6.route-metric "$WIFI_METRIC" \
                || log WARN "Gagal memodifikasi profil WiFi $WIFI_NAME"
        fi
    done
fi

# -----------------------------------------------------------------------
# STEP 3: Connect GSM dengan retry, dan VERIFIKASI hasilnya nyata --
# bukan cuma "nmcli exit 0" tapi benar-benar cek default route lewat
# interface modem. Ini juga bagian yang hilang di versi lama.
# -----------------------------------------------------------------------
GSM_CONNECTED=false

for attempt in $(seq 1 "$CONNECT_ATTEMPTS"); do
    log INFO "Menghubungkan GSM... percobaan $attempt/$CONNECT_ATTEMPTS"

    if nmcli connection up "$CONNECTION_NAME" >/dev/null 2>&1; then
        GSM_IFACE=$(nmcli -g GENERAL.DEVICES connection show "$CONNECTION_NAME" 2>/dev/null | head -n1)
        ROUTE_INFO=$(ip route get 8.8.8.8 2>/dev/null || true)

        if [ -n "$GSM_IFACE" ] && echo "$ROUTE_INFO" | grep -q "dev $GSM_IFACE"; then
            log INFO "GSM connected. Default route terkonfirmasi lewat interface $GSM_IFACE."
            GSM_CONNECTED=true
            break
        else
            log WARN "nmcli melaporkan sukses tapi default route BELUM lewat interface GSM ($GSM_IFACE). Mungkin masih tertahan WiFi metric atau belum dapat IP."
        fi
    else
        log WARN "nmcli connection up gagal pada percobaan $attempt."
    fi

    if [ "$attempt" -lt "$CONNECT_ATTEMPTS" ]; then
        sleep "$CONNECT_RETRY_DELAY"
    fi
done

if [ "$GSM_CONNECTED" = true ]; then
    log INFO "STATUS AKHIR: GSM/SIM berhasil connect dan jadi jalur utama."
else
    log FAIL "STATUS AKHIR: GSM/SIM GAGAL connect setelah $CONNECT_ATTEMPTS percobaan."
    if [ -n "$WIFI_CONNECTIONS" ]; then
        log WARN "Sistem akan mengandalkan WiFi sebagai fallback (jika WiFi berhasil connect)."
    else
        log WARN "Tidak ada WiFi backup tersedia -- kemungkinan TIDAK ADA konektivitas internet sama sekali. EFWS akan jalan dengan offline queue."
    fi
fi

log INFO "Current route:"
ip route get 8.8.8.8 2>&1 || log WARN "Tidak bisa resolve route ke 8.8.8.8 -- kemungkinan belum ada koneksi internet sama sekali."

log INFO "Done."

# =============================================================================
# EXIT POLICY (SENGAJA, jangan diubah tanpa update efws.service juga):
# Skrip ini SELALU exit 0, walau GSM_CONNECTED=false. Ini konsisten
# dengan versi lama, sesuai dependency `efws.service` yang pakai
# `Requires=gsm-connect.service`. Kalau skrip ini exit non-zero, systemd
# akan MEMBLOKIR efws.service sama sekali -- padahal EFWS punya
# offline-queue dan tetap berguna berjalan lokal walau tanpa internet.
# Yang membedakan dari versi lama: sekarang status sukses/gagal GSM
# TERCATAT JELAS di journal, tidak lagi dibungkam oleh `|| true`.
# =============================================================================
exit 0