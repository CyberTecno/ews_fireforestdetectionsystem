# EFWS — Panduan Deployment

Dari NOL sampai EFWS jalan stabil sebagai systemd service di Raspberry Pi.

**Hardware yang dibutuhkan:**
Raspberry Pi 3 Model B+ / 4, MicroSD 32 GB, MCP3008 (SPI ADC), Logic Level Converter 4-ch,
MQ-2, MQ-135, BME280 (I2C), Rainfall Sensor DFRobot SEN0575 (I2C),
2× Soil Moisture Probe, Submersible Pressure Sensor (4-20 mA), Flame Sensor (IR AO),
Voltage Sensor Module DC 0–25 V (baterai), RS485 Anemometer + USB-RS485 Converter,
Wind Direction JL-FSX2 (UART GPIO14/15), **SIM7600 4G HAT** (Waveshare, kartu biasa Telkomsel),
Relay 5 V 1-ch, Siren 12 V.
Sistem catu daya: Solar Panel 100 W, SCC 20 A, LiFePO4 12 V, Buck Converter.

Struktur project **flat** — `main.py` langsung di root, sejajar dengan
`venv/`, `.env`, `scripts/`, `logs/`, `database/`.

**Dua service yang berjalan di Raspberry Pi:**
- `gsm-connect.service` — koneksi 4G + GPS fetch (jalan duluan, sekali saat boot)
- `efws.service` — aplikasi utama EFWS (start setelah gsm-connect selesai)
- `ews-gps-refresh.timer` — refresh GPS setiap 30 menit di background

---

## TAHAP 0 — Wiring fisik

**Baca dulu** [`docs/Pinout.md`](Pinout.md) dan [`docs/PowerSystem.md`](PowerSystem.md)
sebelum menyambungkan apapun. Perhatikan khusus:

- Sinyal analog **5 V** dari MQ-2, MQ-135, dan Soil Probe **wajib** lewat Logic Level Converter
  sebelum masuk MCP3008 (VREF 3.3 V) — tanpa LLC, ADC bisa rusak.
- Battery voltage sensor dan Flame Sensor AO langsung ke MCP3008 **tanpa LLC**
  (sudah native 3.3 V).
- Siren 12 V **wajib** melalui Relay Module — tidak boleh dicatu dari GPIO langsung.
- Wind Direction JL-FSX2 butuh prasyarat kernel (lihat TAHAP 2).
- Sensor pressure 4-20 mA butuh PSU 12 V terpisah untuk loop-nya dan burden resistor 100 Ω.
- SIM7600 HAT: pasang via USB data ke Raspberry Pi, antena LTE dan antena GNSS **keduanya harus** terpasang.

Setelah wiring terpasang: **jangan langsung jalankan kode** — lanjut ke TAHAP 2 dulu.

---

## TAHAP 1 — Pindahkan project ke Raspberry Pi

```bash
# Dari laptop/PC:
scp -r ews_1 uwfadmin@<ip-raspberry-pi>:/home/uwfadmin/ews

# SSH masuk:
ssh uwfadmin@<ip-raspberry-pi>
cd /home/uwfadmin/ews
```

> Sesuaikan username `uwfadmin` dan nama folder tujuan dengan setup Anda.
> Path ini harus konsisten dengan `WorkingDirectory=` dan `ExecStart=` di semua `.service` file.

---

## TAHAP 2 — Persiapan OS (sekali saja)

### 2a. Install dependensi sistem

```bash
sudo apt update && sudo apt install -y \
    python3-venv python3-pip \
    i2c-tools \
    usb-modeswitch modemmanager \
    network-manager \
    git awk
```

> `network-manager` dan `modemmanager` **wajib** untuk koneksi SIM7600 via nmcli.

### 2b. Aktifkan service ModemManager dan NetworkManager

```bash
sudo systemctl enable --now ModemManager
sudo systemctl enable --now NetworkManager
```

Cek status modem setelah SIM7600 dicolok:

```bash
mmcli -L
# Harus muncul: /org/freedesktop/ModemManager1/Modem/0 [QUALCOMM] SIMCOM_SIM7600...
```

### 2c. Aktifkan interface hardware

```bash
sudo raspi-config
# Interface Options → SPI       → Yes   (MCP3008)
# Interface Options → I2C       → Yes   (BME280, Rainfall SEN0575)
# Interface Options → Serial Port:
#   "login shell over serial" → No
#   "serial port hardware"    → Yes     (Wind Direction UART)

sudo reboot
```

### 2d. Aktifkan UART penuh untuk Wind Direction (JL-FSX2)

Wind Direction Sensor memakai GPIO14/GPIO15 (UART). Di RPi secara default,
GPIO14/15 terhubung ke **mini-UART** yang clock-nya tidak stabil.
Bluetooth juga menempati PL011 UART penuh.

```bash
# Tambahkan ke /boot/config.txt (atau /boot/firmware/config.txt di Bookworm):
sudo nano /boot/config.txt
# Tambahkan di akhir:
#   dtoverlay=disable-bt

# Setelah simpan:
sudo systemctl disable hciuart
sudo reboot
```

Setelah reboot, `/dev/serial0` akan terhubung ke **PL011 UART penuh** (baudrate stabil).

### 2e. Tambahkan user ke grup hardware

```bash
# Ganti "uwfadmin" sesuai username yang dipakai:
sudo usermod -aG gpio,spi,i2c,dialout uwfadmin
sudo reboot
```

### 2f. Verifikasi device terdeteksi

```bash
lsusb                    # harus muncul: SIMCom atau Qualcomm (SIM7600)
ls /dev/ttyUSB*          # harus: /dev/ttyUSB0 s/d ttyUSB3 (SIM7600) + ttyUSB4/5 (RS485)
ls /dev/spidev*          # harus: /dev/spidev0.0  (MCP3008)
i2cdetect -y 1           # harus: 0x76 (BME280) DAN 0x1D (Rainfall SEN0575)
ls /dev/serial0          # harus ada (Wind Direction UART)
```

> Port SIM7600 (Waveshare HAT):
> - `ttyUSB0` = DM (diagnostic), `ttyUSB1` = AT secondary, `ttyUSB2` = **AT command** ← dipakai script
> - `ttyUSB3` = PPP/modem (jangan dipakai bersamaan nmcli)
>
> Jika salah satu tidak muncul: berhenti, cek wiring dan `raspi-config` sebelum lanjut.

---

## TAHAP 3 — Setup Python environment

```bash
cd /home/uwfadmin/ews
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

---

## TAHAP 4 — Konfigurasi `.env`

```bash
cp .env.example .env
nano .env
```

### Wajib diisi sebelum menjalankan apapun:

```ini
# Identitas device (unik per unit di lapangan)
EFWS_DEVICE_ID=DEV-JAM-001
EFWS_DEVICE_TOKEN=token_rahasia_dari_backend

# Untuk prototyping awal: buka https://webhook.site, copy URL unik
EFWS_API_URL=https://webhook.site/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EFWS_API_KEY=

# Mode: "mock" dulu untuk test tanpa hardware, "hardware" untuk produksi
EFWS_RUN_MODE=mock

# Koordinat fallback statis (dipakai HANYA jika GPS belum pernah fix sama sekali)
# Saat GPS sudah pernah fix, cache /tmp/ews_gps_cache.json dipakai (bukan ini)
EFWS_LAT=-6.2146
EFWS_LON=106.8208

# APN kartu SIM (Telkomsel = internet, Tri = 3data)
# Jika tidak diisi, ews_network_setup.sh auto-detect dari operator code
EFWS_APN=internet
```

### Env var interval (nilai default sudah sane, ubah hanya jika perlu):

```ini
EFWS_READ_INTERVAL=180              # sensor sampling tiap 3 menit
EFWS_TELEMETRY_INTERVAL_SEC=1800    # kirim telemetry tiap 30 menit (normal)
EFWS_EMERGENCY_TELEMETRY_INTERVAL_SEC=600  # tiap 10 menit saat emergency
EFWS_LOCATION_INTERVAL_SEC=1800     # kirim lokasi tiap 30 menit (selalu tetap)
EFWS_HEARTBEAT_INTERVAL_SEC=300     # heartbeat tiap 5 menit (selalu tetap)
EFWS_CONNECTIVITY_CHECK_SEC=120     # retry offline queue tiap 2 menit
```

### Env var SIM7600 (opsional — default sudah benar untuk Waveshare HAT):

```ini
# EFWS_SIM_PORT=/dev/ttyUSB2    # AT command port SIM7600 (default: ttyUSB2)
# EFWS_SIM_BAUD=115200          # baudrate AT port
# EFWS_GPS_CACHE=/tmp/ews_gps_cache.json  # file cache GPS (dibaca main.py)
```

---

## TAHAP 5 — Setup koneksi 4G (gsm-connect.service)

Ini adalah **langkah paling penting** — tanpa koneksi 4G, data tidak bisa dikirim ke API.

### 5a. Install service dan script

```bash
# Copy service files ke systemd
sudo cp /home/uwfadmin/ews/gsm-connect.service     /etc/systemd/system/
sudo cp /home/uwfadmin/ews/ews-gps-refresh.service /etc/systemd/system/
sudo cp /home/uwfadmin/ews/ews-gps-refresh.timer   /etc/systemd/system/

# Set executable
chmod +x /home/uwfadmin/ews/scripts/ews_network_setup.sh
chmod +x /home/uwfadmin/ews/scripts/gps_refresh.sh
chmod +x /home/uwfadmin/ews/scripts/check_comm.sh

# Reload systemd
sudo systemctl daemon-reload
```

### 5b. Test koneksi 4G manual (sebelum enable service)

```bash
sudo bash /home/uwfadmin/ews/scripts/ews_network_setup.sh
```

Pantau output:
```
[1/8] Cek ModemManager & NetworkManager...
[2/8] Aktifkan WWAN radio...
[3/8] Tunggu modem SIM7600...      ← harus muncul "Modem ditemukan: Modem/0"
[4/8] Tentukan APN...               ← harus muncul Provider: Telkomsel / APN: internet
[5/8] Konfigurasi profil EWS-4G...
[6/8] Set WiFi sebagai backup...
[7/8] Aktifkan koneksi EWS-4G...   ← harus muncul "berhasil aktif!"
[8/8] Verifikasi koneksi...         ← harus muncul IP + interface (wwan0 / cdc-wdm0)
[GPS] Mulai GPS fetch via AT command... (butuh ~5-10 menit)
```

Verifikasi manual setelah script selesai:

```bash
# Cek interface aktif
nmcli device status
# Harus: cdc-wdm0 gsm connected EWS-4G

# Cek default route via modem (bukan WiFi)
ip route get 8.8.8.8
# Harus: dev wwan0 atau cdc-wdm0 (bukan wlan0)

# Cek IP didapat
ip addr show wwan0   # atau cdc-wdm0

# Test internet
ping -c 4 8.8.8.8

# Cek cache GPS (butuh beberapa menit)
cat /tmp/ews_gps_cache.json
# Jika fix: {"fix":true,"lat":-6.xxx,"lon":106.xxx,...}
# Jika belum fix: {"fix":false,...} — normal, tunggu antena GNSS di outdoor
```

### 5c. Jika route masih via WiFi (troubleshoot metric)

```bash
# Cek metric yang terpasang
ip route show

# Paksa metric 4G lebih kecil dari WiFi
sudo nmcli connection modify "EWS-4G" ipv4.route-metric 50
sudo nmcli connection modify "NAMA_WIFI_ANDA" ipv4.route-metric 600
sudo nmcli connection up "EWS-4G"
```

### 5d. Enable service agar auto-start saat boot

```bash
sudo systemctl enable gsm-connect.service
sudo systemctl enable ews-gps-refresh.timer
```

### 5e. Verifikasi diagnostik lengkap

```bash
sudo bash /home/uwfadmin/ews/scripts/check_comm.sh
```

Semua baris harus `[OK]` atau `[WARN]` (bukan `[FAIL]`).

---

## TAHAP 6 — Test koneksi API (mode mock)

```bash
source venv/bin/activate
python3 tests/test_webhook_api.py
```

Buka halaman webhook.site — satu POST JSON harus muncul live. Jika berhasil:
jalur Pi → 4G → internet → API terbukti jalan.

> Belum ada koneksi internet? Jalankan `tools/mock_api_server.py` di laptop (satu
> jaringan Wi-Fi dengan Pi), lalu set `EFWS_API_URL=http://<ip-laptop>:5000`.

---

## TAHAP 7 — Test tiap sensor (URUTAN PENTING, mode hardware)

Ubah dulu di `.env`:
```ini
EFWS_RUN_MODE=hardware
```

Jalankan **berurutan** — kalau satu gagal, selesaikan dulu sebelum lanjut:

```bash
source venv/bin/activate

# 1. MCP3008 — fondasi semua sensor analog
python3 tests/test_mcp3008.py

# 2. MQ-2 & MQ-135 (analog via MCP3008 + LLC)
python3 tests/test_gas_sensors.py

# 3. BME280 (I2C)
python3 tests/test_bme280.py

# 4. Rainfall Sensor SEN0575 (I2C)
python3 tests/test_rainfall.py

# 5. Soil Moisture × 2 (analog via MCP3008 + LLC)
python3 tests/test_soil.py

# 6. Submersible Pressure Sensor (4-20mA via burden resistor → MCP3008)
python3 tests/test_pressure.py

# 7. Battery Voltage Sensor (analog via MCP3008, native 3.3V)
python3 tests/test_battery.py

# 8. Flame Sensor (AO analog via MCP3008 CH6)
python3 tests/test_flame.py

# 9. Anemometer RS485 (Modbus RTU via USB-RS485)
python3 tests/test_anemometer.py

# 10. Wind Direction JL-FSX2 (UART /dev/serial0)
python3 tests/test_weather.py

# 11. Relay + Sirine (⚠️ SUARA KERAS 120 dB — jauhkan dari telinga)
python3 tests/test_relay_siren.py

# 12. Semua sensor sekaligus (final check sebelum main.py)
python3 tests/test_all_sensors.py

# 13. Integritas offline queue (simulasi jaringan putus)
python3 tests/test_offline_queue_integrity.py
```

> **SIM7600 tidak perlu ditest terpisah** — GPS ditangani penuh oleh `ews_network_setup.sh`
> dan dibaca `main.py` dari file cache. Cek via: `cat /tmp/ews_gps_cache.json`

---

## TAHAP 8 — Jalankan EFWS penuh (foreground dulu)

```bash
source venv/bin/activate
python3 main.py
```

Amati beberapa siklus (default tiap 3 menit). Pastikan:
- Semua sensor terbaca (tidak ada `NullSensor` yang tak terduga)
- Log menampilkan `READ | semua nilai NORMAL` atau threshold yang memang diharapkan
- `[Telemetry Publisher] Normal Scheduled Send` muncul dan webhook.site menerima data
- `[Location Publisher]` muncul dan menampilkan `📍 [GPS] Cache valid — lat=..., lon=...`
  atau `Cache GPS tidak ada / fix=false` (jika GPS belum fix) lalu pakai koordinat config
- `[Heartbeat Publisher]` muncul tiap 5 menit

Tekan `Ctrl+C` untuk berhenti. EFWS shutdown gracefully (sirine dimatikan, koneksi ditutup).

---

## TAHAP 9 — Install semua service (produksi)

### 9a. Copy dan enable semua service

```bash
# Copy service files ke systemd (jika belum dari TAHAP 5)
sudo cp /home/uwfadmin/ews/gsm-connect.service     /etc/systemd/system/
sudo cp /home/uwfadmin/ews/ews-gps-refresh.service /etc/systemd/system/
sudo cp /home/uwfadmin/ews/ews-gps-refresh.timer   /etc/systemd/system/
sudo cp /home/uwfadmin/ews/efws.service             /etc/systemd/system/

sudo systemctl daemon-reload

# Enable semua (auto-start saat boot)
sudo systemctl enable gsm-connect.service
sudo systemctl enable ews-gps-refresh.timer
sudo systemctl enable efws.service
```

### 9b. Start untuk pertama kali (urutan penting)

```bash
# 1. Jalankan network setup dulu
sudo systemctl start gsm-connect
# Tunggu sampai selesai (oneshot — bisa butuh 5-15 menit untuk GPS)
sudo systemctl status gsm-connect   # harus: active (exited)

# 2. Start GPS timer
sudo systemctl start ews-gps-refresh.timer

# 3. Start EFWS
sudo systemctl start efws
```

> Setelah ini, saat Raspberry Pi **reboot**, `gsm-connect` otomatis jalan duluan,
> `efws` menunggu `gsm-connect` selesai, baru kemudian start.
> Ini dijamin oleh `After=gsm-connect.service` dan `Requires=gsm-connect.service`
> di `efws.service`.

### 9c. Operasi sehari-hari

```bash
# ── Status ───────────────────────────────────────────────────────────
sudo systemctl status efws            # status EFWS utama
sudo systemctl status gsm-connect    # status network setup
systemctl list-timers ews-gps*       # status timer GPS refresh

# ── Log real-time ────────────────────────────────────────────────────
sudo journalctl -u efws -f            # log EFWS (Ctrl+C hanya stop pantau, service tetap jalan)
sudo journalctl -u ews-gsm -f         # log network setup
sudo journalctl -u ews-gps -f         # log GPS refresh
tail -f /home/uwfadmin/ews/logs/network_setup.log  # log network (lebih detail)
tail -f /home/uwfadmin/ews/logs/gps_refresh.log    # log GPS refresh
tail -f /home/uwfadmin/ews/logs/efws.log           # log EFWS (timestamp ms)

# ── Restart (WAJIB setelah update kode atau edit .env) ───────────────
sudo systemctl restart efws

# ── GPS manual check ─────────────────────────────────────────────────
cat /tmp/ews_gps_cache.json           # lihat posisi GPS terakhir
sudo bash /home/uwfadmin/ews/scripts/gps_refresh.sh  # paksa refresh GPS
sudo journalctl -u ews-gps -n 30      # lihat log GPS refresh terakhir

# ── Diagnostik koneksi lengkap ────────────────────────────────────────
sudo bash /home/uwfadmin/ews/scripts/check_comm.sh
```

### 9d. Script helper (alternatif untuk development)

```bash
chmod +x scripts/efws_ctl.sh
./scripts/efws_ctl.sh start     # jalankan di background
./scripts/efws_ctl.sh status    # cek + CPU/RAM
./scripts/efws_ctl.sh logs      # tail log real-time
./scripts/efws_ctl.sh restart   # restart (tiap kali update kode)
./scripts/efws_ctl.sh stop      # berhenti
```

---

## TAHAP 10 — Setup izin Reboot command

Backend dapat mengirim command `Reboot` via response heartbeat. EFWS
mengeksekusinya dengan `sudo systemctl restart efws.service` dari proses child.
Agar ini bisa jalan **tanpa password sudo**, tambahkan sudoers rule:

```bash
sudo visudo -f /etc/sudoers.d/efws
```

Isi file:
```
uwfadmin ALL=(root) NOPASSWD: /usr/bin/systemctl restart efws.service
```

> Tanpa baris ini, command `Reboot` dari backend akan selalu gagal dengan status `FAILED`.

---

## TAHAP 11 — Pindah ke API produksi

Setelah prototyping dengan webhook.site selesai dan backend asli siap:

```bash
nano .env
# EFWS_API_URL=https://api-anda.com/v1
# EFWS_API_KEY=token_rahasia_dari_backend

sudo systemctl restart efws
```

Verifikasi di log bahwa `[Telemetry Publisher]` mengirim ke URL baru dan
`⚙️ Threshold remote diperbarui dari backend:` muncul jika backend mengembalikan `config`.

---

## Troubleshooting

### Koneksi 4G

| Gejala | Kemungkinan Penyebab | Solusi |
|--------|----------------------|--------|
| `mmcli -L` → `No modems were found` | SIM7600 tidak terdeteksi USB | `lsusb` + `ls /dev/ttyUSB*`; cek kabel USB data; tekan tombol PWRKEY modem; ganti port USB |
| `cdc-wdm0 gsm disconnected` | Modem terdeteksi tapi koneksi belum aktif | `sudo nmcli connection up EWS-4G` atau `sudo systemctl restart gsm-connect` |
| Route masih via `wlan0` (WiFi) | Metric route tidak benar | `ip route show` → pastikan EWS-4G metric 50, WiFi metric 600; jalankan `sudo nmcli connection up EWS-4G` |
| `gsm-connect` status `failed` | Script error | `journalctl -u ews-gsm -n 50`; cek `tail -f logs/network_setup.log` |
| Tidak ada IP di `wwan0` | APN salah atau modem belum registrasi | Cek operator code: `mmcli -m 0 \| grep operator-code`; sesuaikan APN di `.env` |

### GPS

| Gejala | Kemungkinan Penyebab | Solusi |
|--------|----------------------|--------|
| `fix=false` di cache JSON | Antena GNSS belum terpasang / di dalam ruangan | Pastikan antena GNSS (bukan antena LTE) terpasang dan ada langit terbuka; cold fix butuh 2-5 menit |
| `/tmp/ews_gps_cache.json` tidak ada | Script belum jalan / port AT error | `sudo bash scripts/gps_refresh.sh` + `journalctl -u ews-gps -n 30` |
| `port_busy` di cache | Port ttyUSB2 dipakai proses lain | `fuser /dev/ttyUSB2`; kill prosesnya; jalankan ulang gps_refresh |
| `port_not_found` | SIM7600 tidak mount sebagai ttyUSB2 | `ls /dev/ttyUSB*`; ubah `EFWS_SIM_PORT=/dev/ttyUSBx` di `.env` |
| Lokasi di EFWS selalu dari config (lat=..env..) | Cache GPS tidak ada / fix=false | Tunggu GPS warm-up atau cek antena GNSS |

### Sensor

| Komponen | Gejala | Kemungkinan Penyebab |
|----------|--------|----------------------|
| MCP3008 | `test_mcp3008.py` error | SPI belum aktif (`raspi-config`); wiring CLK/MISO/MOSI/CS salah; `spidev` belum terinstall |
| MQ-2/MQ-135 | Nilai clipping / selalu max | Tidak ada Logic Level Converter di jalur analog 5V |
| MQ-2/MQ-135 | ppm tidak masuk akal | Sensor butuh preheat 24–48 jam untuk akurasi penuh |
| BME280 | `i2cdetect -y 1` kosong | I2C belum aktif; SDA/SCL terbalik; coba `EFWS_BME280_ADDR=0x77` |
| Rainfall SEN0575 | `RuntimeError: PID/VID tidak cocok` | Sensor tidak terpasang / alamat I2C salah (`0x1D`); I2C belum aktif |
| Soil Probe | `moisture_percent` selalu 0% atau 100% | Perlu kalibrasi `dry_raw`/`wet_raw` di `sensors/soil.py` |
| Flame Sensor | `flame_detected` selalu True/False | Threshold `EFWS_FLAME_AO_THRESHOLD_V` belum dikalibrasi; lihat `python sensors/flame.py` |
| Pressure Sensor | `fault_open_loop=True`, `current_ma≈0` | Loop 4-20 mA putus; PSU 12 V loop belum nyala; burden resistor belum terpasang |
| Battery Sensor | `voltage`/`percent` salah | `EFWS_BATTERY_SENSOR_MAX_V` (default 16.5 V) atau `EFWS_BATTERY_MAX_V`/`MIN_V` perlu disesuaikan |
| Anemometer RS485 | Exception saat baca | Slave ID / register Modbus salah; wiring A/B terbalik; `EFWS_ANEM_PORT` salah |
| Wind Direction | Data acak / tidak ada | `disable-bt` belum di-set; console serial login masih aktif; wiring TX/RX terbalik |
| Relay | Klik tapi sirine tidak bunyi | Sumber 12 V sirine belum tersambung; wiring COM/NO salah |
| Relay | Tidak klik | GPIO pin di `.env` tidak sesuai wiring fisik; cek `EFWS_GPIO_RELAY` |

### Sistem & Service

| Gejala | Kemungkinan Penyebab | Solusi |
|--------|----------------------|--------|
| API kirim gagal terus | Tidak ada internet | `ping 8.8.8.8`; cek route (`ip route get 8.8.8.8`); pastikan EWS-4G aktif |
| `efws` status `failed` | Module Python hilang / `.env` tidak terbaca | `journalctl -u efws -n 50`; aktifkan venv + cek `requirements.txt` |
| Reboot command `FAILED` | Sudoers rule belum ditambahkan | Lihat TAHAP 10 |
| SQLite terus membesar | Retention loop bermasalah | Cek log `🧹 Retention:`; pastikan `EFWS_DB_RETENTION_DAYS=3` |

---

## Cek Kondisi Sistem — Perintah Berguna

```bash
# ── Jaringan ─────────────────────────────────────────────────────────
nmcli device status                   # status semua interface
ip route get 8.8.8.8                  # cek route ke internet (harus via wwan0/cdc-wdm0)
mmcli -L                              # daftar modem yang terdeteksi
mmcli -m 0                            # detail modem (signal, state, operator)
sudo bash scripts/check_comm.sh       # diagnostik lengkap (modem + koneksi + GPS + API)

# ── GPS ──────────────────────────────────────────────────────────────
cat /tmp/ews_gps_cache.json           # cache GPS (ditulis oleh ews_network_setup / gps_refresh)
sudo bash scripts/gps_refresh.sh      # paksa refresh GPS sekarang
systemctl list-timers ews-gps*        # cek timer GPS refresh (kapan terakhir/berikutnya jalan)
journalctl -u ews-gps -n 40          # log GPS refresh terakhir

# ── EFWS ─────────────────────────────────────────────────────────────
sudo journalctl -u efws -f            # log real-time
sudo journalctl -u efws -n 100 --no-pager  # 100 baris terakhir
tail -f logs/efws.log                 # log file (timestamp ms, lebih detail)

# ── Database lokal ───────────────────────────────────────────────────
python3 -c "
from database.db_manager import DBManager
import json
db = DBManager()
print('Pending queue:', db.count_pending_queue(), 'item')
for r in db.recent_readings(5): print(r)
db.close()
"

# ── Tools tambahan ───────────────────────────────────────────────────
python3 tools/modbus_register_scan.py   # scan register Modbus anemometer
```
