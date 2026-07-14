#!/bin/bash

APN="CMNET"
IFACE="wwan0"
ROUTE_METRIC=50
WIFI_METRIC=600

echo "[EWS-GSM] Starting Telkomsel IoT auto connect..."
echo "[EWS-GSM] APN: $APN"

systemctl start ModemManager || true
systemctl start NetworkManager || true

# Matikan auto-connect NetworkManager untuk profile lama agar tidak bentrok
nmcli connection modify "EWS-4G" connection.autoconnect no 2>/dev/null || true

# Set WiFi sebagai backup metric besar
WIFI_CONNECTIONS=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 || true)
echo "$WIFI_CONNECTIONS" | while read -r WIFI_NAME; do
  if [ -n "$WIFI_NAME" ]; then
    echo "[EWS-GSM] Set WiFi backup: $WIFI_NAME"
    nmcli connection modify "$WIFI_NAME" \
      connection.autoconnect yes \
      connection.autoconnect-priority 0 \
      ipv4.route-metric "$WIFI_METRIC" \
      ipv6.route-metric "$WIFI_METRIC" || true
  fi
done

# Cari modem
MODEM_ID=""
for i in {1..30}; do
  MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n 1 || true)
  if [ -n "$MODEM_ID" ]; then
    echo "[EWS-GSM] Modem found: $MODEM_ID"
    break
  fi
  echo "[EWS-GSM] Waiting for modem... $i"
  sleep 2
done

if [ -z "$MODEM_ID" ]; then
  echo "[EWS-GSM] ERROR: Modem not found"
  exit 1
fi

# Enable modem dan paksa LTE
mmcli -m "$MODEM_ID" --enable || true
sleep 5
mmcli -m "$MODEM_ID" --set-allowed-modes='4g' || true
sleep 5

echo "[EWS-GSM] Modem status:"
mmcli -m "$MODEM_ID" | grep -E "state|access tech|operator|registration|packet|rejection|apn|signal" || true

# Bersihkan koneksi lama
echo "[EWS-GSM] Disconnect previous bearer if any..."
mmcli -m "$MODEM_ID" --simple-disconnect || true
ip link set "$IFACE" down 2>/dev/null || true
ip addr flush dev "$IFACE" 2>/dev/null || true
sleep 3

# Connect modem pakai APN CMNET
echo "[EWS-GSM] Connecting with APN $APN..."
CONNECT_OUTPUT=$(mmcli -m "$MODEM_ID" --simple-connect="apn=$APN,ip-type=ipv4" 2>&1)
CONNECT_STATUS=$?

echo "$CONNECT_OUTPUT"

if [ "$CONNECT_STATUS" -ne 0 ]; then
  echo "[EWS-GSM] ERROR: simple-connect failed"
  exit 1
fi

# Ambil bearer path dari output
BEARER_PATH=$(echo "$CONNECT_OUTPUT" | grep -o '/org/freedesktop/ModemManager1/Bearer/[0-9]*' | head -n 1)
BEARER_ID=$(basename "$BEARER_PATH")

if [ -z "$BEARER_ID" ]; then
  echo "[EWS-GSM] ERROR: Bearer ID not found"
  exit 1
fi

echo "[EWS-GSM] Bearer ID: $BEARER_ID"

# Ambil IP config dari bearer
BEARER_INFO=$(mmcli -b "$BEARER_ID")

echo "$BEARER_INFO"

ADDRESS=$(echo "$BEARER_INFO" | awk -F': ' '/address/ {gsub(/ /,"",$2); print $2; exit}')
PREFIX=$(echo "$BEARER_INFO" | awk -F': ' '/prefix/ {gsub(/ /,"",$2); print $2; exit}')
GATEWAY=$(echo "$BEARER_INFO" | awk -F': ' '/gateway/ {gsub(/ /,"",$2); print $2; exit}')
DNS_RAW=$(echo "$BEARER_INFO" | awk -F': ' '/dns/ {print $2; exit}')
MTU=$(echo "$BEARER_INFO" | awk -F': ' '/mtu/ {gsub(/ /,"",$2); print $2; exit}')

if [ -z "$ADDRESS" ] || [ -z "$PREFIX" ] || [ -z "$GATEWAY" ]; then
  echo "[EWS-GSM] ERROR: Failed to read IP config from bearer"
  exit 1
fi

echo "[EWS-GSM] Address: $ADDRESS/$PREFIX"
echo "[EWS-GSM] Gateway: $GATEWAY"
echo "[EWS-GSM] DNS: $DNS_RAW"
echo "[EWS-GSM] MTU: $MTU"

# Set IP ke wwan0
ip link set "$IFACE" up
ip addr flush dev "$IFACE"
ip addr add "$ADDRESS/$PREFIX" dev "$IFACE"

if [ -n "$MTU" ]; then
  ip link set dev "$IFACE" mtu "$MTU" || true
fi

# Set 4G sebagai default route utama
ip route replace default via "$GATEWAY" dev "$IFACE" metric "$ROUTE_METRIC"

# Set DNS manual
if [ ! -f /etc/resolv.conf.backup.ews ]; then
  cp /etc/resolv.conf /etc/resolv.conf.backup.ews || true
fi

DNS_LIST=$(echo "$DNS_RAW" | tr ',' ' ')

{
  for DNS in $DNS_LIST; do
    echo "nameserver $DNS"
  done
  echo "nameserver 8.8.8.8"
  echo "nameserver 1.1.1.1"
} > /etc/resolv.conf

echo "[EWS-GSM] Current route:"
ip route

echo "[EWS-GSM] Testing internet via $IFACE..."
ping -I "$IFACE" -c 3 8.8.8.8 || true
ping -I "$IFACE" -c 3 google.com || true

echo "[EWS-GSM] Done."
