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
  │ MCP3008 ADC     │                          │  6 threads; 4 API endpoints │
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
  └─────────────────┘                           [120 dB]       REST API Backend
```

---

## Thread Model (6 Threads)

`main.py` starts six independent threads.
A failure in one thread does not stop the others.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MAIN THREAD — sensor sampling every SENSOR_READ_INTERVAL_SEC               │
│ • Call .read() on every sensor driver.                                      │
│ • Calculate smokeLevel from weighted MQ-2 and MQ-135 readings.             │
│ • Evaluate each active threshold: remote first, local fallback.            │
│ • Set/clear _emergency Event (single source of truth).                     │
│ • Set local siren to "critical" or "normal" via AlarmController.            │
│ • Update _latest_data for the publisher threads.                           │
│ NEVER send to the API, write SQLite, or fetch GPS here.                    │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │ locked _latest_data snapshot
                  ┌──────────────────┼─────────────────────┐
                  ▼                  ▼                     ▼
┌──────────────────────────┐ ┌──────────────────────────┐ ┌──────────────────────────┐
│ LOCATION PUBLISHER       │ │ TELEMETRY PUBLISHER      │ │ HEARTBEAT PUBLISHER      │
│ Fixed interval: 1,800 s  │ │ Adaptive interval:       │ │ Fixed interval: 300 s    │
│                          │ │ normal 1,800 s;          │ │                          │
│ 1. Get GPS (A7670E       │ │ emergency 600 s.         │ │ POST /sensors/heartbeat  │
│    AT+CGPSINFO).         │ │ 1. Save to SQLite.       │ │ Response: 'commands'     │
│ 2. Log location locally. │ │ 2. POST /sensors/        │ │ → _process_commands()    │
│ 3. POST /sensors/        │ │    telemetry.            │ │ → event-driven ACK via   │
│    location.             │ │ Response: 'config' with  │ │   endpoint 4.            │
│                          │ │ remote thresholds.       │ │                          │
│ Emergency mode does not  │ │ Wake immediately on      │ │ Emergency mode does not  │
│ change this schedule.    │ │ emergency entry via      │ │ change this schedule.    │
└──────────────────────────┘ │ _telemetry_wake Event.   │ └──────────────────────────┘
                             └──────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ FLUSH QUEUE — independent interval: 120 s                                  │
│ Retry offline api_queue in SQLite in FIFO order. Stop when connectivity    │
│ drops again and preserve FIFO order.                                        │
└─────────────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────────┐
│ RETENTION — every 6 hours                                                   │
│ Purge old sensor_readings, sent api_queue entries, and location_log rows    │
│ older than 3 days.                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Four API Endpoints

| # | Endpoint | Scheduler | Interval |Notes|
|---|----------|-----------|----------|---------|
| 1 | `POST /sensors/location` | Location Publisher | 1800s (fixed) | GPS is acquired ONLY here |
| 2 | `POST /sensors/telemetry` | Telemetry Publisher | 1800s / 600s (emergency) | Response carries `config` (remote thresholds); data is stored in SQLite FIRST |
| 3 | `POST /sensors/heartbeat` | Heartbeat Publisher | 300s (fixed) | Response carries `commands` |
| 4 | `POST /sensors/commands/ack` |Event-driven from #3| — |Only works if response #3 brings `commands`|

---

## Data Flow — Details

### Sensor Sampling (Main Thread)
```
Read all sensors → calculate smokeLevel → evaluate active thresholds
      │                                          │
      ▼                                          ▼
Update _latest_data                   Has any threshold been exceeded?
(publisher snapshot)                    ├─ No → clear _emergency
                                        │        alarm.set_level("normal")
                                        └─ Yes, N consecutive readings?
                                                 ├─ No → keep sampling
                                                 └─ Yes → set _emergency
                                                          alarm.set_level("critical")
                                                          _telemetry_wake.set()  (send now)
                                                          _emergency_immediate_send.set()
                                                          (once on entry)
```

### Telemetry Publisher (Thread)
```
Wait for _telemetry_wake OR the scheduled interval
    ↓
Copy _latest_data under a lock
    ↓
Calculate rainfall_delta since the PREVIOUS telemetry delivery
(not the sensor's one-hour rainfall window)
    ↓
Save sensor_readings and full_payload to SQLite FIRST
    ↓
POST /sensors/telemetry
    ├─ Success → apply remote_config overrides field by field
    └─ Network/5xx failure → enqueue in api_queue (FIFO)
                             for the separate retry worker
```

### GPS — Location Publisher
```
Location fallback every 1,800 seconds:
  1. Enable GNSS with AT+CGNSSPWR=1; poll AT+CGPSINFO.
     Valid fix → source="gps".
  2. No current fix, but an earlier fix exists
     → source="gps_cached" (last known position).
  3. No fix has ever been obtained
     → source="config" (static coordinates from .env).
```

### Emergency Mode
- **Entry:** N consecutive readings passed threshold → `_emergency.set()` → Telemetry Publisher
  woken up instantly (Immediate Emergency Send), then switches to 600s interval
- **Exit:** all values return to normal → `_emergency.clear()` → return interval 1800s
- **Not affected:** Location Publisher and Heartbeat Publisher (fixed interval)

### Thresholds — Remote Values First, Field by Field
```
resolve_active_thresholds(local, remote_config):
  For each field, use the remote value when it is not None;
  otherwise use the local fallback.
  windDangerThreshold always stays local (not in the API contract).
```

---

## Offline Queue Flow

```
Network/5xx failure → add payload to api_queue (SQLite, FIFO)
    ↓
Queue worker every 120 seconds:
  Check connectivity.
  ├─ Online → retry up to 10 items in FIFO order
  │           ├─ Success → mark sent=1
  │           ├─ 4xx → mark failed; do not block later items
  │           └─ Connection drops → stop on that item; retain FIFO order
  └─ Offline → wait for the next check

Skip items after 10 failed attempts so stale entries cannot block the queue.
Every six hours, retention removes sent entries and entries with attempts ≥ 10.
```

---

## Module Responsibilities

| Module | Files | Responsibility |
|--------|-----------|---------------|
| **sensors/** | `mq2.py`, `mq135.py`, `bme280.py`, `soil.py`, `pressure.py`, `anemometer.py`, `wind_direction.py`, `battery.py`, `flame.py`, `rainfall.py` |Hardware drivers, each has `.read()` → dict. `null_sensor.py` for fallback if sensor fails init. `mock_sensors.py` to `EFWS_RUN_MODE=mock`.|
| **alarm/** | `relay.py`, `siren.py` |`relay.py`: low-level driver GPIO. `AlarmController`: 2 escalation levels (WARNING=pulsing 0.4s/1.6s, CRITICAL=on continuously) from 1 relay. There is no separate buzzer.|
| **communication/** | `sim_detector.py`, `a7670e.py`, `sim7600_legacy.py`, `api_publisher.py` |Auto-detect 4G module (A7670E or SIM7600 via ATI fingerprint, cache to `.sim_cache`). `api_publisher.py`: the only data egress path (REST + offline queue).|
| **database/** | `db_manager.py` |SQLite: tables `sensor_readings`, `api_queue`, `location_log`. Doesn't store alarm levels/thresholds — that's the backend's responsibility.|
| **config/** | `settings.py`, `thresholds.json`, `threshold_resolver.py` |`settings.py`: all env vars centralized. `thresholds.json`: ONLY local fallback for real-time siren. `threshold_resolver.py`: merge remote+local per-field.|
| **main.py** | — |Orchestrator: initialize all modules, run 6 threads, main sensor sampling loop.|

---

## Design Principles

- **Data is never lost:** Write to SQLite before sending to the API. If delivery fails, enqueue the payload for automatic retry.
- **Real-time siren, independent of network:** threshold evaluation & local relay running on main thread, never waiting for API responses.
- **Remote-first threshold:** The backend can override each threshold in a telemetry response; the device keeps a local fallback for every field.
- **Emergencies do not interfere Location/Heartbeat:** only the telemetry interval changes during an emergency.
- **Sensor failure graceful:** sensor failure init → `NullSensor` (return `None` all fields) → `_exceeds(None, ...)` is always False → does not trigger a false alarm.
- **SIM auto-detect:** one code running on top of A7670E or SIM7600, auto-selected at startup based on ATI's response.
