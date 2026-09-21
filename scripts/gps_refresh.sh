#!/bin/bash

# ============================================================
# EFWS — GPS Refresh (run every 30 minutes by systemd timer)
#
# Tugas:
#   - Retrieve the latest GPS position from SIM7600 via AT command
#   - Save to GPS_CACHE_FILE (JSON)
#   - main.py reads this file every time Location Publisher runs
#
# No network setup required — just GPS fetch.
# Can also be run manually: sudo bash /home/uwfadmin/ews/scripts/gps_refresh.sh
# ============================================================

set -u

SIM_AT_PORT="${EFWS_SIM_PORT:-/dev/ttyUSB2}"
SIM_BAUD="${EFWS_SIM_BAUD:-115200}"
GPS_CACHE_FILE="${EFWS_GPS_CACHE:-/tmp/ews_gps_cache.json}"

GPS_ATTEMPTS=3
GPS_WARMUP_FIRST=60      # first-attempt warm-up seconds (shorter than boot; GPS is pre-warmed)
GPS_POLL_INTERVAL=5      # seconds between AT+CGPSINFO reads
GPS_POLL_TIMEOUT=60      # maximum seconds per attempt
GPS_RETRY_WAIT=90        # seconds to wait between failed attempts

LOG_DIR="/home/uwfadmin/ews/logs"
LOG_FILE="${LOG_DIR}/gps_refresh.log"
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [GPS-refresh] $*" | tee -a "$LOG_FILE"
}

# ── Parse AT+CGPSINFO → JSON (same as ews_network_setup.sh) ──
parse_cgpsinfo() {
    local raw="$1"
    local line

    line=$(echo "$raw" | grep -oE '\+CGPSINFO:[^\r\n]+' | head -n1 || true)
    [ -z "$line" ] && { echo ""; return 1; }

    local data lat_raw lat_ns lon_raw lon_ew date_raw utc_raw alt spd crs
    data=$(echo "$line" | sed 's/+CGPSINFO:[[:space:]]*//')
    lat_raw=$(echo "$data" | cut -d, -f1 | tr -d ' ')
    [ -z "$lat_raw" ] && { echo ""; return 1; }

    lat_ns=$(echo  "$data" | cut -d, -f2)
    lon_raw=$(echo "$data" | cut -d, -f3)
    lon_ew=$(echo  "$data" | cut -d, -f4)
    date_raw=$(echo "$data" | cut -d, -f5)
    utc_raw=$(echo  "$data" | cut -d, -f6)
    alt=$(echo     "$data" | cut -d, -f7)
    spd=$(echo     "$data" | cut -d, -f8)
    crs=$(echo     "$data" | cut -d, -f9 | tr -d '[:space:]')

    local lat lon
    lat=$(awk -v nmea="$lat_raw" -v dir="$lat_ns" 'BEGIN {
        dot=index(nmea,".")
        dd=substr(nmea,1,dot-3)+0 + substr(nmea,dot-2)+0/60
        if(dir=="S") dd=-dd
        printf "%.6f", dd }')
    lon=$(awk -v nmea="$lon_raw" -v dir="$lon_ew" 'BEGIN {
        dot=index(nmea,".")
        dd=substr(nmea,1,dot-3)+0 + substr(nmea,dot-2)+0/60
        if(dir=="W") dd=-dd
        printf "%.6f", dd }')

    local date_fmt utc_fmt
    [ ${#date_raw} -eq 6 ] && date_fmt="${date_raw:0:2}/${date_raw:2:2}/20${date_raw:4:2}" || date_fmt="$date_raw"
    [ ${#utc_raw} -ge 6 ]  && utc_fmt="${utc_raw:0:2}:${utc_raw:2:2}:${utc_raw:4}"       || utc_fmt="$utc_raw"

    printf '{"fix":true,"lat":%s,"lon":%s,"altitude_m":%s,"speed_kmh":%s,"course_deg":"%s","date_utc":"%s","time_utc":"%s","source":"gps","timestamp":%s}\n' \
        "$lat" "$lon" "${alt:-null}" "${spd:-null}" "${crs:-0}" "$date_fmt" "$utc_fmt" "$(date +%s)"
    return 0
}

write_fallback() {
    local reason="$1"
    cat > "$GPS_CACHE_FILE" <<EOF
{"fix":false,"lat":null,"lon":null,"reason":"${reason}","source":"none","timestamp":$(date +%s)}
EOF
    log "Fallback cache written: $reason"
}

# ── Check whether the cache is valid and still fresh (< 35 minutes) ─────
if [ -f "$GPS_CACHE_FILE" ]; then
    CACHE_TS=$(grep -oP '"timestamp":\K[0-9]+' "$GPS_CACHE_FILE" 2>/dev/null || echo 0)
    CACHE_FIX=$(grep -oP '"fix":\K(true|false)' "$GPS_CACHE_FILE" 2>/dev/null || echo "false")
    NOW=$(date +%s)
    AGE=$(( NOW - CACHE_TS ))

    if [ "$CACHE_FIX" = "true" ] && [ "$AGE" -lt 2100 ]; then
        log "Cache GPS is still fresh ($((AGE/60)) minutes), skip fetch."
        exit 0
    fi
fi

# ── Helper: Look for an AT port that is not busy ────────────────────
find_at_port() {
    local default_port="$1"
    local candidates="$default_port /dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB1"
    local checked=" "

    for p in $candidates; do
        if [ -z "$p" ] || [ ! -e "$p" ]; then
            continue
        fi
        if echo "$checked" | grep -q " $p "; then
            continue
        fi
        checked="$checked$p "

        if fuser "$p" > /dev/null 2>&1; then
            continue
        fi

        stty -F "$p" "$SIM_BAUD" raw -echo cs8 -cstopb -parenb 2>/dev/null || continue

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
    return 1
}

log "Start looking for a free AT port (ModemManager may be locking $SIM_AT_PORT)..."

SIM_AT_PORT=$(find_at_port "$SIM_AT_PORT")
if [ -z "$SIM_AT_PORT" ]; then
    log "Didn't find a free and responding AT port. Skip."
    write_fallback "no_available_at_port"
    exit 0
fi

log "Using AT port: $SIM_AT_PORT"

# ── Port configuration ──────────────────── ────────────────────
stty -F "$SIM_AT_PORT" "$SIM_BAUD" raw -echo cs8 -cstopb -parenb 2>/dev/null || {
    log "Stty configuration failed. Skip."
    write_fallback "stty_failed"
    exit 0
}

exec 7<>"$SIM_AT_PORT" 2>/dev/null || {
    log "Failed to open port. Skip."
    write_fallback "fd_failed"
    exit 0
}


# ── Make sure GPS is ON ──────────────────── ─────────────────────
printf 'AT+CGPS?\r\n' >&7; sleep 1
dd <&7 count=1 bs=512 iflag=nonblock > /dev/null 2>&1 || true
printf 'AT+CGPS=1\r\n' >&7; sleep 2
dd <&7 count=1 bs=512 iflag=nonblock > /dev/null 2>&1 || true
log "GPS engine ON."

# ── 3 Fetch attempts ──────────────────── ────────────────────
FIX_FOUND=0
GPS_JSON=""

for attempt in 1 2 3; do
    if [ "$attempt" -eq 1 ]; then
        log "Experiment $attempt/$GPS_ATTEMPTS: warm-up ${GPS_WARMUP_FIRST}s..."
        sleep "$GPS_WARMUP_FIRST"
    else
        log "Trial $attempt/$GPS_ATTEMPTS: wait ${GPS_RETRY_WAIT}s..."
        sleep "$GPS_RETRY_WAIT"
    fi

    log "Polling (max ${GPS_POLL_TIMEOUT}s)..."
    elapsed=0

    while [ "$elapsed" -lt "$GPS_POLL_TIMEOUT" ]; do
        dd <&7 count=1 bs=4096 iflag=nonblock > /dev/null 2>&1 || true
        printf 'AT+CGPSINFO\r\n' >&7
        sleep "$GPS_POLL_INTERVAL"

        RAW=$(dd <&7 count=1 bs=2048 iflag=nonblock 2>/dev/null || true)
        GPS_JSON=$(parse_cgpsinfo "$RAW")

        if [ -n "$GPS_JSON" ]; then
            log "FIX! lat=$(echo "$GPS_JSON" | grep -oP '"lat":\K[0-9.-]+'), lon=$(echo "$GPS_JSON" | grep -oP '"lon":\K[0-9.-]+')"
            FIX_FOUND=1
            break 2
        fi

        elapsed=$(( elapsed + GPS_POLL_INTERVAL ))
        log "  No fix (${elapsed}s/${GPS_POLL_TIMEOUT}s)..."
    done

    log "Attempt $attempt failed."
done

# Turn off GPS (power saving)
printf 'AT+CGPS=0\r\n' >&7; sleep 1
exec 7>&-

if [ "$FIX_FOUND" -eq 1 ]; then
    echo "$GPS_JSON" > "$GPS_CACHE_FILE"
    log "Cache saved: $GPS_CACHE_FILE"
else
    write_fallback "all_attempts_failed"
fi

log "GPS refresh completed."
exit 0
