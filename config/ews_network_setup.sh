#!/bin/bash

set -e

CONNECTION_NAME="EWS-4G"
MODEM_METRIC=50
WIFI_METRIC=600
DEFAULT_APN="internet"

echo "======================================"
echo " EWS Network Setup - 4G Main + WiFi Backup"
echo " Tanpa install package"
echo "======================================"

if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] Jalankan dengan sudo:"
  echo "sudo bash ~/ews_network_setup.sh"
  exit 1
fi

echo "[1/7] Cek service ModemManager dan NetworkManager..."

if ! systemctl is-active --quiet ModemManager; then
  echo "[WARN] ModemManager belum aktif. Mengaktifkan..."
  systemctl enable --now ModemManager
fi

if ! systemctl is-active --quiet NetworkManager; then
  echo "[WARN] NetworkManager belum aktif. Mengaktifkan..."
  systemctl enable --now NetworkManager
fi

echo "[OK] Service aktif."

sleep 3

echo "[2/7] Deteksi modem..."

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n 1 || true)

if [ -z "$MODEM_ID" ]; then
  echo "[WARN] Modem belum terdeteksi oleh ModemManager."
  echo "[WARN] Script tetap lanjut membuat profile 4G."
  echo "[WARN] Kalau nanti modem dipasang, NetworkManager akan coba auto-connect."
  OPERATOR_CODE=""
else
  echo "[OK] Modem ditemukan: Modem/$MODEM_ID"

  echo "[INFO] Enable modem..."
  mmcli -m "$MODEM_ID" --enable || true

  sleep 3

  OPERATOR_CODE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.operator-code" | cut -d: -f2 | tr -d ' ' || true)

  echo "[INFO] Operator code: ${OPERATOR_CODE:-unknown}"
fi

echo "[3/7] Tentukan APN berdasarkan provider..."

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
    PROVIDER="Unknown / Default"
    APN="$DEFAULT_APN"
    ;;
esac

echo "[INFO] Provider : $PROVIDER"
echo "[INFO] APN      : $APN"

echo "[4/7] Buat atau update koneksi 4G..."

if nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
  echo "[INFO] Profile $CONNECTION_NAME sudah ada. Update setting..."
else
  echo "[INFO] Membuat profile $CONNECTION_NAME..."
  nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$APN"
fi

nmcli connection modify "$CONNECTION_NAME" \
  gsm.apn "$APN" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric "$MODEM_METRIC" \
  ipv6.method ignore

echo "[5/7] Set semua koneksi WiFi sebagai backup..."

WIFI_CONNECTIONS=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 || true)

if [ -z "$WIFI_CONNECTIONS" ]; then
  echo "[WARN] Tidak ada profile WiFi ditemukan."
else
  echo "$WIFI_CONNECTIONS" | while read -r WIFI_NAME; do
    if [ -n "$WIFI_NAME" ]; then
      echo "[INFO] Set WiFi backup: $WIFI_NAME"
      nmcli connection modify "$WIFI_NAME" \
        connection.autoconnect yes \
        connection.autoconnect-priority 0 \
        ipv4.route-metric "$WIFI_METRIC" \
        ipv6.route-metric "$WIFI_METRIC" || true
    fi
  done
fi

echo "[6/7] Aktifkan koneksi 4G..."

nmcli connection down "$CONNECTION_NAME" >/dev/null 2>&1 || true
sleep 2
nmcli connection up "$CONNECTION_NAME" || true

echo "[7/7] Status akhir..."

echo ""
echo "======================================"
echo " MODEM"
echo "======================================"
mmcli -L || true

echo ""
echo "======================================"
echo " DEVICE STATUS"
echo "======================================"
nmcli device status || true

echo ""
echo "======================================"
echo " CONNECTION LIST"
echo "======================================"
nmcli connection show || true

echo ""
echo "======================================"
echo " IP ROUTE"
echo "======================================"
ip route || true

echo ""
echo "======================================"
echo " ROUTE KE INTERNET"
echo "======================================"
ip route get 8.8.8.8 || true

echo ""
echo "======================================"
echo " PING TEST"
echo "======================================"
ping -c 4 8.8.8.8 || true

echo ""
echo "======================================"
echo " SELESAI"
echo "======================================"
echo "Target:"
echo "- Jika modem terpasang dan konek: internet lewat 4G"
echo "- Jika modem dicabut: otomatis fallback ke WiFi"
echo "- Jika modem dipasang lagi: otomatis balik ke 4G"
echo ""
echo "Cek manual:"
echo "ip route get 8.8.8.8"
echo ""
echo "Kalau lewat modem biasanya muncul:"
echo "dev wwan0 / ppp0 / usb0"
echo ""
echo "Kalau lewat WiFi muncul:"
echo "dev wlan0"
