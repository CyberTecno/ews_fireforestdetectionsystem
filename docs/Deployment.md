# EFWS — Panduan Lengkap: Wiring → Testing → Prototyping API → Jalan di Background

Panduan ini dari NOL sampai EFWS jalan stabil di background, memakai
hardware aktual: Raspberry Pi 4, MCP3008 (ADC SPI), Logic Level Converter,
MQ-2, MQ-135, BME280, 2x Soil moisture probe, Submersible pressure sensor
(4-20mA), Modul sensor tegangan DC 0-25V (baterai), RS485 Anemometer,
A7670E/SIM7600 (4G+GNSS, salah satu saja), Relay 5V + Sirine 12V 120dB.

Struktur project ini **flat** — `main.py` ada langsung di root project
(bukan di subfolder). `venv/`, `.env`, `scripts/`, `logs/`, `database/`
semuanya sejajar dengan `main.py`.

---

## TAHAP 0 — Wiring fisik

**WAJIB dibaca dulu**: `docs/Pinout.md` — berisi tabel wiring lengkap per
komponen, termasuk catatan keselamatan logic level converter (sinyal 5V
sensor analog HARUS lewat level converter sebelum masuk MCP3008/GPIO) dan
catatan keselamatan jalur 12V sirine.

Setelah semua kabel terpasang, **JANGAN langsung jalankan kode** — lanjut
dulu ke persiapan OS & cek device terlebih dulu di Tahap 2.

---

## TAHAP 1 — Pindahkan project ke Raspberry Pi

```bash
scp -r efws pi@<ip-raspberry-pi>:/home/pi/efws
ssh pi@<ip-raspberry-pi>
cd /home/pi/efws
```

---

## TAHAP 2 — Persiapan OS (sekali saja)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip \
    i2c-tools usb-modeswitch modemmanager network-manager git

sudo raspi-config
# Interface Options -> I2C  -> Yes   (untuk BME280)
# Interface Options -> SPI  -> Yes   (untuk MCP3008)
# Interface Options -> Serial Port -> "login shell over serial" = No,
#                                     "serial port hardware" = Yes
#                                     (HANYA jika A7670E disambung via UART,
#                                      kalau via USB langkah ini bisa dilewati)
sudo reboot
```

Setelah reboot, cek device-device fisik sudah terdeteksi sebelum lanjut:
```bash
ls /dev/spidev*     # harus muncul /dev/spidev0.0 (MCP3008)
i2cdetect -y 1       # harus muncul 0x76 (BME280)
ls /dev/ttyUSB*      # harus muncul beberapa ttyUSBx (A7670E + anemometer)
```
Kalau salah satu di atas TIDAK muncul, berhenti dulu dan cek wiring/
`raspi-config` sebelum lanjut — jangan paksa lanjut ke instalasi Python.

Tambahkan user `pi` ke grup yang dibutuhkan supaya tidak perlu `sudo`
tiap akses hardware:
```bash
sudo usermod -aG gpio,spi,i2c,dialout pi
sudo reboot
```

---

## TAHAP 3 — Setup Python environment

```bash
cd /home/pi/efws
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

---

## TAHAP 4 — Setup `.env` (mode mock dulu, lalu webhook.site)

```bash
cp .env.example .env
nano .env
```

Untuk **prototyping cepat ke API**, buka https://webhook.site di browser,
copy "Your unique URL", lalu isi:
```ini
EFWS_RUN_MODE=mock
EFWS_API_URL=https://webhook.site/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EFWS_API_KEY=
```
Biarkan `EFWS_RUN_MODE=mock` dulu di tahap ini — kita test koneksi API
TANPA hardware terlebih dulu, baru testing per-sensor satu-satu, baru
pindah ke `hardware` di TAHAP 7.

---

## TAHAP 5 — Test koneksi API (webhook.site) duluan

```bash
source venv/bin/activate
python3 tests/test_webhook_api.py
```
Buka halaman webhook.site Anda — satu request POST JSON telemetry harus
muncul live di sana. Kalau ini sukses, jalur Pi → internet → API sudah
terbukti bekerja, baru lanjut ke testing sensor satu-satu.

> Belum ada koneksi internet/4G di Pi? Pakai `tools/mock_api_server.py`
> dulu (jalankan di laptop yang satu jaringan dengan Pi, lalu set
> `EFWS_API_URL=http://<ip-laptop>:5000/api/v1/efws` di `.env`) supaya bisa
> lihat JSON yang terkirim secara langsung tanpa perlu internet sama sekali.

---

## TAHAP 6 — Test tiap sensor satu-satu (URUTAN INI PENTING)

Jalankan **berurutan** — kalau satu gagal, selesaikan dulu sebelum lanjut
ke yang berikutnya (sensor analog semuanya bergantung ke MCP3008, jadi
kalau test #1 gagal, semua sensor analog setelahnya juga akan gagal).

```bash
# 1. MCP3008 dulu - fondasi semua sensor analog
python3 tests/test_mcp3008.py

# 2. MQ-2 & MQ-135 (analog, lewat MCP3008)
python3 tests/test_gas_sensors.py

# 3. BME280 (I2C, independen dari MCP3008)
python3 tests/test_bme280.py

# 4. Soil moisture probe (analog, lewat MCP3008) - termasuk kalibrasi
python3 tests/test_soil.py

# 5. Submersible pressure sensor (analog via burden resistor, lewat MCP3008)
python3 tests/test_pressure.py

# 6. Battery voltage sensor (analog, lewat MCP3008)
python3 tests/test_battery.py

# 7. RS485 Anemometer
python3 tests/test_anemometer.py

# 8. A7670E/SIM7600 - sinyal, SIM, GPS
python3 tests/test_a7670e.py --gps-timeout 90

# 9. Relay + Sirine (⚠️ SUARA KERAS 120dB, baca peringatan di scriptnya)
python3 tests/test_relay_siren.py

# 10. Semua sensor sekaligus, satu putaran baca (final check sebelum main.py)
python3 tests/test_all_sensors.py

# 11. Integritas antrian offline (simulasi sinyal terputus, cek data tidak berubah)
python3 tests/test_offline_queue_integrity.py
```

---

## TAHAP 7 — Jalankan EFWS penuh di mode hardware (foreground dulu)

```bash
nano .env
# Ubah: EFWS_RUN_MODE=hardware

python3 main.py
```
Amati beberapa siklus baca (default tiap 5 detik) — pastikan semua nilai
sensor masuk akal, lalu cek webhook.site untuk konfirmasi data benar-benar
terkirim. Tekan `Ctrl+C` untuk berhenti setelah yakin semuanya jalan baik.

---

## TAHAP 8 — Jalankan di background (tanpa mengganggu terminal)

Dua cara — pilih salah satu sesuai kebutuhan:

### Cara A: `scripts/efws_ctl.sh` (cepat, untuk masih sering edit kode)

```bash
chmod +x scripts/efws_ctl.sh
./scripts/efws_ctl.sh start      # jalankan
./scripts/efws_ctl.sh status     # cek jalan/tidak + CPU/RAM
./scripts/efws_ctl.sh logs       # tail log real-time (Ctrl+C cuma stop pantau, proses tetap jalan)
./scripts/efws_ctl.sh restart    # WAJIB jalankan ini tiap kali update kode
./scripts/efws_ctl.sh stop       # berhenti
```

### Cara B: systemd (disarankan untuk produksi — auto-start saat boot, auto-restart saat crash)

```bash
sudo cp efws.service /etc/systemd/system/efws.service
sudo systemctl daemon-reload
sudo systemctl enable efws      # auto-start saat boot
sudo systemctl start efws       # jalankan sekarang

sudo systemctl status efws          # cek jalan/tidak
sudo systemctl restart efws         # WAJIB jalankan ini tiap kali update kode
sudo systemctl stop efws            # berhenti
sudo journalctl -u efws -f          # log sistem real-time
tail -f logs/efws.log               # log aplikasi (lebih detail)
```

`.env` dibaca otomatis lewat `EnvironmentFile=` di `efws.service` — jadi
edit `.env` lalu `systemctl restart efws` cukup, tidak perlu sentuh file
service lagi kecuali ganti path/user.

---

## TAHAP 9 — Pindah dari webhook.site ke API produksi

Setelah prototyping selesai dan backend asli sudah siap:
```bash
nano .env
# EFWS_API_URL=https://api-anda.com/api/v1/efws
# EFWS_API_KEY=token_rahasia_anda   (jika backend pakai auth Bearer token)

./scripts/efws_ctl.sh restart    # atau: sudo systemctl restart efws
```

---

## Troubleshooting per komponen

| Komponen | Gejala | Kemungkinan penyebab |
|----------|--------|------------------------|
| MCP3008 | `test_mcp3008.py` gagal buka SPI | SPI belum aktif di raspi-config; `spidev` belum terinstall; wiring CLK/DOUT/DIN/CS salah |
| MQ-2/MQ-135 | Nilai selalu mentok di angka sama (clipping) | Lupa pasang logic level converter di jalur analognya |
| MQ-2/MQ-135 | Nilai ppm tidak masuk akal | Sensor belum preheat (butuh 24-48 jam untuk akurasi penuh) |
| BME280 | `i2cdetect -y 1` tidak muncul 0x76 | I2C belum aktif; wiring SDA/SCL terbalik; alamat sebenarnya 0x77 (set `EFWS_BME280_ADDR=0x77`) |
| Soil probe | moisture_percent selalu 0% atau 100% | Belum dikalibrasi (`dry_raw`/`wet_raw` di `sensors/soil.py`) |
| Pressure sensor | `current_ma` selalu ~0, `fault_open_loop=True` | Loop putus/belum tersambung, atau PSU 12-24V loop belum nyala — jalankan `python3 tests/test_pressure.py` untuk diagnosis |
| Pressure sensor | `depth_m` tidak masuk akal | `EFWS_PRESSURE_RANGE_M` belum disesuaikan datasheet sensor Anda |
| Battery sensor | `voltage`/`percent` tidak masuk akal | `BATTERY_SENSOR_MAX_V`/`BATTERY_MAX_V`/`BATTERY_MIN_V` belum disesuaikan spesifikasi baterai |
| Anemometer | Exception saat baca | Slave ID/register Modbus salah (cek datasheet unit Anda); wiring A/B terbalik |
| A7670E | `AT` tidak merespons | Port salah (`ls /dev/ttyUSB*`), modul belum power-on, baudrate salah |
| A7670E | GPS timeout terus | Antena GNSS belum terpasang/tidak ada langit terbuka; pastikan pakai `AT+CGNSSPWR` bukan `AT+CGPS` (sudah benar di kode ini) |
| Relay/Sirine | Relay "klik" tapi sirine tidak bunyi | Sumber 12V belum tersambung; wiring COM/NO salah |
| Relay/Sirine | Relay tidak "klik" sama sekali | `active_low` salah; GPIO pin di `.env` tidak sesuai wiring fisik |
| API | `test_webhook_api.py` gagal kirim | Cek `ping 8.8.8.8` (internet jalan?); `EFWS_API_URL` masih placeholder |
| systemd | `status` → `failed` | `journalctl -u efws -n 50 --no-pager` untuk detail; biasanya modul Python belum terinstall di venv, atau `.env` tidak ditemukan |
