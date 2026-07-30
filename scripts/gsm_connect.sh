#!/bin/bash

# ============================================================
# EFWS — SIM7600 IoT GSM Primary Connection
#
# Tidak melakukan:
# - apt update/install
# - ping
# - curl
# - DNS lookup
# - menunggu WiFi
# - network-online.target
#
# Hanya:
# - mendeteksi SIM7600
# - connect APN m2minternet
# - memasang IP/gateway bearer
# - menjadikan wwan0 sebagai default route utama
# ============================================================

APN="m2minternet"
WWAN_INTERFACE="wwan0"

GSM_METRIC=50
WIFI_METRIC=600

MODEM_WAIT_ATTEMPTS=30
MODEM_WAIT_DELAY=2

CONNECT_ATTEMPTS=5
CONNECT_RETRY_DELAY=5

LOG_DIR="/home/uwfadmin/ews/logs"
LOG_FILE="${LOG_DIR}/iot_gsm_connect.log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" |
        tee -a "$LOG_FILE"
}

get_modem_id() {
    mmcli -L 2>/dev/null |
        grep -oE 'Modem/[0-9]+' |
        head -n 1 |
        cut -d/ -f2
}

get_bearer_id() {
    local modem_id="$1"

    mmcli -m "$modem_id" --list-bearers 2>/dev/null |
        grep -oE 'Bearer/[0-9]+' |
        tail -n 1 |
        cut -d/ -f2
}

get_bearer_field() {
    local bearer_output="$1"
    local field_name="$2"

    echo "$bearer_output" |
        awk -F': ' -v key="$field_name" '
            index($0, key) {
                value=$2
                gsub(/^[ \t]+|[ \t]+$/, "", value)
                print value
                exit
            }
        '
}

set_wifi_backup_metric() {
    # Tidak menunggu atau mengaktifkan WiFi.
    # Hanya mengubah metric profile yang sudah ada agar GSM tetap utama.
    while IFS=: read -r connection_name connection_type; do
        if [ "$connection_type" = "802-11-wireless" ] &&
           [ -n "$connection_name" ]; then

            nmcli connection modify "$connection_name" \
                ipv4.route-metric "$WIFI_METRIC" \
                ipv6.route-metric "$WIFI_METRIC" \
                connection.autoconnect-priority 0 \
                2>/dev/null || true

            log "WiFi profile diset sebagai backup: $connection_name"
        fi
    done < <(
        nmcli -t -f NAME,TYPE connection show 2>/dev/null
    )
}

log "============================================================"
log "EFWS IoT GSM connection start"
log "APN: $APN"

# Hanya memastikan service lokal berjalan.
# Tidak memerlukan koneksi internet.
systemctl is-active --quiet ModemManager ||
    systemctl start ModemManager

systemctl is-active --quiet NetworkManager ||
    systemctl start NetworkManager

# Nyalakan radio WWAN.
nmcli radio wwan on 2>/dev/null || true

# Jangan gunakan PPP bersamaan dengan QMI/ModemManager.
poff -a 2>/dev/null || true
pkill -9 pppd 2>/dev/null || true

# Menunggu SIM7600 muncul di ModemManager.
MODEM_ID=""

for attempt in $(seq 1 "$MODEM_WAIT_ATTEMPTS"); do
    MODEM_ID=$(get_modem_id)

    if [ -n "$MODEM_ID" ]; then
        log "Modem ditemukan: Modem/$MODEM_ID"
        break
    fi

    log "Menunggu modem: $attempt/$MODEM_WAIT_ATTEMPTS"
    sleep "$MODEM_WAIT_DELAY"
done

if [ -z "$MODEM_ID" ]; then
    log "Modem tidak ditemukan. Keluar tanpa menahan proses lain."
    exit 0
fi

# Enable modem, abaikan jika modem sudah enabled.
mmcli -m "$MODEM_ID" --enable >>"$LOG_FILE" 2>&1 || true
sleep 2

# Jika bearer aktif sudah tersedia, pakai bearer tersebut.
BEARER_ID=$(get_bearer_id "$MODEM_ID")

if [ -n "$BEARER_ID" ]; then
    EXISTING_BEARER=$(mmcli -b "$BEARER_ID" 2>/dev/null || true)

    if ! echo "$EXISTING_BEARER" |
        grep -q "connected: yes"; then

        BEARER_ID=""
    fi
fi

# Kalau belum ada bearer aktif, buat koneksi baru.
if [ -z "$BEARER_ID" ]; then
    log "Belum ada bearer aktif. Menghubungkan APN $APN."

    CONNECTED=0

    for attempt in $(seq 1 "$CONNECT_ATTEMPTS"); do
        log "Percobaan koneksi: $attempt/$CONNECT_ATTEMPTS"

        if mmcli -m "$MODEM_ID" \
            --simple-connect="apn=${APN},ip-type=ipv4" \
            >>"$LOG_FILE" 2>&1; then

            CONNECTED=1
            break
        fi

        sleep "$CONNECT_RETRY_DELAY"
    done

    if [ "$CONNECTED" -ne 1 ]; then
        log "Gagal membuat bearer. Keluar tanpa menahan proses lain."
        exit 0
    fi

    sleep 2
    BEARER_ID=$(get_bearer_id "$MODEM_ID")
fi

if [ -z "$BEARER_ID" ]; then
    log "Bearer tidak ditemukan setelah proses connect."
    exit 0
fi

log "Bearer ditemukan: Bearer/$BEARER_ID"

BEARER_OUTPUT=$(mmcli -b "$BEARER_ID" 2>/dev/null || true)
echo "$BEARER_OUTPUT" >>"$LOG_FILE"

CONNECTED=$(get_bearer_field "$BEARER_OUTPUT" "connected")
INTERFACE=$(get_bearer_field "$BEARER_OUTPUT" "interface")
IP_ADDRESS=$(get_bearer_field "$BEARER_OUTPUT" "address")
PREFIX=$(get_bearer_field "$BEARER_OUTPUT" "prefix")
GATEWAY=$(get_bearer_field "$BEARER_OUTPUT" "gateway")
MTU=$(get_bearer_field "$BEARER_OUTPUT" "mtu")

INTERFACE="${INTERFACE:-$WWAN_INTERFACE}"
MTU="${MTU:-1500}"

if [ "$CONNECTED" != "yes" ]; then
    log "Bearer belum connected."
    exit 0
fi

if [ -z "$IP_ADDRESS" ] ||
   [ -z "$PREFIX" ] ||
   [ -z "$GATEWAY" ]; then

    log "Data IPv4 bearer tidak lengkap."
    log "IP=$IP_ADDRESS Prefix=$PREFIX Gateway=$GATEWAY"
    exit 0
fi

log "Interface : $INTERFACE"
log "IP        : $IP_ADDRESS/$PREFIX"
log "Gateway   : $GATEWAY"
log "MTU       : $MTU"

# Konfigurasi interface lokal.
# Tidak membutuhkan akses internet.
ip link set "$INTERFACE" up
ip link set dev "$INTERFACE" mtu "$MTU"

ip addr flush dev "$INTERFACE"
ip addr add "${IP_ADDRESS}/${PREFIX}" dev "$INTERFACE"

# Pastikan gateway dianggap reachable melalui interface point-to-point.
ip route replace "$GATEWAY" \
    dev "$INTERFACE" \
    src "$IP_ADDRESS"

# Jadikan SIM IoT sebagai default route utama.
ip route replace default \
    via "$GATEWAY" \
    dev "$INTERFACE" \
    src "$IP_ADDRESS" \
    metric "$GSM_METRIC" \
    onlink

# WiFi tidak diaktifkan atau ditunggu.
# Hanya diberi metric lebih besar jika profile-nya ada.
set_wifi_backup_metric

ip route flush cache

log "Default route yang terpasang:"
ip route show default |
    tee -a "$LOG_FILE"

if ip route show default |
    grep -q "dev ${INTERFACE}"; then

    log "BERHASIL: SIM IoT menjadi koneksi utama."
else
    log "PERINGATAN: default route wwan0 belum ditemukan."
fi

log "EFWS IoT GSM connection selesai."
exit 0
