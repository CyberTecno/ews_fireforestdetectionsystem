#!/bin/bash

# ============================================================
# EFWS — SIM7600 IoT GSM Primary Connection
#
# Fungsi:
# - Mendeteksi modem SIM7600
# - Mengabaikan bearer default-attach seperti APN CMNET
# - Menggunakan bearer APN m2minternet
# - Membuat bearer baru jika belum tersedia
# - Mengambil IP, prefix, gateway, DNS, dan MTU
# - Mengonfigurasi wwan0
# - Menjadikan SIM IoT sebagai koneksi utama
# - Menjadikan WiFi sebagai backup
#
# Tidak melakukan:
# - ping
# - curl
# - DNS lookup
# - apt update/install
# - menunggu network-online.target
# - menunggu WiFi tersambung
# ============================================================

APN="m2minternet"
WWAN_INTERFACE="wwan0"

GSM_METRIC=50
WIFI_METRIC=600

MODEM_WAIT_ATTEMPTS=30
MODEM_WAIT_DELAY=2

CONNECT_ATTEMPTS=5
CONNECT_RETRY_DELAY=5

BEARER_WAIT_ATTEMPTS=15
BEARER_WAIT_DELAY=2

IP_WAIT_ATTEMPTS=15
IP_WAIT_DELAY=2

LOG_DIR="/home/uwfadmin/ews/logs"
LOG_FILE="${LOG_DIR}/iot_gsm_connect.log"

mkdir -p "$LOG_DIR"

# Penting:
# Log dikirim ke stderr agar tidak ikut masuk ke hasil command substitution:
# VARIABLE=$(fungsi)
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" |
        tee -a "$LOG_FILE" >&2
}

get_modem_id() {
    mmcli -L 2>/dev/null |
        grep -oE 'Modem/[0-9]+' |
        head -n 1 |
        cut -d/ -f2
}

get_bearer_paths() {
    local modem_id="$1"

    mmcli -m "$modem_id" 2>/dev/null |
        grep -oE '/org/freedesktop/ModemManager1/Bearer/[0-9]+'
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

find_valid_bearer() {
    local modem_id="$1"

    local bearer_path
    local bearer_id
    local bearer_output

    local bearer_type
    local bearer_apn
    local bearer_connected
    local bearer_interface
    local bearer_ip
    local bearer_prefix
    local bearer_gateway

    while read -r bearer_path; do
        [ -z "$bearer_path" ] && continue

        bearer_id="${bearer_path##*/}"
        bearer_output=$(mmcli -b "$bearer_id" 2>/dev/null || true)

        bearer_type=$(get_bearer_field "$bearer_output" "type")
        bearer_apn=$(get_bearer_field "$bearer_output" "apn")
        bearer_connected=$(get_bearer_field "$bearer_output" "connected")
        bearer_interface=$(get_bearer_field "$bearer_output" "interface")
        bearer_ip=$(get_bearer_field "$bearer_output" "address")
        bearer_prefix=$(get_bearer_field "$bearer_output" "prefix")
        bearer_gateway=$(get_bearer_field "$bearer_output" "gateway")

        log "Memeriksa Bearer/$bearer_id: type=$bearer_type apn=$bearer_apn connected=$bearer_connected"

        if [ "$bearer_type" = "default" ] &&
           [ "$bearer_apn" = "$APN" ] &&
           [ "$bearer_connected" = "yes" ] &&
           [ "$bearer_interface" = "$WWAN_INTERFACE" ] &&
           [ -n "$bearer_ip" ] &&
           [ -n "$bearer_prefix" ] &&
           [ -n "$bearer_gateway" ]; then

            printf '%s\n' "$bearer_id"
            return 0
        fi
    done < <(get_bearer_paths "$modem_id")

    return 1
}

find_apn_bearer() {
    local modem_id="$1"

    local bearer_path
    local bearer_id
    local bearer_output
    local bearer_type
    local bearer_apn

    while read -r bearer_path; do
        [ -z "$bearer_path" ] && continue

        bearer_id="${bearer_path##*/}"
        bearer_output=$(mmcli -b "$bearer_id" 2>/dev/null || true)

        bearer_type=$(get_bearer_field "$bearer_output" "type")
        bearer_apn=$(get_bearer_field "$bearer_output" "apn")

        if [ "$bearer_type" = "default" ] &&
           [ "$bearer_apn" = "$APN" ]; then

            printf '%s\n' "$bearer_id"
            return 0
        fi
    done < <(get_bearer_paths "$modem_id")

    return 1
}

wait_for_valid_bearer() {
    local modem_id="$1"
    local attempt
    local bearer_id

    for attempt in $(seq 1 "$BEARER_WAIT_ATTEMPTS"); do
        bearer_id=$(find_valid_bearer "$modem_id")

        if [ -n "$bearer_id" ]; then
            printf '%s\n' "$bearer_id"
            return 0
        fi

        log "Menunggu bearer valid: $attempt/$BEARER_WAIT_ATTEMPTS"
        sleep "$BEARER_WAIT_DELAY"
    done

    return 1
}

wait_for_bearer_ipv4() {
    local bearer_id="$1"

    local attempt
    local bearer_output
    local connected
    local interface
    local ip_address
    local prefix
    local gateway

    for attempt in $(seq 1 "$IP_WAIT_ATTEMPTS"); do
        bearer_output=$(mmcli -b "$bearer_id" 2>/dev/null || true)

        connected=$(get_bearer_field "$bearer_output" "connected")
        interface=$(get_bearer_field "$bearer_output" "interface")
        ip_address=$(get_bearer_field "$bearer_output" "address")
        prefix=$(get_bearer_field "$bearer_output" "prefix")
        gateway=$(get_bearer_field "$bearer_output" "gateway")

        if [ "$connected" = "yes" ] &&
           [ "$interface" = "$WWAN_INTERFACE" ] &&
           [ -n "$ip_address" ] &&
           [ -n "$prefix" ] &&
           [ -n "$gateway" ]; then

            printf '%s\n' "$bearer_output"
            return 0
        fi

        log "Menunggu konfigurasi IPv4 Bearer/$bearer_id: $attempt/$IP_WAIT_ATTEMPTS"
        sleep "$IP_WAIT_DELAY"
    done

    return 1
}

set_wifi_backup_metric() {
    local connection_name
    local connection_type

    while IFS=: read -r connection_name connection_type; do
        if [ "$connection_type" = "802-11-wireless" ] &&
           [ -n "$connection_name" ]; then

            nmcli connection modify "$connection_name" \
                ipv4.route-metric "$WIFI_METRIC" \
                ipv6.route-metric "$WIFI_METRIC" \
                connection.autoconnect yes \
                connection.autoconnect-priority 0 \
                2>/dev/null || true

            log "WiFi profile diset sebagai backup: $connection_name"
        fi
    done < <(
        nmcli -t -f NAME,TYPE connection show 2>/dev/null
    )
}

configure_dns() {
    local bearer_output="$1"

    local dns_list
    local dns1
    local dns2

    dns_list=$(get_bearer_field "$bearer_output" "dns")

    dns1=$(echo "$dns_list" |
        cut -d',' -f1 |
        xargs)

    dns2=$(echo "$dns_list" |
        cut -d',' -f2 |
        xargs)

    if [ -z "$dns1" ]; then
        log "DNS bearer tidak ditemukan. DNS tidak diubah."
        return 0
    fi

    {
        echo "# DNS dari SIM7600 APN $APN"
        echo "nameserver $dns1"

        if [ -n "$dns2" ]; then
            echo "nameserver $dns2"
        fi
    } > /etc/resolv.conf

    log "DNS dipasang: $dns1 ${dns2:-}"
}

configure_wwan_interface() {
    local bearer_output="$1"

    local connected
    local interface
    local ip_address
    local prefix
    local gateway
    local mtu

    connected=$(get_bearer_field "$bearer_output" "connected")
    interface=$(get_bearer_field "$bearer_output" "interface")
    ip_address=$(get_bearer_field "$bearer_output" "address")
    prefix=$(get_bearer_field "$bearer_output" "prefix")
    gateway=$(get_bearer_field "$bearer_output" "gateway")
    mtu=$(get_bearer_field "$bearer_output" "mtu")

    interface="${interface:-$WWAN_INTERFACE}"
    mtu="${mtu:-1500}"

    if [ "$connected" != "yes" ]; then
        log "ERROR: Bearer belum connected."
        return 1
    fi

    if [ -z "$ip_address" ] ||
       [ -z "$prefix" ] ||
       [ -z "$gateway" ]; then

        log "ERROR: Data IPv4 bearer tidak lengkap."
        log "IP=$ip_address Prefix=$prefix Gateway=$gateway"
        return 1
    fi

    log "Interface : $interface"
    log "IP        : $ip_address/$prefix"
    log "Gateway   : $gateway"
    log "MTU       : $mtu"

    ip link set "$interface" up
    ip link set dev "$interface" mtu "$mtu"

    ip addr flush dev "$interface"
    ip addr add "${ip_address}/${prefix}" dev "$interface"

    ip route replace "$gateway" \
        dev "$interface" \
        src "$ip_address"

    ip route replace default \
        via "$gateway" \
        dev "$interface" \
        src "$ip_address" \
        metric "$GSM_METRIC" \
        onlink

    ip route flush cache

    return 0
}

log "============================================================"
log "EFWS IoT GSM connection start"
log "APN: $APN"

# Service lokal saja. Tidak membutuhkan internet.
systemctl is-active --quiet ModemManager ||
    systemctl start ModemManager

systemctl is-active --quiet NetworkManager ||
    systemctl start NetworkManager

# Mengaktifkan radio WWAN.
nmcli radio wwan on 2>/dev/null || true

# Mencegah PPP lama menggunakan modem.
poff -a 2>/dev/null || true
pkill -9 pppd 2>/dev/null || true

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
    log "ERROR: Modem tidak ditemukan."
    exit 1
fi

mmcli -m "$MODEM_ID" --enable \
    >>"$LOG_FILE" 2>&1 || true

sleep 2

BEARER_ID=$(find_valid_bearer "$MODEM_ID")

if [ -n "$BEARER_ID" ]; then
    log "Bearer aktif dan lengkap ditemukan: Bearer/$BEARER_ID"
else
    log "Bearer valid APN $APN belum ditemukan."

    OLD_APN_BEARER=$(find_apn_bearer "$MODEM_ID")

    if [ -n "$OLD_APN_BEARER" ]; then
        log "Bearer/$OLD_APN_BEARER untuk APN $APN tidak valid."

        mmcli -m "$MODEM_ID" --simple-disconnect \
            >>"$LOG_FILE" 2>&1 || true

        sleep 2
    fi

    CONNECTED=0

    for attempt in $(seq 1 "$CONNECT_ATTEMPTS"); do
        log "Percobaan koneksi APN $APN: $attempt/$CONNECT_ATTEMPTS"

        if mmcli -m "$MODEM_ID" \
            --simple-connect="apn=${APN},ip-type=ipv4" \
            >>"$LOG_FILE" 2>&1; then

            CONNECTED=1
            break
        fi

        log "Percobaan koneksi gagal. Menunggu ${CONNECT_RETRY_DELAY} detik."
        sleep "$CONNECT_RETRY_DELAY"
    done

    if [ "$CONNECTED" -ne 1 ]; then
        log "ERROR: Gagal menghubungkan APN $APN."
        exit 1
    fi

    BEARER_ID=$(wait_for_valid_bearer "$MODEM_ID")

    if [ -z "$BEARER_ID" ]; then
        log "ERROR: Bearer valid tidak ditemukan setelah connect."
        exit 1
    fi

    log "Bearer valid muncul setelah connect: Bearer/$BEARER_ID"
fi

BEARER_OUTPUT=$(wait_for_bearer_ipv4 "$BEARER_ID")

if [ -z "$BEARER_OUTPUT" ]; then
    log "ERROR: Bearer/$BEARER_ID tidak memperoleh konfigurasi IPv4."
    exit 1
fi

echo "$BEARER_OUTPUT" >>"$LOG_FILE"

if ! configure_wwan_interface "$BEARER_OUTPUT"; then
    log "ERROR: Gagal mengonfigurasi interface $WWAN_INTERFACE."
    exit 1
fi

set_wifi_backup_metric
configure_dns "$BEARER_OUTPUT"

log "Default route yang terpasang:"
ip route show default |
    tee -a "$LOG_FILE" >&2

if ip route show default |
    grep -qE "default .* dev ${WWAN_INTERFACE} .*metric ${GSM_METRIC}"; then

    log "BERHASIL: SIM IoT menjadi koneksi utama."
else
    log "ERROR: Default route $WWAN_INTERFACE belum terpasang."
    exit 1
fi

log "EFWS IoT GSM connection selesai."
exit 0
