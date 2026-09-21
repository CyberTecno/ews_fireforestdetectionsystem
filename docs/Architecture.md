# EFWS Architecture Overview

## Hardware Topology

```
┌──────────────────────────────────────────────────────────────────────────┐
│ POWER SYSTEM │
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
│ MCP3008 ADC │ │ (6 threads, 4 endpoints API) │
  │  CH0: MQ-2      │◄── LLC ──── MQ-2         │                             │
  │  CH1: MQ-135    │◄── LLC ──── MQ-135       └──────┬────────┬─────────────┘
  │  CH2: Soil Surf │◄── LLC ──── Soil Surface        │        │
  │  CH3: Soil Deep │◄── LLC ──── Soil Deep           │        │
  │  CH4: Pressure  │◄── R_BURDEN 100Ω (4-20mA)       │ GPIO27 │ USB
  │  CH5: Battery   │◄── Voltage Sensor Module        │        │
  │  CH6: Flame AO  │◄── Flame IR Sensor              ▼        ▼
  └─────────────────┘                          [Relay 5V]   [A7670E / SIM7600]
  ┌─────────────────┐  USB + RS485                   │        (one only, auto-
  │ RS485 Anemometer│◄── USB-RS485 Converter         │         detect ATI)
  └─────────────────┘  (Modbus RTU)                  │              │
  ┌─────────────────┐  UART GPIO14/15                ▼              ▼
  │ Wind Dir JL-FSX2│◄── (9600 bps TTL)        [Siren 12V]    4G Network →
└─────────────────┘ [120 dB] REST API Backend
```

---

## Thread Model (6 Thread)

`main.py` runs **6 independent threads** simultaneously from startup.
Failure in one thread never stops other threads.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MAIN THREAD (sensor sampling loop)          tiap SENSOR_READ_INTERVAL_SEC  │
│ ─ Read all sensors (.read() each driver) │
│  ─ Hitung smokeLevel (MQ-2 + MQ-135 weighted formula)                       │
│ ─ Active threshold evaluation (per-field remote-first, local fallback) │
│  ─ Set/clear _emergency Event (single source of truth)                      │
│ ─ Local siren: AlarmController.set_level("critical"/"normal") │
│ ─ Update _latest_data snapshot (read by another Publisher thread) │
│ NEVER: send to API, save to SQLite, take GPS │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ _latest_data snapshot (lock)
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌────────────────┐ ┌─────────────────┐ ┌────────────────────────────────────┐
│ LOCATION       │ │ TELEMETRY       │ │ HEARTBEAT                          │
│ PUBLISHER      │ │ PUBLISHER       │ │ PUBLISHER                          │
│                │ │                 │ │                                    │
│ Interval:      │ │ Interval ADAPTIF│ │ Interval:                          │
│ 1800s (fixed) │ │ Normal: 1800s │ │ 300s (fixed) │
│                │ │ Emergency: 600s │ │                                    │
│ 1. Download GPS │ │ │ │ POST /sensors/heartbeat │
│    (A7670E AT  │ │ 1. Save to DB   │ │ → response carries 'commands'      │
│    +CGPSINFO)  │ │    (SQLite)     │ │ → _process_commands()              │
│ 2. Local log │ │ 2. POST │ │ (endpoint 4 ACK, event-driven) │
│ 3. POST        │ │    /sensors/    │ │                                    │
│ /sensors/ │ │ telemetry │ │ Emergency Mode DOES NOT affect │
│ location │ │ → response bring │ │ Heartbeat interval at all │
│                │ │   'config'      │ │                                    │
│ Emergency Mode │ │   (remote thr.) │ └────────────────────────────────────┘
│ NO │ │ │
│ affected       │ │ Awakened        │ ┌────────────────────────────────────┐
│ Same location │ │ INSTANTLY │ │ FLUSH QUEUE │
│ once │ │ entered Emergency │ │ │
└────────────────┘ │ (_telemetry_    │ │ Interval: 120s (independen)        │
                   │  wake Event)    │ │ Retry offline queue FIFO           │
└─────────────────┘ │ (api_queue in SQLite) │
│ Stop when the network drops again, │
                                       │ preserve FIFO order                │
                                       └────────────────────────────────────┘
                                       ┌────────────────────────────────────┐
                                       │ RETENTION                          │
                                       │                                    │
│ Interval: 6 hours │
                                       │ Purge sensor_readings +            │
│ api_queue (finished) + │
│ old location_log (> 3 days) │
                                       └────────────────────────────────────┘
```

---

## 4 Endpoints API

| # | Endpoint | Scheduler | Interval |Notes|
|---|----------|-----------|----------|---------|
| 1 | `POST /sensors/location` | Location Publisher | 1800s (fixed) | GPS is acquired ONLY here |
| 2 | `POST /sensors/telemetry` | Telemetry Publisher | 1800s / 600s (emergency) | Response carries `config` (remote thresholds); data is stored in SQLite FIRST |
| 3 | `POST /sensors/heartbeat` | Heartbeat Publisher | 300s (fixed) | Response carries `commands` |
| 4 | `POST /sensors/commands/ack` |Event-driven from #3| — |Only works if response #3 brings `commands`|

---

## Alur Data — Detail

### Sensor Sampling (Main Thread)
```
Read all sensors → calculate smokeLevel → evaluate threshold (remote-first per-field)
     ↓                                         ↓
Update _latest_data Has any threshold been exceeded?
(pronounced Publisher) ↓ ↓
YES: N times NO:
                                        consecutively?   ↓
                                         ↓           _emergency.clear()
↓ alarm.set_level("normal")
                                      _emergency.set()
                                      alarm.set_level("critical")
                                      _telemetry_wake.set()   ← wake Telemetry NOW
_emergency_immediate_send.set() ← only once
```

### Telemetry Publisher (Thread)
```
Wait for _telemetry_wake OR interval to expire
     ↓
Take _latest_data snapshot (lock)
     ↓
Calculate rainfall_delta (delta from PREVIOUS delivery, not 1 hour sensor window)
     ↓
Save to SQLite FIRST (sensor_readings + full_payload for audit)
     ↓
POST /sensors/telemetry
├── Success → apply remote_config (per-field threshold override)
└── Failed (network/5xx) → entered api_queue (FIFO), flushed separate thread
```

### GPS — Location Publisher
```
Priority fallback (tiap 1800s):
  1. AT+CGNSSPWR=1 → polling AT+CGPSINFO → fix? → source="gps"
2. All attempts failed & have been fixed before → source="gps_cached" (last position)
3. Never fixed it at all → source="config" (static coordinates from .env)
```

### Emergency Mode
- **Entered:** N consecutive readings passed threshold → `_emergency.set()` → Telemetry Publisher
  woken up instantly (Immediate Emergency Send), then switches to 600s interval
- **Exit:** all values ​​return to normal → `_emergency.clear()` → return interval 1800s
- **Not affected:** Location Publisher and Heartbeat Publisher (fixed interval)

### Threshold — Remote-first Per-field
```
resolve_active_thresholds(local, remote_config):
Each field: remote wins if not None, else uses local
windDangerThreshold → ALWAYS local (not in contract API)
```

---

## Alur Offline Queue

```
Network/5xx failed → payload incoming api_queue (SQLite, FIFO)
        ↓
Flush Queue thread (tiap 120s):
Check connectivity → online?
  → YA: flush batch 10 item FIFO
Success → mark sent=1
4xx → mark failed (discard, do not block FIFO)
Break again → stop on that item, FIFO is maintained
→ NO: skip (wait another 120s)

Items are skipped after 10 failures (stale, no FIFO blocking forever).
api_queue (which has sent=1 or attempts≥10) is cleaned by thread retention every 6 hours.
```

---

## Module Responsibilities

| Module |Play files|Responsibility|
|--------|-----------|---------------|
| **sensors/** | `mq2.py`, `mq135.py`, `bme280.py`, `soil.py`, `pressure.py`, `anemometer.py`, `wind_direction.py`, `battery.py`, `flame.py`, `rainfall.py` |Hardware drivers, each has `.read()` → dict. `null_sensor.py` for fallback if sensor fails init. `mock_sensors.py` to `EFWS_RUN_MODE=mock`.|
| **alarm/** | `relay.py`, `siren.py` |`relay.py`: low-level driver GPIO. `AlarmController`: 2 escalation levels (WARNING=pulsing 0.4s/1.6s, CRITICAL=on continuously) from 1 relay. There is no separate buzzer.|
| **communication/** | `sim_detector.py`, `a7670e.py`, `sim7600_legacy.py`, `api_publisher.py` |Auto-detect 4G module (A7670E or SIM7600 via ATI fingerprint, cache to `.sim_cache`). `api_publisher.py`: the only data egress path (REST + offline queue).|
| **database/** | `db_manager.py` |SQLite: tables `sensor_readings`, `api_queue`, `location_log`. Doesn't store alarm levels/thresholds — that's the backend's responsibility.|
| **config/** | `settings.py`, `thresholds.json`, `threshold_resolver.py` |`settings.py`: all env vars centralized. `thresholds.json`: ONLY local fallback for real-time siren. `threshold_resolver.py`: merge remote+local per-field.|
| **main.py** | — |Orchestrator: initialize all modules, run 6 threads, main sensor sampling loop.|

---

## Prinsip Desain

- **Data is never lost:** SQLite written BEFORE sending to API. Failed to send → offline queue → automatic retry.
- **Real-time siren, independent of network:** threshold evaluation & local relay running on main thread, never waiting for response API.
- **Remote-first threshold:** The backend can override the threshold per-field via response telemetry. Devices always have local fallback.
- **Emergencies do not interfere Location/Heartbeat:** only the Telemetry interval changes during an emergency.
- **Sensor failure graceful:** sensor failure init → `NullSensor` (return `None` all fields) → `_exceeds(None, ...)` is always False → does not trigger a false alarm.
- **SIM auto-detect:** one code running on top of A7670E or SIM7600, auto-selected at startup based on ATI's response.
