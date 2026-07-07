#!/bin/bash

CONNECTION_NAME="EWS-4G"
DEFAULT_APN="internet"
MODEM_METRIC=50
WIFI_METRIC=600

echo "[EWS-GSM] Starting GSM auto connect..."

systemctl is-active --quiet ModemManager || systemctl start ModemManager
systemctl is-active --quiet NetworkManager || systemctl start NetworkManager

nmcli radio wwan on || true

# Create GSM connection if not exists
if ! nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
    echo "[EWS-GSM] Creating GSM profile..."

    nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$DEFAULT_APN"
fi

# Wait modem
MODEM_ID=""

for i in {1..30}; do

    MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)

    if [ -n "$MODEM_ID" ]; then
        echo "[EWS-GSM] Modem found: $MODEM_ID"
        break
    fi

    echo "[EWS-GSM] Waiting for modem... $i"
    sleep 2

done

APN="$DEFAULT_APN"
PROVIDER="Unknown"

# Detect provider
if [ -n "$MODEM_ID" ]; then

    mmcli -m "$MODEM_ID" --enable || true
    sleep 3

    OPERATOR_CODE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.operator-code" | cut -d= -f2 | tr -d ' ' || true)

    case "$OPERATOR_CODE" in
        "51010")
            PROVIDER="Telkomsel / by.U"
            APN="internet"
            ;;
        "51011")
            PROVIDER="XL / AXIS"
            APN="internet"
            ;;
        "51001")
            PROVIDER="Indosat"
            APN="internet"
            ;;
        "51021")
            PROVIDER="Indosat / IM3"
            APN="internet"
            ;;
        "51089")
            PROVIDER="Tri"
            APN="3data"
            ;;
        *)
            PROVIDER="Default"
            APN="$DEFAULT_APN"
            ;;
    esac
fi

echo "[EWS-GSM] Provider : $PROVIDER"
echo "[EWS-GSM] APN      : $APN"

# Configure GSM connection
nmcli connection modify "$CONNECTION_NAME" \
    gsm.apn "$APN" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    ipv4.method auto \
    ipv4.route-metric "$MODEM_METRIC" \
    ipv6.method ignore

# Configure WiFi as backup
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

# --------------------------------------------------------------------
# Connect GSM
# --------------------------------------------------------------------
echo "[EWS-GSM] Connecting GSM..."

nmcli connection up "$CONNECTION_NAME" || true

echo "[EWS-GSM] Current route:"
ip route get 8.8.8.8 || true

echo "[EWS-GSM] Done."