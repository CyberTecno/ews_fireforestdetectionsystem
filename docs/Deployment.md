# EFWS — Panduan Deployment & Testing di Raspberry Pi
> Versi refaktor: komunikasi via **HTTP REST API** (bukan MQTT/Telegram)

---

## 1. Persiapan awal (satu kali)

```bash
# Di Raspberry Pi, buka terminal
cd ~
git clone https://github.com/kamu/efws.git   # atau transfer folder efws_refactored

# Buat virtual environment
python3 -m venv efws/venv
source efws/venv/bin/activate

# Install dependensi minimal (untuk testing mock)
pip install requests

# Install semua dependensi (untuk hardware nyata)
# pip install -r efws/efws/requirements.txt
```

---

## 2. Testing mode MOCK (tanpa hardware apapun)

Mode ini mensimulasi semua sensor dengan skenario otomatis (normal → warning → critical setiap 2 menit).

```bash
cd ~/efws/efws
export EFWS_RUN_MODE=mock
export EFWS_DEVICE_ID=efws-test-01

# Opsional: ganti ke URL API kamu (atau pakai https://webhook.site untuk inspeksi)
export EFWS_API_URL=https://webhook.site/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Jalankan langsung (foreground, Ctrl+C untuk berhenti)
python main.py
```

**Yang akan terlihat di terminal:**
```
2025-01-01T10:00:00 [INFO] efws.main: EFWS initialised. Device: efws-test-01 | Mode: mock
2025-01-01T10:00:00 [INFO] efws.main: EFWS loop started...
2025-01-01T10:00:05 [INFO] efws.main: READ #1 | alarm=none     | mq2=80 ppm | ...
```

---

## 3. Jalankan sebagai background service (tidak ganggu terminal)

### Opsi A — systemd (REKOMENDASI, auto-start saat Pi booting)

```bash
# Edit path & environment di file service
nano ~/efws/efws.service

# Install service
sudo cp ~/efws/efws.service /etc/systemd/system/efws.service
sudo systemctl daemon-reload
sudo systemctl enable efws          # auto-start saat boot
sudo systemctl start efws           # mulai sekarang

# Cek status
sudo systemctl status efws

# Lihat log live (seperti tail -f tapi dari systemd)
sudo journalctl -u efws -f

# Lihat log 100 baris terakhir
sudo journalctl -u efws -n 100

# Hentikan / restart
sudo systemctl stop efws
sudo systemctl restart efws
```

### Opsi B — nohup (simpel, cocok untuk testing cepat)

```bash
cd ~/efws/efws
source ~/efws/venv/bin/activate

# Jalankan di background, log ke file
nohup python main.py >> logs/efws.log 2>&1 &

# Simpan PID
echo $! > efws.pid

# Cek apakah masih jalan
ps aux | grep main.py

# Lihat log live
tail -f logs/efws.log

# Hentikan
kill $(cat efws.pid)
```

### Opsi C — screen (bisa di-attach kembali kapanpun)

```bash
# Install screen jika belum ada
sudo apt-get install screen

# Buat sesi baru
screen -S efws

# Dalam sesi screen, jalankan EFWS
cd ~/efws/efws && source ~/efws/venv/bin/activate
python main.py

# Detach tanpa menghentikan: tekan Ctrl+A lalu D
# Re-attach kapanpun: screen -r efws
```

---

## 4. Verifikasi data tersimpan di database

```bash
cd ~/efws/efws

# Buka SQLite
sqlite3 database/efws_data.db

# Query data sensor terbaru
SELECT id, timestamp, alarm_level, mq2_ppm, mq135_ppm,
       flame_detected, temperature_c, humidity_pct,
       soil_moisture, wind_speed_ms
FROM sensor_readings
ORDER BY id DESC
LIMIT 10;

# Lihat alarm yang pernah terjadi
SELECT * FROM alarm_events ORDER BY id DESC LIMIT 5;

# Lihat API queue (pending / gagal kirim)
SELECT id, endpoint, attempts, sent, last_error
FROM api_queue WHERE sent=0;

# Hitung total readings
SELECT COUNT(*) as total, MIN(timestamp) as first, MAX(timestamp) as last
FROM sensor_readings;

# Keluar dari sqlite3
.quit
```

---

## 5. Konfigurasi API endpoint

Edit `config/settings.py` atau set environment variable:

```bash
# Untuk testing cepat (inspeksi request di browser)
export EFWS_API_URL=https://webhook.site/your-unique-id

# Untuk server sendiri
export EFWS_API_URL=https://api.server-kamu.com/v1/efws
export EFWS_API_KEY=bearer_token_opsional
```

Payload JSON yang dikirim ke `{API_URL}/data`:
```json
{
  "device_id": "efws-001",
  "location": {"lat": 0.0, "lon": 0.0},
  "timestamp": "2025-01-01T10:00:00+00:00",
  "mode": "mock",
  "sensors": {
    "mq2":   {"voltage": 0.48, "ppm": 80.0},
    "mq135": {"voltage": 0.43, "ppm": 120.0},
    "flame": {"raw": 1, "flame_detected": false},
    "bme280":{"temperature_c": 30.1, "humidity_percent": 64.8, "pressure_hpa": 1013.0},
    "soil":  {"raw": 18200, "moisture_percent": 55.0},
    "wind":  {"speed_ms": 2.5}
  },
  "statuses": {
    "mq2": "normal", "mq135": "normal", "flame": "normal",
    "temperature": "normal", "humidity_low": "normal",
    "soil_dry": "normal", "wind": "normal"
  },
  "alarm": {"active": false, "level": "none", "triggered_by": []}
}
```

---

## 6. Switch ke mode hardware (setelah sensor terpasang)

```bash
# Edit settings atau set env
export EFWS_RUN_MODE=hardware

# Pastikan I2C aktif di Pi
sudo raspi-config   # Interface Options → I2C → Enable

# Cek perangkat I2C terdeteksi
sudo i2cdetect -y 1
# Harus muncul 0x48 (ADS1115) dan 0x76 atau 0x77 (BME280)

# Cek port serial anemometer
ls /dev/ttyUSB*

# Restart service
sudo systemctl restart efws
```

---

## 7. Rotasi log otomatis (agar log tidak penuh)

```bash
sudo nano /etc/logrotate.d/efws
```
Isi:
```
/home/pi/efws/efws/logs/efws.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    postrotate
        systemctl restart efws
    endscript
}
```

---

## Ringkasan perintah harian

| Aksi | Perintah |
|------|----------|
| Lihat log live | `sudo journalctl -u efws -f` |
| Cek status | `sudo systemctl status efws` |
| Restart | `sudo systemctl restart efws` |
| Lihat DB (10 data terbaru) | `sqlite3 database/efws_data.db "SELECT id,timestamp,alarm_level,temperature_c FROM sensor_readings ORDER BY id DESC LIMIT 10;"` |
| Hitung total data | `sqlite3 database/efws_data.db "SELECT COUNT(*) FROM sensor_readings;"` |
