# README — Setup SIM7600E sebagai Koneksi Utama Raspberry Pi

> **Cakupan dokumen ini:** hanya modem **SIM7600E-H**. EFWS juga mendukung **A7670E**
> sebagai alternatif (`sim_detector.py` auto-detect salah satu yang terpasang), tapi
> langkah setup A7670E-nya belum didokumentasikan secara terpisah di sini — kalau
> dibutuhkan, minta dibuatkan dokumen sendiri.
>
> **Soal penamaan "A7670E" vs "SIM7670E":** ini modul YANG SAMA, bukan dua modul
> berbeda. Sebagian unit A7670E melaporkan dirinya sebagai "SIM7670E" saat ditanya
> `ATI` (Product Identification), tergantung firmware — makanya kode dan beberapa
> dokumen menyebut "A7670E/SIM7670E" berdampingan. `sim_detector.py` sudah menangani
> kedua varian penamaan ini dengan benar (sudah diuji lewat simulasi terpisah).

Dokumen ini berisi tutorial setup **SIM7600E-H 4G LTE modem** pada **Raspberry Pi 4** agar menjadi koneksi internet utama, sedangkan **WiFi menjadi koneksi backup**.

Target akhir:

```text
SIM7600E 4G = koneksi utama
WiFi        = koneksi cadangan / fallback otomatis
```

Jika modem SIM7600E dilepas, Raspberry Pi otomatis kembali memakai WiFi. Jika modem dipasang lagi, Raspberry Pi akan mencoba kembali memakai koneksi 4G.

---

## 1. Hardware yang digunakan

- Raspberry Pi 4
- SIM7600E-H 4G HAT / USB modem
- SIM card aktif
- Antena LTE
- Kabel USB data
- Power supply Raspberry Pi yang stabil
- Koneksi WiFi sebagai backup

> Catatan penting: modem 4G harus tersambung ke Raspberry Pi melalui **USB data**. GPIO saja biasanya tidak cukup agar modem muncul sebagai device internet.

---

## 2. Cek power Raspberry Pi

Sebelum setup modem, cek apakah Raspberry Pi mengalami undervoltage:

```bash
vcgencmd get_throttled
```

Target ideal:

```text
throttled=0x0
```

Jika muncul:

```text
throttled=0x50000
```

artinya Raspberry Pi pernah mengalami undervoltage sejak boot. Gunakan power supply yang lebih stabil, minimal:

```text
5V 3A berkualitas
lebih aman 5V 4A–5A jika modem ikut dipakai
```

Modem 4G bisa menarik arus cukup besar saat mencari jaringan.

---

## 3. Cek modem terdeteksi oleh USB

Colok modem SIM7600E ke port USB Raspberry Pi, lalu jalankan:

```bash
lsusb
```

Targetnya muncul device seperti:

```text
ID 1e0e:9001 Qualcomm / Option SimTech
```

atau terdapat nama:

```text
SIMCom
Qualcomm
```

Lalu cek port serial:

```bash
ls /dev/ttyUSB*
```

Target:

```text
/dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB4
```

Jika belum muncul, coba:

```text
1. Ganti kabel USB, pastikan kabel data
2. Tekan tombol PWRKEY / POWER modem 2–3 detik
3. Pindah port USB
4. Gunakan power supply yang lebih kuat
5. Coba powered USB hub
```

Untuk melihat log saat modem dicolok:

```bash
sudo dmesg -wH
```

Lalu cabut-colok modem dan lihat apakah muncul log `new USB device`, `SIMCom`, atau `ttyUSB`.

Keluar dari log:

```text
CTRL + C
```

---

## 4. Install NetworkManager dan ModemManager

Install manual:

```bash
sudo apt update
sudo apt install -y modemmanager network-manager
```

Aktifkan service:

```bash
sudo systemctl enable --now ModemManager
sudo systemctl enable --now NetworkManager
```

Restart service:

```bash
sudo systemctl restart ModemManager
sudo systemctl restart NetworkManager
```

Reboot agar bersih:

```bash
sudo reboot
```

---

## 5. Cek ModemManager mendeteksi modem

Setelah Raspberry Pi nyala lagi:

```bash
mmcli -L
```

Contoh hasil yang benar:

```text
/org/freedesktop/ModemManager1/Modem/0 [QUALCOMM INCORPORATED] SIMCOM_SIM7600E-H
```

Cek status device NetworkManager:

```bash
nmcli device status
```

Contoh:

```text
DEVICE         TYPE      STATE         CONNECTION
wlan0          wifi      connected     netplan-wlan0-Uwaterloo
cdc-wdm0       gsm       disconnected  --
eth0           ethernet  unavailable   --
```

Jika `cdc-wdm0` muncul sebagai `gsm`, artinya modem siap dibuatkan koneksi.

---

## 6. Jangan pakai AT manual saat memakai NetworkManager

Jika sebelumnya memakai Minicom dan menjalankan:

```text
AT+NETOPEN
AT+CGACT
AT+HTTPINIT
```

sebaiknya hentikan dulu penggunaan AT manual untuk koneksi internet.

NetworkManager + ModemManager akan mengatur koneksi modem secara otomatis.

Kalau masih ada Minicom terbuka:

```text
CTRL + A
X
Yes
```

Atau matikan dari terminal:

```bash
sudo killall minicom 2>/dev/null
sudo killall picocom 2>/dev/null
```

---

## 7. Buat koneksi 4G manual

Untuk APN, banyak provider Indonesia bisa memakai:

```text
internet
```

Termasuk AXIS/XL, Telkomsel/by.U, dan beberapa Indosat.

Buat koneksi:

```bash
sudo nmcli connection add type gsm ifname cdc-wdm0 con-name "EWS-4G" apn "internet"
```

Jika profile sudah ada, cukup update:

```bash
sudo nmcli connection modify "EWS-4G" gsm.apn "internet"
```

Set 4G sebagai koneksi utama:

```bash
sudo nmcli connection modify "EWS-4G" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric 50 \
  ipv6.method ignore
```

Aktifkan koneksi 4G:

```bash
sudo nmcli connection up "EWS-4G"
```

---

## 8. Jadikan WiFi sebagai backup

Lihat nama koneksi WiFi:

```bash
nmcli connection show
```

Contoh nama WiFi:

```text
netplan-wlan0-Uwaterloo
```

Set WiFi sebagai backup dengan route metric lebih besar:

```bash
sudo nmcli connection modify "netplan-wlan0-Uwaterloo" \
  connection.autoconnect yes \
  connection.autoconnect-priority 0 \
  ipv4.route-metric 600 \
  ipv6.route-metric 600
```

> Ganti `netplan-wlan0-Uwaterloo` sesuai nama WiFi yang muncul di Raspberry Pi kamu.

---

## 9. Cek koneksi utama sudah lewat modem

Jalankan:

```bash
nmcli device status
```

Target:

```text
cdc-wdm0       gsm       connected      EWS-4G
wlan0          wifi      connected      netplan-wlan0-Uwaterloo
```

Cek route internet:

```bash
ip route get 8.8.8.8
```

Jika 4G sudah menjadi utama, hasilnya biasanya menunjukkan interface modem, misalnya:

```text
dev wwan0
```

atau interface sejenis dari modem.

Jika masih menunjukkan:

```text
dev wlan0
```

berarti WiFi masih menjadi jalur utama dan route metric perlu dicek ulang.

Tes ping:

```bash
ping -c 4 8.8.8.8
```

---

## 10. Script otomatis setup koneksi 4G utama + WiFi backup

Script ini **tidak menginstall package**. Install `network-manager` dan `modemmanager` harus dilakukan manual seperti bagian sebelumnya.

Buat file:

```bash
nano ~/ews_network_setup.sh
```

Isi:

```bash
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
```

Simpan:

```text
CTRL + O
ENTER
CTRL + X
```

Jadikan executable:

```bash
chmod +x ~/ews_network_setup.sh
```

Jalankan:

```bash
sudo bash ~/ews_network_setup.sh
```

---

## 11. Test fallback otomatis

### Saat modem terpasang

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wwan0
```

atau interface modem sejenis.

### Cabut modem

Tunggu 30–60 detik, lalu:

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wlan0
```

### Pasang modem lagi

Tunggu 60 detik, lalu:

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wwan0
```

---

## 12. Test kecepatan koneksi modem

Install speedtest:

```bash
sudo apt update
sudo apt install -y speedtest-cli
```

Jalankan:

```bash
speedtest-cli --simple
```

Cek dulu route agar speedtest benar-benar lewat modem:

```bash
ip route get 8.8.8.8
```

Jika masih lewat WiFi, jangan anggap hasil speedtest sebagai hasil SIM7600E.

---

## 13. Remote SSH jarak jauh

Untuk akses SSH jarak jauh melalui jaringan 4G, disarankan memakai **Tailscale** karena koneksi seluler biasanya berada di balik CGNAT.

Install Tailscale di Raspberry Pi:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Cek IP Tailscale Raspberry Pi:

```bash
tailscale ip -4
```

SSH dari laptop:

```bash
ssh uwfadmin@IP_TAILSCALE_RASPBERRY_PI
```

Contoh:

```bash
ssh uwfadmin@100.77.65.15
```

---

## 14. Troubleshooting

### A. `mmcli -L` menampilkan `No modems were found`

Cek:

```bash
lsusb
ls /dev/ttyUSB*
```

Jika modem tidak muncul di `lsusb`, masalahnya di hardware:

```text
1. Kabel USB bukan kabel data
2. Modem belum ON / PWRKEY belum ditekan
3. Power kurang
4. Port USB bermasalah
5. Modem hanya terhubung ke GPIO, bukan USB
```

### B. `cdc-wdm0 gsm disconnected`

Artinya modem terdeteksi, tapi koneksi belum dibuat/aktif.

Jalankan:

```bash
sudo nmcli connection up "EWS-4G"
```

### C. Route masih lewat WiFi

Cek metric:

```bash
ip route
```

Pastikan metric modem lebih kecil dari WiFi:

```text
4G  metric 50
WiFi metric 600
```

Update lagi:

```bash
sudo nmcli connection modify "EWS-4G" ipv4.route-metric 50
sudo nmcli connection modify "NAMA_WIFI" ipv4.route-metric 600
```

### D. Internet modem tidak jalan

Cek status modem:

```bash
mmcli -m 0
```

Cek device:

```bash
nmcli device status
```

Coba restart service:

```bash
sudo systemctl restart ModemManager
sudo systemctl restart NetworkManager
sudo mmcli -S
sudo nmcli connection up "EWS-4G"
```

---

## 15. Ringkasan command penting

```bash
# Cek power
vcgencmd get_throttled

# Cek USB modem
lsusb
ls /dev/ttyUSB*

# Cek modem
mmcli -L

# Cek device network
nmcli device status

# Buat koneksi 4G
sudo nmcli connection add type gsm ifname cdc-wdm0 con-name "EWS-4G" apn "internet"

# Set 4G utama
sudo nmcli connection modify "EWS-4G" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric 50 \
  ipv6.method ignore

# Set WiFi backup
sudo nmcli connection modify "NAMA_WIFI" \
  connection.autoconnect yes \
  connection.autoconnect-priority 0 \
  ipv4.route-metric 600 \
  ipv6.route-metric 600

# Aktifkan 4G
sudo nmcli connection up "EWS-4G"

# Cek route utama
ip route get 8.8.8.8

# Test internet
ping -c 4 8.8.8.8
```

---

## 16. Struktur koneksi final

```text
Raspberry Pi 4
├── SIM7600E-H 4G modem
│   ├── APN: internet
│   ├── Profile: EWS-4G
│   └── Route metric: 50
│
└── WiFi backup
    ├── Profile: netplan-wlan0-Uwaterloo / nama WiFi lain
    └── Route metric: 600
```

Dengan konfigurasi ini, Raspberry Pi akan memprioritaskan modem 4G untuk internet, sedangkan WiFi tetap tersedia sebagai backup.
