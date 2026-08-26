#!/bin/bash

# ============================================================
# EFWS — Network Setup (SIM7600 + GPS Fetch)
#
# Alur:
#   1. Pastikan ModemManager & NetworkManager aktif
#   2. Nyalakan radio WWAN, matikan PPP konflik
#   3. Tunggu modem SIM7600 terdeteksi
#   4. Auto-detect provider dari operator code → set APN
#   5. Buat / update profil nmcli "EWS-4G"
#   6. Set WiFi sebagai backup (metric lebih besar)
#   7. Aktifkan koneksi EWS-4G
#   8. Verifikasi IP & default route
#   9. GPS fetch via AT+CGPS=1 + AT+CGPSINFO (3 percobaan)
#      Hasil disimpan ke GPS_CACHE_FILE untuk dibaca main.py
#
# GPS pre-panas (warm-up):
#   Percobaan 1 — setelah 90 detik warm-up (cold start butuh waktu)
#   Percobaan 2 — setelah +120 detik jika percobaan 1 gagal
#   Percobaan 3 — setelah +120 detik jika percobaan 2 gagal
#   Kalau semua gagal → tulis file dengan fix=false, main.py
#   akan pakai koordinat fallback dari .env
#
# Script selalu exit 0 → tidak pernah memblokir efws.service.
# ============================================================

set -u

# ── Konfigurasi ─────────────────────────────────────────────
CONNECTION_NAME="EWS-4G"
MODEM_METRIC=50
WIFI_METRIC=600
DEFAULT_APN="internet"

# Port AT command SIM7600:
#   ttyUSB0 = DM (diagnostic)
#   ttyUSB1 = AT secondary / NMEA
#   ttyUSB2 = AT command (dipakai script ini)
#   ttyUSB3 = PPP/modem (jangan dipakai)
SIM_AT_PORT="${EFWS_SIM_PORT:-/dev/ttyUSB2}"
SIM_BAUD="${EFWS_SIM_BAUD:-115200}"

# GPS: 3 percobaan dengan warm-up yang cukup
GPS_ATTEMPTS=3
GPS_WARMUP_FIRST=90      # detik warm-up sebelum percobaan 1 (cold start)
GPS_POLL_INTERVAL=5      # detik antar pembacaan AT+CGPSINFO per percobaan
GPS_POLL_TIMEOUT=60      # detik maks polling per percobaan (12x polling @ 5 detik)
GPS_RETRY_WAIT=120       # detik tunggu antar percobaan jika gagal

# Lokasi cache GPS — dibaca oleh main.py
GPS_CACHE_FILE="${EFWS_GPS_CACHE:-/tmp/ews_gps_cache.json}"

# Modem wait
MODEM_WAIT_ATTEMPTS=30
MODEM_WAIT_DELAY=2

# Log
LOG_DIR="/home/uwfadmin/ews/logs"
LOG_FILE="${LOG_DIR}/network_setup.log"
mkdir -p "$LOG_DIR"

# ── Helper logging ───────────────────────────────────────────
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}

log_gps() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [GPS] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}

# ── Helper: ambil Modem ID ───────────────────────────────────
get_modem_id() {
    mmcli -L 2>/dev/null \
        | grep -oE 'Modem/[0-9]+' \
        | head -n 1 \
        | cut -d/ -f2
}

# ── Helper: set WiFi sebagai backup ─────────────────────────
set_wifi_backup() {
    local found=0
    while IFS=: read -r cname ctype; do
        if [ "$ctype" = "802-11-wireless" ] && [ -n "$cname" ]; then
            nmcli connection modify "$cname" \
                connection.autoconnect yes \
                connection.autoconnect-priority 0 \
                ipv4.route-metric "$WIFI_METRIC" \
                ipv6.route-metric "$WIFI_METRIC" \
                2>/dev/null || true
            log "WiFi backup: $cname (metric $WIFI_METRIC)"
            found=1
        fi
    done < <(nmcli -t -f NAME,TYPE connection show 2>/dev/null)
    [ "$found" -eq 0 ] && log "Tidak ada profil WiFi ditemukan."
}

# ── Helper: kirim AT command ke serial port ──────────────────
# Membuka file descriptor sementara, kirim command, baca response
send_at() {
    local port="$1"
    local cmd="$2"
    local wait_sec="${3:-1}"
    local response

    # Kirim command
    printf '%s\r\n' "$cmd" > "$port" 2>/dev/null
    sleep "$wait_sec"

    # Baca response (baca semua yang tersedia)
    response=$(dd if="$port" count=1 bs=4096 iflag=nonblock 2>/dev/null || true)
    echo "$response"
}

# ── Helper: parse AT+CGPSINFO → JSON ────────────────────────
# Format: +CGPSINFO: ddmm.mmmm,N/S,dddmm.mmmm,E/W,DDMMYY,HHMMSS.s,alt,speed,course
# Contoh fix:    +CGPSINFO: 0114.5506,S,11649.5982,E,270826,173042.0,8.2,0.0,0.0
# Contoh no fix: +CGPSINFO: ,,,,,,,,
parse_cgpsinfo() {
    local raw="$1"
    local line

    # Ekstrak baris +CGPSINFO
    line=$(echo "$raw" | grep -oE '\+CGPSINFO:[^\r\n]+' | head -n1 || true)
    if [ -z "$line" ]; then
        echo ""
        return 1
    fi

    # Ambil bagian setelah ":"
    local data
    data=$(echo "$line" | sed 's/+CGPSINFO:[[:space:]]*//')

    # Cek apakah ada fix (field pertama tidak kosong)
    local lat_raw
    lat_raw=$(echo "$data" | cut -d, -f1 | tr -d ' ')
    if [ -z "$lat_raw" ]; then
        echo ""
        return 1
    fi

    local lat_ns lon_raw lon_ew date_raw utc_raw alt spd crs
    lat_ns=$(echo  "$data" | cut -d, -f2)
    lon_raw=$(echo "$data" | cut -d, -f3)
    lon_ew=$(echo  "$data" | cut -d, -f4)
    date_raw=$(echo "$data" | cut -d, -f5)
    utc_raw=$(echo  "$data" | cut -d, -f6)
    alt=$(echo     "$data" | cut -d, -f7)
    spd=$(echo     "$data" | cut -d, -f8)
    crs=$(echo     "$data" | cut -d, -f9 | tr -d '[:space:]')

    # Konversi NMEA ddmm.mmmm → desimal (pakai awk)
    local lat lon
    lat=$(awk -v nmea="$lat_raw" -v dir="$lat_ns" '
        BEGIN {
            dot = index(nmea, ".")
            deg = substr(nmea, 1, dot - 3) + 0
            min = substr(nmea, dot - 2) + 0
            dd  = deg + min / 60.0
            if (dir == "S") dd = -dd
            printf "%.6f", dd
        }
    ')
    lon=$(awk -v nmea="$lon_raw" -v dir="$lon_ew" '
        BEGIN {
            dot = index(nmea, ".")
            deg = substr(nmea, 1, dot - 3) + 0
            min = substr(nmea, dot - 2) + 0
            dd  = deg + min / 60.0
            if (dir == "W") dd = -dd
            printf "%.6f", dd
        }
    ')

    # Format tanggal dan waktu
    local date_fmt utc_fmt
    if [ ${#date_raw} -eq 6 ]; then
        date_fmt="${date_raw:0:2}/${date_raw:2:2}/20${date_raw:4:2}"
    else
        date_fmt="$date_raw"
    fi
    if [ ${#utc_raw} -ge 6 ]; then
        utc_fmt="${utc_raw:0:2}:${utc_raw:2:2}:${utc_raw:4}"
    else
        utc_fmt="$utc_raw"
    fi

    # Output JSON
    printf '{"fix":true,"lat":%s,"lon":%s,"altitude_m":%s,"speed_kmh":%s,"course_deg":"%s","date_utc":"%s","time_utc":"%s","source":"gps","timestamp":%s}\n' \
        "$lat" "$lon" \
        "${alt:-null}" \
        "${spd:-null}" \
        "${crs:-0}" \
        "$date_fmt" \
        "$utc_fmt" \
        "$(date +%s)"
    return 0
}

# ── Helper: tulis cache GPS (fix=false / fallback) ───────────
write_gps_cache_fallback() {
    local reason="$1"
    local ts
    ts=$(date +%s)
    cat > "$GPS_CACHE_FILE" <<EOF
{"fix":false,"lat":null,"lon":null,"reason":"${reason}","source":"none","timestamp":${ts}}
EOF
    log_gps "Cache ditulis (no fix): $reason"
}

# ── GPS fetch — fungsi utama ─────────────────────────────────
gps_fetch() {
    local port="$1"

    # Cek port ada
    if [ ! -e "$port" ]; then
        log_gps "Port $port tidak ditemukan. GPS skip."
        write_gps_cache_fallback "port_not_found:$port"
        return 0
    fi

    # Cek port tidak dipakai proses lain
    if fuser "$port" > /dev/null 2>&1; then
        log_gps "Port $port sedang dipakai proses lain. GPS skip."
        write_gps_cache_fallback "port_busy:$port"
        return 0
    fi

    log_gps "Memulai GPS fetch via AT command ($port)..."

    # Konfigurasi serial port
    stty -F "$port" "$SIM_BAUD" raw -echo cs8 -cstopb -parenb 2>/dev/null || {
        log_gps "Gagal konfigurasi stty $port. GPS skip."
        write_gps_cache_fallback "stty_failed"
        return 0
    }

    # Buka file descriptor ke port
    exec 7<>"$port" 2>/dev/null || {
        log_gps "Gagal buka $port. GPS skip."
        write_gps_cache_fallback "fd_open_failed"
        return 0
    }

    # Test AT dasar
    printf 'AT\r\n' >&7
    sleep 1
    local at_resp
    at_resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)
    if ! echo "$at_resp" | grep -q "OK"; then
        log_gps "Modem tidak merespons AT. GPS skip."
        exec 7>&-
        write_gps_cache_fallback "modem_no_at_response"
        return 0
    fi
    log_gps "Modem merespons AT."

    # Cek status GPS sebelum nyalakan
    printf 'AT+CGPS?\r\n' >&7; sleep 1
    local status_resp
    status_resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)

    # Nyalakan GPS engine
    printf 'AT+CGPS=1\r\n' >&7; sleep 2
    local on_resp
    on_resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)

    if echo "$on_resp" | grep -qE "OK|\+CGPS:"; then
        log_gps "GPS engine ON (AT+CGPS=1)."
    elif echo "$status_resp" | grep -q "+CGPS: 1"; then
        log_gps "GPS engine sudah ON sebelumnya."
    else
        log_gps "Respon AT+CGPS=1: $(echo "$on_resp" | tr -d '\r\n' | head -c 80)"
        log_gps "Lanjut polling meski respon tidak ideal..."
    fi

    local attempt fix_found=0 gps_json=""

    for attempt in 1 2 3; do
        if [ "$attempt" -eq 1 ]; then
            log_gps "Percobaan $attempt/$GPS_ATTEMPTS: warm-up ${GPS_WARMUP_FIRST}s (cold start GPS butuh waktu)..."
            sleep "$GPS_WARMUP_FIRST"
        else
            log_gps "Percobaan $attempt/$GPS_ATTEMPTS: tunggu ${GPS_RETRY_WAIT}s sebelum retry..."
            sleep "$GPS_RETRY_WAIT"
        fi

        log_gps "Polling AT+CGPSINFO (max ${GPS_POLL_TIMEOUT}s, interval ${GPS_POLL_INTERVAL}s)..."

        local elapsed=0
        while [ "$elapsed" -lt "$GPS_POLL_TIMEOUT" ]; do
            # Bersihkan buffer
            dd <&7 count=1 bs=4096 iflag=nonblock > /dev/null 2>&1 || true

            # Kirim AT+CGPSINFO
            printf 'AT+CGPSINFO\r\n' >&7
            sleep "$GPS_POLL_INTERVAL"

            local raw_resp
            raw_resp=$(dd <&7 count=1 bs=2048 iflag=nonblock 2>/dev/null || true)

            # Coba parse
            gps_json=$(parse_cgpsinfo "$raw_resp")
            if [ -n "$gps_json" ]; then
                log_gps "FIX ditemukan pada percobaan $attempt! lat=$(echo "$gps_json" | grep -oP '"lat":\K[0-9.-]+'), lon=$(echo "$gps_json" | grep -oP '"lon":\K[0-9.-]+')"
                fix_found=1
                break 2
            fi

            elapsed=$(( elapsed + GPS_POLL_INTERVAL ))
            log_gps "  Belum fix (${elapsed}s/${GPS_POLL_TIMEOUT}s)..."
        done

        log_gps "Percobaan $attempt gagal fix dalam ${GPS_POLL_TIMEOUT}s."
    done

    # Matikan GPS engine (hemat daya) — opsional, karena main.py tidak pakai serial
    printf 'AT+CGPS=0\r\n' >&7; sleep 1
    exec 7>&-
    log_gps "GPS engine OFF, port ditutup."

    if [ "$fix_found" -eq 1 ]; then
        echo "$gps_json" > "$GPS_CACHE_FILE"
        log_gps "Cache GPS disimpan: $GPS_CACHE_FILE"
        log_gps "  Data: $gps_json"
    else
        write_gps_cache_fallback "all_${GPS_ATTEMPTS}_attempts_failed"
        log_gps "Semua $GPS_ATTEMPTS percobaan GPS gagal. Cache fallback ditulis."
        log_gps "main.py akan pakai koordinat dari .env sebagai fallback."
    fi

    return 0
}

# ============================================================
# MAIN
# ============================================================
log "============================================================"
log "EFWS Network Setup dimulai"
log "Connection : $CONNECTION_NAME"
log "SIM port   : $SIM_AT_PORT"
log "GPS cache  : $GPS_CACHE_FILE"

# ── Step 1: Pastikan service berjalan ────────────────────────
log "[1/8] Cek ModemManager & NetworkManager..."
systemctl is-active --quiet ModemManager  || { log "Start ModemManager...";  systemctl start ModemManager;  }
systemctl is-active --quiet NetworkManager || { log "Start NetworkManager..."; systemctl start NetworkManager; }
sleep 2

# ── Step 2: Nyalakan radio WWAN, matikan konflik ─────────────
log "[2/8] Aktifkan WWAN radio..."
nmcli radio wwan on 2>/dev/null || true
poff -a     2>/dev/null || true
pkill -9 pppd 2>/dev/null || true

# ── Step 3: Tunggu modem terdeteksi ─────────────────────────
log "[3/8] Tunggu modem SIM7600..."
MODEM_ID=""
for attempt in $(seq 1 "$MODEM_WAIT_ATTEMPTS"); do
    MODEM_ID=$(get_modem_id)
    if [ -n "$MODEM_ID" ]; then
        log "Modem ditemukan: Modem/$MODEM_ID"
        break
    fi
    log "  Menunggu modem: $attempt/$MODEM_WAIT_ATTEMPTS ..."
    sleep "$MODEM_WAIT_DELAY"
done

if [ -z "$MODEM_ID" ]; then
    log "PERINGATAN: Modem tidak ditemukan. Skip setup GSM."
    write_gps_cache_fallback "modem_not_found"
    exit 0
fi

# Info modem + operator
MODEM_INFO=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null || true)
MODEM_MODEL=$(echo "$MODEM_INFO" | grep -oP 'modem\.generic\.model\s*:\s*\K.*' | head -n1 | xargs 2>/dev/null || true)
OPERATOR_CODE=$(echo "$MODEM_INFO" | grep -oP 'modem\.3gpp\.operator-code\s*:\s*\K\S+' | head -n1 || true)

log "Model modem    : ${MODEM_MODEL:-unknown}"
log "Operator code  : ${OPERATOR_CODE:-unknown}"

# ── Step 4: Tentukan APN berdasarkan provider ────────────────
log "[4/8] Tentukan APN..."
case "${OPERATOR_CODE:-}" in
    "51010") PROVIDER="Telkomsel / by.U"; APN="internet"  ;;
    "51011") PROVIDER="XL / AXIS";        APN="internet"  ;;
    "51001") PROVIDER="Indosat";          APN="internet"  ;;
    "51021") PROVIDER="Indosat IM3";      APN="internet"  ;;
    "51089") PROVIDER="Tri";              APN="3data"     ;;
    *)       PROVIDER="Default";          APN="${EFWS_APN:-$DEFAULT_APN}" ;;
esac

log "Provider : $PROVIDER"
log "APN      : $APN"

# Enable modem
mmcli -m "$MODEM_ID" --enable >> "$LOG_FILE" 2>&1 || true
sleep 2

# ── Step 5: Buat / update profil nmcli ──────────────────────
log "[5/8] Konfigurasi profil EWS-4G..."
if nmcli connection show "$CONNECTION_NAME" &>/dev/null; then
    log "Update profil '$CONNECTION_NAME'..."
else
    log "Buat profil baru '$CONNECTION_NAME'..."
    nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$APN" \
        >> "$LOG_FILE" 2>&1 || true
fi

nmcli connection modify "$CONNECTION_NAME" \
    gsm.apn                       "$APN" \
    connection.autoconnect         yes \
    connection.autoconnect-priority 100 \
    ipv4.method                    auto \
    ipv4.route-metric              "$MODEM_METRIC" \
    ipv6.method                    ignore \
    >> "$LOG_FILE" 2>&1 || true

# ── Step 6: Set WiFi sebagai backup ─────────────────────────
log "[6/8] Set WiFi sebagai backup..."
set_wifi_backup

# ── Step 7: Aktifkan koneksi 4G ─────────────────────────────
log "[7/8] Aktifkan koneksi EWS-4G..."
nmcli connection down "$CONNECTION_NAME" >> "$LOG_FILE" 2>&1 || true
sleep 1

CONNECTED=0
for attempt in 1 2 3 4 5; do
    log "  Percobaan koneksi: $attempt/5..."
    if nmcli connection up "$CONNECTION_NAME" >> "$LOG_FILE" 2>&1; then
        CONNECTED=1
        log "Koneksi '$CONNECTION_NAME' berhasil aktif!"
        break
    fi
    log "  Gagal, tunggu 5s..."
    sleep 5
done

if [ "$CONNECTED" -ne 1 ]; then
    log "PERINGATAN: Koneksi GSM gagal diaktifkan."
fi

sleep 3

# ── Step 8: Verifikasi & log hasil ──────────────────────────
log "[8/8] Verifikasi koneksi..."

ACTIVE_IFACE=""
for iface in wwan0 cdc-wdm0 usb0; do
    if ip addr show "$iface" 2>/dev/null | grep -q "inet "; then
        ACTIVE_IFACE="$iface"
        break
    fi
done

if [ -n "$ACTIVE_IFACE" ]; then
    IP_INFO=$(ip addr show "$ACTIVE_IFACE" | grep "inet " | awk '{print $2}' | head -n1)
    log "Interface aktif : $ACTIVE_IFACE"
    log "IP address      : ${IP_INFO:-unknown}"
else
    log "INFO: Belum ada IP pada interface GSM (nmcli mungkin masih proses)."
fi

log "Default route:"
ip route show default | tee -a "$LOG_FILE" | head -5

if ip route show default | grep -qE "wwan|cdc-wdm|usb"; then
    log "✓ Interface GSM menjadi koneksi utama."
else
    log "i Default route belum via GSM — WiFi mungkin lebih dulu atau GSM belum IP."
fi

# ── GPS Fetch (3 percobaan dengan warm-up) ───────────────────
log "------------------------------------------------------------"
log "GPS FETCH — $GPS_ATTEMPTS percobaan | warm-up: ${GPS_WARMUP_FIRST}s"
log "  Port        : $SIM_AT_PORT"
log "  Poll timeout: ${GPS_POLL_TIMEOUT}s per percobaan"
log "  Retry wait  : ${GPS_RETRY_WAIT}s antar percobaan"
log "  Cache file  : $GPS_CACHE_FILE"
log "------------------------------------------------------------"

gps_fetch "$SIM_AT_PORT"

log "============================================================"
log "EFWS Network Setup selesai."
exit 0
