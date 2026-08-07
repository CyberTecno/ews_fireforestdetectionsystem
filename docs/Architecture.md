# EFWS Architecture Overview

## Hardware Topology

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     POWER SYSTEM                                         │
│  [Solar Panel 100W] → [SCC 20A PWM] → [LiFePO4 12V]                      │
│       [LiFePO4 12V] → [Buck Converter 12V→5V] → [Raspberry Pi 4 USB-C]   │
└──────────────────────────────────────────────────────────────────────────┘

                              I2C (bus shared 0x76 + 0x1D)
  ┌─────────────────┐ ────────────────────────────────────────
  │ BME280 (0x76)   │                                         │
  ├─────────────────┤                                         │
  │ Rainfall SEN0575│                          ┌──────────────▼──────────────┐
  │ (I2C 0x1D)      │                          │                             │
  └─────────────────┘         SPI              │      Raspberry Pi 4         │
  ┌─────────────────┐ ────────────────────────►│    main.py orchestrator     │
  │ MCP3008 ADC     │                          │  (6 thread, 4 endpoint API) │
  │  CH0: MQ-2      │◄── LLC ──── MQ-2         │                             │
  │  CH1: MQ-135    │◄── LLC ──── MQ-135       └──────┬────────┬─────────────┘
  │  CH2: Soil Surf │◄── LLC ──── Soil Surface        │        │
  │  CH3: Soil Deep │◄── LLC ──── Soil Deep           │        │
  │  CH4: Pressure  │◄── R_BURDEN 100Ω (4-20mA)       │ GPIO27 │ USB
  │  CH5: Battery   │◄── Voltage Sensor Module        │        │
  │  CH6: Flame AO  │◄── Flame IR Sensor              ▼        ▼
  └─────────────────┘                          [Relay 5V]   [A7670E / SIM7600]
  ┌─────────────────┐  USB + RS485                   │        (satu saja, auto-
  │ RS485 Anemometer│◄── USB-RS485 Converter         │         detect ATI)
  └─────────────────┘  (Modbus RTU)                  │              │
  ┌─────────────────┐  UART GPIO14/15                ▼              ▼
  │ Wind Dir JL-FSX2│◄── (9600 bps TTL)        [Siren 12V]    4G Network →
  └─────────────────┘                           [120 dB]       REST API Backend
```

---

## Thread Model (6 Thread)

`main.py` menjalankan **6 thread independen** secara bersamaan sejak startup.
Kegagalan di satu thread tidak pernah menghentikan thread lain.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MAIN THREAD (sensor sampling loop)          tiap SENSOR_READ_INTERVAL_SEC  │
│  ─ Baca semua sensor (.read() masing-masing driver)                         │
│  ─ Hitung smokeLevel (MQ-2 + MQ-135 weighted formula)                       │
│  ─ Evaluasi threshold aktif (remote-first per-field, fallback lokal)        │
│  ─ Set/clear _emergency Event (single source of truth)                      │
│  ─ Sirine lokal: AlarmController.set_level("critical"/"normal")             │
│  ─ Update _latest_data snapshot (dibaca Publisher thread lain)              │
│  TIDAK PERNAH: kirim ke API, simpan ke SQLite, ambil GPS                    │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ _latest_data snapshot (lock)
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌────────────────┐ ┌─────────────────┐ ┌────────────────────────────────────┐
│ LOCATION       │ │ TELEMETRY       │ │ HEARTBEAT                          │
│ PUBLISHER      │ │ PUBLISHER       │ │ PUBLISHER                          │
│                │ │                 │ │                                    │
│ Interval:      │ │ Interval ADAPTIF│ │ Interval:                          │
│ 1800s (tetap)  │ │ Normal: 1800s   │ │ 300s (tetap)                       │
│                │ │ Emergency: 600s │ │                                    │
│ 1. Ambil GPS   │ │                 │ │ POST /sensors/heartbeat            │
│    (A7670E AT  │ │ 1. Simpan DB    │ │ → response bawa 'commands'         │
│    +CGPSINFO)  │ │    (SQLite)     │ │ → _process_commands()              │
│ 2. Log lokal   │ │ 2. POST         │ │   (endpoint 4 ACK, event-driven)   │
│ 3. POST        │ │    /sensors/    │ │                                    │
│    /sensors/   │ │    telemetry    │ │ Emergency Mode TIDAK mempengaruhi  │
│    location    │ │ → response bawa │ │ interval Heartbeat sama sekali     │
│                │ │   'config'      │ │                                    │
│ Emergency Mode │ │   (remote thr.) │ └────────────────────────────────────┘
│ TIDAK          │ │                 │
│ mempengaruhi   │ │ Dibangunkan     │ ┌────────────────────────────────────┐
│ Location sama  │ │ SEKETIKA saat   │ │ FLUSH QUEUE                        │
│ sekali         │ │ masuk Emergency │ │                                    │
└────────────────┘ │ (_telemetry_    │ │ Interval: 120s (independen)        │
                   │  wake Event)    │ │ Retry offline queue FIFO           │
                   └─────────────────┘ │ (api_queue di SQLite)              │
                                       │ Stop saat jaringan putus lagi,     │
                                       │ pertahankan urutan FIFO            │
                                       └────────────────────────────────────┘
                                       ┌────────────────────────────────────┐
                                       │ RETENTION                          │
                                       │                                    │
                                       │ Interval: 6 jam                    │
                                       │ Purge sensor_readings +            │
                                       │ api_queue (selesai) +              │
                                       │ location_log lama (> 3 hari)       │
                                       └────────────────────────────────────┘
```

---

## 4 Endpoint API

| # | Endpoint | Scheduler | Interval | Catatan |
|---|----------|-----------|----------|---------|
| 1 | `POST /sensors/location` | Location Publisher | 1800s (tetap) | GPS HANYA diambil di sini |
| 2 | `POST /sensors/telemetry` | Telemetry Publisher | 1800s / 600s (emergency) | Response bawa `config` (remote threshold), data disimpan SQLite DULU |
| 3 | `POST /sensors/heartbeat` | Heartbeat Publisher | 300s (tetap) | Response bawa `commands` |
| 4 | `POST /sensors/commands/ack` | Event-driven dari #3 | — | Hanya jalan jika response #3 bawa `commands` |

---

## Alur Data — Detail

### Sensor Sampling (Main Thread)
```
Baca semua sensor → hitung smokeLevel → evaluasi threshold (remote-first per-field)
     ↓                                         ↓
Update _latest_data                   Apakah ada threshold terlampaui?
(dibaca Publisher)                         ↓              ↓
                                        YA: N kali      TIDAK:
                                        berturut?        ↓
                                         ↓           _emergency.clear()
                                         ↓           alarm.set_level("normal")
                                      _emergency.set()
                                      alarm.set_level("critical")
                                      _telemetry_wake.set()   ← bangunkan Telemetry SEKARANG
                                      _emergency_immediate_send.set()  ← sekali saja
```

### Telemetry Publisher (Thread)
```
Tunggu _telemetry_wake ATAU interval habis
     ↓
Ambil _latest_data snapshot (lock)
     ↓
Hitung rainfall_delta (delta dari pengiriman SEBELUMNYA, bukan window 1 jam sensor)
     ↓
Simpan ke SQLite DULU (sensor_readings + full_payload untuk audit)
     ↓
POST /sensors/telemetry
     ├── Sukses → apply remote_config (threshold override per-field)
     └── Gagal (jaringan/5xx) → masuk api_queue (FIFO), di-flush thread terpisah
```

### GPS — Location Publisher
```
Priority fallback (tiap 1800s):
  1. AT+CGNSSPWR=1 → polling AT+CGPSINFO → fix? → source="gps"
  2. Semua percobaan gagal & pernah fix sebelumnya → source="gps_cached" (posisi terakhir)
  3. Belum pernah fix sama sekali → source="config" (koordinat statis dari .env)
```

### Emergency Mode
- **Masuk:** N consecutive readings melewati threshold → `_emergency.set()` → Telemetry Publisher
  dibangunkan seketika (Immediate Emergency Send), lalu beralih ke interval 600s
- **Keluar:** semua nilai kembali normal → `_emergency.clear()` → interval kembali 1800s
- **Tidak terpengaruh:** Location Publisher dan Heartbeat Publisher (interval tetap)

### Threshold — Remote-first Per-field
```
resolve_active_thresholds(local, remote_config):
  Tiap field: remote menang jika tidak None, else pakai lokal
  windDangerThreshold → SELALU lokal (tidak ada di kontrak API)
```

---

## Alur Offline Queue

```
Jaringan/5xx gagal → payload masuk api_queue (SQLite, FIFO)
        ↓
Flush Queue thread (tiap 120s):
  Cek konektivitas → online?
  → YA: flush batch 10 item FIFO
       Sukses  → mark sent=1
       4xx     → mark failed (buang, jangan blokir FIFO)
       Putus lagi → stop di item itu, FIFO dipertahankan
  → TIDAK: skip (tunggu 120s lagi)

Item di-skip setelah 10 kali gagal (stale, tidak blokir FIFO selamanya).
api_queue (yang sudah sent=1 atau attempts≥10) dibersihkan retention thread tiap 6 jam.
```

---

## Module Responsibilities

| Module | File utama | Tanggung jawab |
|--------|-----------|---------------|
| **sensors/** | `mq2.py`, `mq135.py`, `bme280.py`, `soil.py`, `pressure.py`, `anemometer.py`, `wind_direction.py`, `battery.py`, `flame.py`, `rainfall.py` | Driver hardware, masing-masing punya `.read()` → dict. `null_sensor.py` untuk fallback jika sensor gagal init. `mock_sensors.py` untuk `EFWS_RUN_MODE=mock`. |
| **alarm/** | `relay.py`, `siren.py` | `relay.py`: driver GPIO low-level. `AlarmController`: 2 level eskalasi (WARNING=pulsing 0.4s/1.6s, CRITICAL=on terus) dari 1 relay. Tidak ada buzzer terpisah. |
| **communication/** | `sim_detector.py`, `a7670e.py`, `sim7600_legacy.py`, `api_publisher.py` | Auto-detect modul 4G (A7670E atau SIM7600 via ATI fingerprint, cache ke `.sim_cache`). `api_publisher.py`: satu-satunya jalur keluar data (REST + offline queue). |
| **database/** | `db_manager.py` | SQLite: tabel `sensor_readings`, `api_queue`, `location_log`. Tidak menyimpan alarm level / threshold — itu tanggung jawab backend. |
| **config/** | `settings.py`, `thresholds.json`, `threshold_resolver.py` | `settings.py`: semua env var tersentral. `thresholds.json`: fallback lokal HANYA untuk sirine real-time. `threshold_resolver.py`: merge remote+lokal per-field. |
| **main.py** | — | Orchestrator: inisialisasi semua modul, jalankan 6 thread, sensor sampling loop utama. |

---

## Prinsip Desain

- **Data tidak pernah hilang:** SQLite ditulis SEBELUM dikirim ke API. Gagal kirim → offline queue → retry otomatis.
- **Sirine real-time, independen dari jaringan:** evaluasi threshold & relay lokal jalan di main thread, tidak pernah menunggu respons API.
- **Threshold remote-first:** backend bisa override threshold per-field via response telemetry. Device selalu punya fallback lokal.
- **Emergency tidak mengganggu Location/Heartbeat:** hanya interval Telemetry yang berubah saat emergency.
- **Sensor failure graceful:** sensor yang gagal init → `NullSensor` (return `None` semua field) → `_exceeds(None, ...)` selalu False → tidak trigger alarm palsu.
- **SIM auto-detect:** satu kode berjalan di atas A7670E atau SIM7600, dipilih otomatis saat startup berdasarkan respons ATI.
