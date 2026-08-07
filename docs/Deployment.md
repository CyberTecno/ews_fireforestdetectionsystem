# EFWS — Panduan Deployment

Dari NOL sampai EFWS jalan stabil sebagai systemd service di Raspberry Pi 4.

**Hardware yang dibutuhkan:**
Raspberry Pi 4, MicroSD 32 GB, MCP3008 (SPI ADC), Logic Level Converter 4-ch,
MQ-2, MQ-135, BME280 (I2C), Rainfall Sensor DFRobot SEN0575 (I2C),
2× Soil Moisture Probe, Submersible Pressure Sensor (4-20 mA), Flame Sensor (IR AO),
Voltage Sensor Module DC 0–25 V (baterai), RS485 Anemometer + USB-RS485 Converter,
Wind Direction JL-FSX2 (UART GPIO14/15), A7670E atau SIM7600 (satu saja, auto-detect),
Relay 5 V 1-ch, Siren 12 V. Sistem catu daya: Solar Panel 100 W, SCC 20 A, LiFePO4 12 V, Buck Converter.

Struktur project **flat** — `main.py` langsung di root, sejajar dengan
`venv/`, `.env`, `scripts/`, `logs/`, `database/`.

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
> Path ini harus konsisten dengan `WorkingDirectory=` dan `ExecStart=` di `efws.service`.

---

## TAHAP 2 — Persiapan OS (sekali saja)

### 2a. Install dependensi sistem

```bash
sudo apt update && sudo apt install -y \
    python3-venv python3-pip \
    i2c-tools \
    usb-modeswitch modemmanager \
    network-manager git
```

### 2b. Aktifkan interface hardware

```bash
sudo raspi-config
# Interface Options → SPI       → Yes   (MCP3008)
# Interface Options → I2C       → Yes   (BME280, Rainfall SEN0575)
# Interface Options → Serial Port:
#   "login shell over serial" → No
#   "serial port hardware"    → Yes     (Wind Direction UART)

sudo reboot
```

### 2c. Aktifkan UART penuh untuk Wind Direction (JL-FSX2)

Wind Direction Sensor memakai GPIO14/GPIO15 (UART). Di RPi4 secara default,
GPIO14/15 terhubung ke **mini-UART** yang clock-nya terikat frekuensi VPU
(tidak stabil untuk komunikasi serial). Bluetooth juga menempati PL011 UART penuh.

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

### 2d. Tambahkan user ke grup hardware

```bash
# Ganti "uwfadmin" sesuai username yang dipakai:
sudo usermod -aG gpio,spi,i2c,dialout uwfadmin
sudo reboot
```

### 2e. Verifikasi device terdeteksi

```bash
ls /dev/spidev*          # harus: /dev/spidev0.0  (MCP3008)
i2cdetect -y 1           # harus: 0x76 (BME280) DAN 0x1D (Rainfall SEN0575)
ls /dev/ttyUSB*          # harus: beberapa port (A7670E + USB-RS485 Anemometer)
ls /dev/serial0          # harus ada (Wind Direction UART)
```

> Jika salah satu tidak muncul: berhenti, cek wiring dan `raspi-config` sebelum lanjut.
> Jangan paksa lanjut ke tahap berikutnya karena sensor hilang akan terdeteksi sebagai
> `NullSensor` yang diam-diam mengembalikan `null` tanpa error di terminal.

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
EFWS_LAT=-6.2146
EFWS_LON=106.8208

# APN kartu SIM yang dipakai di A7670E
EFWS_APN=internet
```

### Env var interval (nilai default sudah, ubah hanya jika perlu):

```ini
EFWS_READ_INTERVAL=180              # sensor sampling tiap 3 menit
EFWS_TELEMETRY_INTERVAL_SEC=1800    # kirim telemetry tiap 30 menit (normal)
EFWS_EMERGENCY_TELEMETRY_INTERVAL_SEC=600  # tiap 10 menit saat emergency
EFWS_LOCATION_INTERVAL_SEC=1800     # kirim lokasi tiap 30 menit (selalu tetap)
EFWS_HEARTBEAT_INTERVAL_SEC=300     # heartbeat tiap 5 menit (selalu tetap)
EFWS_CONNECTIVITY_CHECK_SEC=120     # retry offline queue tiap 2 menit
```
---

## TAHAP 5 — Test koneksi API (mode mock)

```bash
source venv/bin/activate
python3 tests/test_webhook_api.py
```

Buka halaman webhook.site — satu POST JSON harus muncul live. Jika berhasil:
jalur Pi → 4G → internet → API terbukti jalan.

> Belum ada koneksi internet? Jalankan `tools/mock_api_server.py` di laptop (satu
> jaringan Wi-Fi dengan Pi), lalu set `EFWS_API_URL=http://<ip-laptop>:5000`.

---

## TAHAP 6 — Test tiap sensor (URUTAN PENTING, mode hardware)

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

# 11. A7670E / SIM7600 — signal, registrasi, GPS
python3 tests/test_a7670e.py --gps-timeout 90

# 12. Relay + Sirine (⚠️ SUARA KERAS 120 dB — jauhkan dari telinga)
python3 tests/test_relay_siren.py

# 13. Semua sensor sekaligus (final check sebelum main.py)
python3 tests/test_all_sensors.py

# 14. Integritas offline queue (simulasi jaringan putus)
python3 tests/test_offline_queue_integrity.py
```

---

## TAHAP 7 — Jalankan EFWS penuh (foreground dulu)

```bash
source venv/bin/activate
python3 main.py
```

Amati beberapa siklus (default tiap 3 menit). Pastikan:
- Semua sensor terbaca (tidak ada `NullSensor` yang tak terduga)
- Log menampilkan `READ | semua nilai NORMAL` atau threshold yang memang diharapkan
- `[Telemetry Publisher] Normal Scheduled Send` muncul dan webhook.site menerima data
- `[Location Publisher]` muncul dan mengirim GPS atau fallback koordinat config
- `[Heartbeat Publisher]` muncul tiap 5 menit

Tekan `Ctrl+C` untuk berhenti. EFWS shutdown gracefully (sirine dimatikan, koneksi ditutup).

---

## TAHAP 8 — Jalankan sebagai systemd service (produksi)

### 8a. Sesuaikan `efws.service`

Buka `efws.service` dan sesuaikan path + user:

```ini
[Service]
WorkingDirectory=/home/uwfadmin/ews
ExecStart=/home/uwfadmin/ews/venv/bin/python main.py
EnvironmentFile=-/home/uwfadmin/ews/.env
User=uwfadmin
Group=uwfadmin
```

### 8b. Install dan aktifkan

```bash
sudo cp efws.service /etc/systemd/system/efws.service
sudo systemctl daemon-reload
sudo systemctl enable efws    # auto-start saat boot
sudo systemctl start efws     # jalankan sekarang
```

### 8c. Operasi sehari-hari

```bash
sudo systemctl status efws          # cek jalan/tidak
sudo systemctl restart efws         # WAJIB setelah update kode atau edit .env
sudo systemctl stop efws            # berhenti
sudo journalctl -u efws -f          # log systemd real-time (Ctrl+C hanya stop pantau)
tail -f logs/efws.log               # log aplikasi (lebih detail, ada timestamp ms)
sudo journalctl -u efws -n 100 --no-pager  # lihat 100 baris terakhir tanpa pager
```

### 8d. Script helper (alternatif systemd untuk development)

```bash
chmod +x scripts/efws_ctl.sh
./scripts/efws_ctl.sh start     # jalankan di background
./scripts/efws_ctl.sh status    # cek + CPU/RAM
./scripts/efws_ctl.sh logs      # tail log real-time
./scripts/efws_ctl.sh restart   # restart (tiap kali update kode)
./scripts/efws_ctl.sh stop      # berhenti
```

---

## TAHAP 9 — Setup izin Reboot command

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

## TAHAP 10 — Pindah ke API produksi

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
| Pressure Sensor | `depth_m` tidak masuk akal | `EFWS_PRESSURE_RANGE_M` belum disesuaikan rentang sensor Anda |
| Battery Sensor | `voltage`/`percent` salah | `EFWS_BATTERY_SENSOR_MAX_V` (default 16.5 V) atau `EFWS_BATTERY_MAX_V`/`MIN_V` perlu disesuaikan |
| Anemometer RS485 | Exception saat baca | Slave ID / register Modbus salah; wiring A/B terbalik; `EFWS_ANEM_PORT` salah |
| Wind Direction | Data acak / tidak ada | `disable-bt` belum di-set; console serial login masih aktif; wiring TX/RX terbalik |
| A7670E | AT tidak merespons | Port salah (`ls /dev/ttyUSB*`); modul belum power-on; coba `EFWS_SIM_PORT=/dev/ttyUSB1` |
| A7670E | GPS timeout terus | Antena GNSS belum terpasang; tidak ada langit terbuka (cold fix butuh 2–5 menit di lapangan) |
| A7670E | Anemometer error setelah SIM detect | `EFWS_ANEM_PORT` belum di-set; `scan_ports()` ikut scan port anemometer |
| Relay | Klik tapi sirine tidak bunyi | Sumber 12 V sirine belum tersambung; wiring COM/NO salah |
| Relay | Tidak klik | GPIO pin di `.env` tidak sesuai wiring fisik; cek `EFWS_GPIO_RELAY` |
| API | Kirim gagal terus | Cek `ping 8.8.8.8`; `EFWS_API_URL` masih placeholder; APN salah |
| systemd | `status` → `failed` | `journalctl -u efws -n 50 --no-pager` untuk detail; biasanya modul Python hilang dari venv atau `.env` tidak terbaca |
| systemd | Reboot command `FAILED` | Sudoers rule untuk `uwfadmin` belum ditambahkan (lihat TAHAP 9) |
| SQLite | Database file besar terus membesar | `EFWS_DB_RETENTION_DAYS` terlalu besar atau retention loop belum jalan; cek log `🧹 Retention:` |

---

## Cek Kondisi Sistem — Perintah Berguna

```bash
# Cek sinyal modem 4G
python3 -c "
from communication.sim_detector import detect_sim
sim = detect_sim()
print('Modul:', sim.module, '@ port', sim.port)
print('Signal:', sim.signal_quality().strip())
print('Network:', sim.network_registration().strip())
sim.close()
"

# Cek offline queue (berapa item pending)
python3 -c "
from database.db_manager import DBManager
db = DBManager()
print('Pending queue:', db.count_pending_queue(), 'item')
db.close()
"

# Cek 5 pembacaan sensor terakhir di SQLite
python3 -c "
from database.db_manager import DBManager
import json
db = DBManager()
for r in db.recent_readings(5):
    print(r)
db.close()
"

# Scan port serial manual (untuk identifikasi port modem)
ls -la /dev/ttyUSB*
python3 tools/modbus_register_scan.py   # scan register anemometer
python3 tools/send_sms.py               # test kirim SMS via A7670E
```
