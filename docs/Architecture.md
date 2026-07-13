# EFWS Architecture Overview

```
                         ┌───────────────────────────┐
                         │   Solar 80-100W + LiFePO4  │
                         │   + Voltage Sensor Module  │
                         └─────────────┬─────────────┘
                                       5V/12V/loop
                                        │
┌──────────────┐   I2C   ┌─────────────▼─────────────┐   GPIO    ┌────────────┐
│ BME280       │◄───────►│                            │──────────►│ Relay 5V   │──►12V Siren
│              │         │      Raspberry Pi 4        │           └────────────┘
├──────────────┤  SPI    │      (main.py orchestrator)│
│ MCP3008 ADC  │◄───────►│                            │
│ (MQ-2/MQ-135/│         │                            │
│  Soil x2/    │         │                            │
│  Pressure/   │         │                            │
│  Battery)    │         │                            │
└──────────────┘         │                            │
┌──────────────┐  USB    │                            │  USB/UART  ┌─────────────┐
│ RS485        │◄───────►│                            │───────────►│ A7670E /    │──► 4G Network
│ Anemometer   │         │                            │            │ SIM7600     │
└──────────────┘         └─────────────┬──────────────┘            │ (satu saja) │
                                        │                           └─────────────┘
                          ┌─────────────┴──────────────┐
                          │ 1) Simpan ke SQLite DULU    │
                          │ 2) Evaluasi lokal (siren)   │
                          │ 3) Coba kirim ke REST API   │
                          │ 4) Gagal → antrian offline  │
                          └─────────────┬──────────────┘
                                        ▼
                    EFWS_API_URL/sensors/telemetry (backend)
                    ── backend yang menyimpan alarm level &
                       evaluasi threshold "resmi"
```

## Alur data (penting)

1. **Baca** semua sensor tiap `EFWS_READ_INTERVAL` detik.
2. **Simpan ke SQLite dulu** (`sensor_readings`, sumber kebenaran lokal) —
   data tidak pernah hilang meski sinyal/koneksi sedang mati.
3. **Evaluasi lokal** terhadap `config/thresholds.json` — HANYA dipakai
   untuk menyalakan sirine secara real-time di lapangan. Hasil evaluasi ini
   **tidak** disimpan ke database maupun dikirim ke API — alarm level &
   threshold "resmi" adalah tanggung jawab backend, bukan device.
4. **Coba kirim** payload ke `EFWS_API_URL/sensors/telemetry`. Kalau
   berhasil, selesai. Kalau gagal (sinyal mati), payload otomatis masuk
   antrian offline (`api_queue`) — payload disimpan APA ADANYA, tidak
   berubah sedikit pun.
5. Selama offline, publisher **tidak** spam retry — hanya cek sinyal ulang
   tiap `EFWS_CONNECTIVITY_CHECK_SEC` (default 120s / 2 menit). Begitu
   online lagi, seluruh antrian di-flush otomatis secara FIFO.

## Module responsibilities

- **sensors/**: satu driver class per sensor fisik, masing-masing punya `.read()`
  yang mengembalikan dict. `mock_sensors.py` menyediakan versi simulasi untuk
  testing tanpa hardware (`EFWS_RUN_MODE=mock`).
- **alarm/**: `relay.py` adalah driver GPIO low-level; `siren.py`
  (`AlarmController`) mengubahnya jadi 2 tingkat eskalasi (WARNING = berdenyut
  pelan, CRITICAL = nyala terus) lewat SATU relay yang sama — tidak ada buzzer
  terpisah di hardware ini.
- **communication/**: `sim_detector.py` auto-detect modul 4G yang terpasang
  (A7670E atau SIM7600), `api_publisher.py` adalah satu-satunya jalur keluar
  data (REST API + offline queue). Tidak ada MQTT atau Telegram di project ini.
- **database/**: `db_manager.py` menyimpan setiap pembacaan sensor mentah +
  payload API persis, dan mengelola antrian offline. Tidak menyimpan alarm
  level maupun threshold — itu tanggung jawab backend.
- **config/**: `settings.py` memusatkan semua pin/channel/kredensial;
  `thresholds.json` memusatkan batas warning/critical untuk sirine LOKAL saja.
- **main.py**: baca → simpan DB → evaluasi lokal (siren) → kirim/antri → ulangi.
