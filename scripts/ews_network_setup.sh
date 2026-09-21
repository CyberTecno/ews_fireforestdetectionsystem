#!/bin/bash

# ============================================================
# EFWS — Network Setup (SIM7600 + GPS Fetch)
#
# Alur:
#   1. Make sure ModemManager & NetworkManager are active
#   2. Turn on radio WWAN, turn off conflict PPP
#   3. Wait for the SIM7600 modem to be detected
#   4. Auto-detect provider from operator code → set APN
#   5. Create/update nmcli profile "EWS-4G"
#   6. Set WiFi as backup (larger metric)
#   7. Activate the EWS-4G connection
#   8. Verifikasi IP & default route
#   9. GPS fetch via AT+CGPS=1 + AT+CGPSINFO (3 attempts)
#      Results are saved to GPS_CACHE_FILE for reading main.py
#
# GPS pre-panas (warm-up):
#   Trial 1 — after 90 seconds of warm-up (cold start takes time)
#   Attempt 2 — after +120 seconds if attempt 1 fails
#   Attempt 3 — after +120 seconds if attempt 2 fails
#   If all else fails → write the file with fix=false, main.py
#   will use fallback coordinates from .env
#
# Script always exits 0 → never blocks efws.service.
# ============================================================

set -u

# ── Configuration ────────────────────── ───────────────────────
CONNECTION_NAME="EWS-4G"
MODEM_METRIC=50
WIFI_METRIC=600
DEFAULT_APN="internet"

# Port AT command SIM7600:
#   ttyUSB0 = DM (diagnostic)
#   ttyUSB1 = AT secondary / NMEA
#   ttyUSB2 = AT command (used by this script)
#   ttyUSB3 = PPP/modem (do not use)
SIM_AT_PORT="${EFWS_SIM_PORT:-/dev/ttyUSB2}"
SIM_BAUD="${EFWS_SIM_BAUD:-115200}"

# GPS: 3 attempts with sufficient warm-up
GPS_ATTEMPTS=3
GPS_WARMUP_FIRST=90      # warm-up seconds before attempt 1 (cold start)
GPS_POLL_INTERVAL=5      # seconds between AT+CGPSINFO reads per attempt
GPS_POLL_TIMEOUT=60      # maximum polling seconds per attempt (12 polls at 5 seconds)
GPS_RETRY_WAIT=120       # seconds to wait between failed attempts

# Cache location GPS — read by main.py
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

# ── Helper: get Modem ID ───────────────────────────────────
get_modem_id() {
    mmcli -L 2>/dev/null \
        | grep -oE 'Modem/[0-9]+' \
        | head -n 1 \
        | cut -d/ -f2
}

# ── Helper: set WiFi as backup ─────────────────────────
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
    [ "$found" -eq 0 ] && log "No WiFi profile found."
}

# ── Helper: send AT command to serial port ──────────────────
# Open temporary file descriptor, send command, read response
send_at() {
    local port="$1"
    local cmd="$2"
    local wait_sec="${3:-1}"
    local response

    # Send command
    printf '%s\r\n' "$cmd" > "$port" 2>/dev/null
    sleep "$wait_sec"

    # Read response (read all available)
    response=$(dd if="$port" count=1 bs=4096 iflag=nonblock 2>/dev/null || true)
    echo "$response"
}

# ── Helper: parse AT+CGPSINFO → JSON ────────────────────────
# Format: +CGPSINFO: ddmm.mmmm,N/S,dddmm.mmmm,E/W,DDMMYY,HHMMSS.s,alt,speed,course
# Example fix: +CGPSINFO: 0114.5506,S,11649.5982,E,270826,173042.0,8.2,0.0,0.0
# Example fix number: +CGPSINFO: ,,,,,,,,
parse_cgpsinfo() {
    local raw="$1"
    local line

    # Extract the +CGPSINFO line
    line=$(echo "$raw" | grep -oE '\+CGPSINFO:[^\r\n]+' | head -n1 || true)
    if [ -z "$line" ]; then
        echo ""
        return 1
    fi

    # Take the part after ":"
    local data
    data=$(echo "$line" | sed 's/+CGPSINFO:[[:space:]]*//')

    # Check if there is a fix (the first field is not empty)
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

    # Convert NMEA ddmm.mmmm → decimal (use awk)
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

    # Date and time format
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

# ── Helper: write cache GPS (fix=false / fallback) ───────────
write_gps_cache_fallback() {
    local reason="$1"
    local ts
    ts=$(date +%s)
    cat > "$GPS_CACHE_FILE" <<EOF
{"fix":false,"lat":null,"lon":null,"reason":"${reason}","source":"none","timestamp":${ts}}
EOF
    log_gps "Cache written (no fix): $reason"
}

# ── Helper: Look for an AT port that is not busy ────────────────────
find_at_port() {
    local default_port="$1"
    local candidates="$default_port /dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB1"
    local checked=" "

    for p in $candidates; do
        if [ -z "$p" ] || [ ! -e "$p" ]; then
            continue
        fi

        # Avoid checking the same port twice
        if echo "$checked" | grep -q " $p "; then
            continue
        fi
        checked="$checked$p "

        # Check whether another process is used (example: ModemManager)
        if fuser "$p" > /dev/null 2>&1; then
            continue
        fi

        # Try setting stty
        stty -F "$p" "$SIM_BAUD" raw -echo cs8 -cstopb -parenb 2>/dev/null || continue

        # Try sending AT in subshell
        (
            exec 7<>"$p" || exit 1
            printf 'AT\r\n' >&7
            sleep 0.5
            resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)
            if echo "$resp" | grep -q "OK"; then
                exit 0
            fi
            exit 1
        ) 2>/dev/null

        if [ $? -eq 0 ]; then
            echo "$p"
            return 0
        fi
    done

    echo ""
    return 1
}

# ── GPS fetch — main function ─────────────────────────────────
gps_fetch() {
    local config_port="$1"
    local port

    log_gps "Looking for a free AT port (ModemManager may be locking $config_port)..."
    port=$(find_at_port "$config_port")

    if [ -z "$port" ]; then
        log_gps "No AT ports are free and responding. GPS skip."
        write_gps_cache_fallback "no_available_at_port"
        return 0
    fi

    log_gps "Using AT port: $port"

    # Serial port configuration
    stty -F "$port" "$SIM_BAUD" raw -echo cs8 -cstopb -parenb 2>/dev/null || {
        log_gps "Failed to configure stty $port. GPS skip."
        write_gps_cache_fallback "stty_failed"
        return 0
    }

    # Open the file descriptor to the port
    exec 7<>"$port" 2>/dev/null || {
        log_gps "Failed to open $port. GPS skip."
        write_gps_cache_fallback "fd_open_failed"
        return 0
    }

    # Basic AT test (already confirmed by find_at_port, but confirm again in this fd)
    printf 'AT\r\n' >&7
    sleep 1
    local at_resp
    at_resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)
    if ! echo "$at_resp" | grep -q "OK"; then
        log_gps "The modem is not responding to AT. GPS skip."
        exec 7>&-
        write_gps_cache_fallback "modem_no_at_response"
        return 0
    fi
    log_gps "The modem responds to AT."

    # Check the status of GPS before turning it on
    printf 'AT+CGPS?\r\n' >&7; sleep 1
    local status_resp
    status_resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)

    # Turn on the GPS engine
    printf 'AT+CGPS=1\r\n' >&7; sleep 2
    local on_resp
    on_resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)

    if echo "$on_resp" | grep -qE "OK|\+CGPS:"; then
        log_gps "GPS engine ON (AT+CGPS=1)."
    elif echo "$status_resp" | grep -q "+CGPS: 1"; then
        log_gps "GPS engine was ON previously."
    else
        log_gps "Respon AT+CGPS=1: $(echo "$on_resp" | tr -d '\r\n' | head -c 80)"
        log_gps "Continue polling even though the response is not ideal..."
    fi

    local attempt fix_found=0 gps_json=""

    for attempt in 1 2 3; do
        if [ "$attempt" -eq 1 ]; then
            log_gps "Experiment $attempt/$GPS_ATTEMPTS: warm-up ${GPS_WARMUP_FIRST}s (cold start GPS takes time)..."
            sleep "$GPS_WARMUP_FIRST"
        else
            log_gps "Trial $attempt/$GPS_ATTEMPTS: wait for ${GPS_RETRY_WAIT}s before retrying..."
            sleep "$GPS_RETRY_WAIT"
        fi

        log_gps "Polling AT+CGPSINFO (max ${GPS_POLL_TIMEOUT}s, interval ${GPS_POLL_INTERVAL}s)..."

        local elapsed=0
        while [ "$elapsed" -lt "$GPS_POLL_TIMEOUT" ]; do
            # Clear the buffer
            dd <&7 count=1 bs=4096 iflag=nonblock > /dev/null 2>&1 || true

            # Send AT+CGPSINFO
            printf 'AT+CGPSINFO\r\n' >&7
            sleep "$GPS_POLL_INTERVAL"

            local raw_resp
            raw_resp=$(dd <&7 count=1 bs=2048 iflag=nonblock 2>/dev/null || true)

            # Try parsing
            gps_json=$(parse_cgpsinfo "$raw_resp")
            if [ -n "$gps_json" ]; then
                log_gps "FIX discovered in experiment $attempt! lat=$(echo"$gps_json" | grep -oP '"lat":\K[0-9.-]+'), lon=$(echo "$gps_json" | grep -oP '"lon":\K[0-9.-]+')"
                fix_found=1
                break 2
            fi

            elapsed=$(( elapsed + GPS_POLL_INTERVAL ))
            log_gps "Not yet fixed (${elapsed}s/${GPS_POLL_TIMEOUT}s)..."
        done

        log_gps "Attempt $attempt failed to fix in ${GPS_POLL_TIMEOUT}s."
    done

    # Turn off GPS engine (power saving) — optional, because main.py does not use serial
    printf 'AT+CGPS=0\r\n' >&7; sleep 1
    exec 7>&-
    log_gps "GPS engine OFF; port closed."

    if [ "$fix_found" -eq 1 ]; then
        echo "$gps_json" > "$GPS_CACHE_FILE"
        log_gps "GPS cache saved: $GPS_CACHE_FILE"
        log_gps "  Data: $gps_json"
    else
        write_gps_cache_fallback "all_${GPS_ATTEMPTS}_attempts_failed"
        log_gps "All $GPS_ATTEMPTS attempts GPS failed. The fallback cache is written."
        log_gps "main.py will use the coordinates from .env as a fallback."
    fi

    return 0
}

# ============================================================
# MAIN
# ============================================================
log "============================================================"
log "EFWS Network Setup started"
log "Connection : $CONNECTION_NAME"
log "SIM port   : $SIM_AT_PORT"
log "GPS cache  : $GPS_CACHE_FILE"

# ── Step 1: Make sure the service is running ────────────────────────
log "[1/8] Check ModemManager & NetworkManager..."
systemctl is-active --quiet ModemManager  || { log "Start ModemManager...";  systemctl start ModemManager;  }
systemctl is-active --quiet NetworkManager || { log "Start NetworkManager..."; systemctl start NetworkManager; }
sleep 2

# ── Step 2: Turn on radio WWAN, turn off conflict ─────────────
log "[2/8] Enable WWAN radio..."
nmcli radio wwan on 2>/dev/null || true
poff -a     2>/dev/null || true
pkill -9 pppd 2>/dev/null || true

# ── Step 3: Wait for the modem to be detected ─────────────────────────
log "[3/8] Wait for modem SIM7600..."
MODEM_ID=""
for attempt in $(seq 1 "$MODEM_WAIT_ATTEMPTS"); do
    MODEM_ID=$(get_modem_id)
    if [ -n "$MODEM_ID" ]; then
        log "Modem found: Modem/$MODEM_ID"
        break
    fi
    log "Waiting for modem: $attempt/$MODEM_WAIT_ATTEMPTS..."
    sleep "$MODEM_WAIT_DELAY"
done

if [ -z "$MODEM_ID" ]; then
    log "WARNING: Modem not found. Skip setup GSM."
    write_gps_cache_fallback "modem_not_found"
    exit 0
fi

# Info modem + operator
MODEM_INFO=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null || true)
MODEM_MODEL=$(echo "$MODEM_INFO" | grep -oP 'modem\.generic\.model\s*:\s*\K.*' | head -n1 | xargs 2>/dev/null || true)
OPERATOR_CODE=$(echo "$MODEM_INFO" | grep -oP 'modem\.3gpp\.operator-code\s*:\s*\K\S+' | head -n1 || true)

log "Model modem    : ${MODEM_MODEL:-unknown}"
log "Operator code  : ${OPERATOR_CODE:-unknown}"

# ── Step 4: Determine APN based on provider ────────────────
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

# ── Step 5: Create / update nmcli profile ──────────────────────
log "[5/8] EWS-4G profile configuration..."
if nmcli connection show "$CONNECTION_NAME" &>/dev/null; then
    log "Update profile '$CONNECTION_NAME'..."
else
    log "Create a new profile '$CONNECTION_NAME'..."
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

# ── Step 6: Set WiFi as backup ─────────────────────────
log "[6/8] Set WiFi as backup..."
set_wifi_backup

# ── Step 7: Activate 4G connection ─────────────────────────────
log "[7/8] Enable connection EWS-4G..."
nmcli connection down "$CONNECTION_NAME" >> "$LOG_FILE" 2>&1 || true
sleep 1

CONNECTED=0
for attempt in 1 2 3 4 5; do
    log "Connection attempt: $attempt/5..."
    if nmcli connection up "$CONNECTION_NAME" >> "$LOG_FILE" 2>&1; then
        CONNECTED=1
        log "Connection '$CONNECTION_NAME' is successfully active!"
        break
    fi
    log "Failed, wait 5s..."
    sleep 5
done

if [ "$CONNECTED" -ne 1 ]; then
    log "WARNING: Connection GSM failed to activate."
fi

sleep 3

# ── Step 8: Verify & log results ──────────────────────────
log "[8/8] Verify connection..."

ACTIVE_IFACE=""
for iface in wwan0 cdc-wdm0 usb0; do
    if ip addr show "$iface" 2>/dev/null | grep -q "inet "; then
        ACTIVE_IFACE="$iface"
        break
    fi
done

if [ -n "$ACTIVE_IFACE" ]; then
    IP_INFO=$(ip addr show "$ACTIVE_IFACE" | grep "inet " | awk '{print $2}' | head -n1)
    log "Active interface: $ACTIVE_IFACE"
    log "IP address      : ${IP_INFO:-unknown}"
else
    log "INFO: No IP yet on interface GSM (nmcli may still be processing)."
fi

log "Default route:"
ip route show default | tee -a "$LOG_FILE" | head -5

if ip route show default | grep -qE "wwan|cdc-wdm|usb"; then
    log "✓ Interface GSM is the main connection."
else
    log "i Default route is not yet via GSM — WiFi may come first or GSM is not IP yet."
fi

# ── GPS Fetch (3 attempts with warm-up) ───────────────────
log "------------------------------------------------------------"
log "GPS FETCH — $GPS_ATTEMPTS trial | warm-up: ${GPS_WARMUP_FIRST}s"
log "  Port        : $SIM_AT_PORT"
log "Poll timeout: ${GPS_POLL_TIMEOUT}s per attempt"
log "Retry wait : ${GPS_RETRY_WAIT}s between tries"
log "Cache file : $GPS_CACHE_FILE"
log "------------------------------------------------------------"

gps_fetch "$SIM_AT_PORT"

log "============================================================"
log "EFWS Network Setup is complete."
exit 0
