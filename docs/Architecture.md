# EFWS architecture

The Forest Fire Early Warning System (EFWS) samples sensors on a Raspberry Pi, controls a local siren, saves telemetry to SQLite, and publishes data to a REST API over 4G. Local alarm evaluation continues when the network is unavailable.

For hardware connections, see the [pinout](Pinout.md) and [power system](PowerSystem.md). For installation, see the [deployment guide](Deployment.md).

## Hardware overview

| Interface | Connected devices |
| --- | --- |
| I2C | BME280 (`0x76` or `0x77`) and SEN0575 rainfall sensor (`0x1D`) |
| SPI, through MCP3008 | MQ-2 (CH0), MQ-135 (CH1), surface soil probe (CH2), deep soil probe (CH3), pressure sensor (CH4), battery voltage sensor (CH5), flame sensor (CH6) |
| USB | RS485 anemometer and one 4G modem: A7670E or SIM7600 |
| UART | JL-FSX2 wind direction sensor on GPIO14/15 |
| GPIO27 | Relay controlling the 12 V siren |

The 100 W solar panel charges a 12 V LiFePO4 battery through a solar charge controller. A buck converter supplies 5 V to the Pi and other 5 V loads. The siren uses the 12 V battery bus through the relay. See [PowerSystem.md](PowerSystem.md) for the full power path.

> **Analog input:** The MCP3008 runs at 3.3 V. The existing design routes the MQ and soil analog outputs through a four-channel digital logic-level converter. That converter may distort analog readings; validate them during calibration. The pressure, battery, and flame inputs connect directly to the ADC at safe voltage levels.

## Runtime workers

`main.py` runs one main sampling loop and five background workers (six concurrent loops in total). Each worker has its own schedule.

| Loop | Default interval | Responsibility |
| --- | --- | --- |
| Main sampling loop | `EFWS_READ_INTERVAL` (180 s) | Read sensors, calculate `smokeLevel`, evaluate active thresholds, control the siren, and update the shared `_latest_data` snapshot. |
| Location publisher | `EFWS_LOCATION_INTERVAL_SEC` (1,800 s) | Obtain a GPS fix or fallback location, log it locally, and POST `/sensors/location`. |
| Telemetry publisher | `EFWS_TELEMETRY_INTERVAL_SEC` (1,800 s); `EFWS_EMERGENCY_TELEMETRY_INTERVAL_SEC` (600 s) during an emergency | Save the latest reading to SQLite, POST `/sensors/telemetry`, and apply remote threshold configuration from the response. Wakes immediately when an emergency starts. |
| Heartbeat publisher | `EFWS_HEARTBEAT_INTERVAL_SEC` (300 s) | POST `/sensors/heartbeat`, process returned commands, and acknowledge them. |
| Offline queue worker | `EFWS_CONNECTIVITY_CHECK_SEC` (120 s) | Retry queued API payloads in FIFO order when connectivity returns. |
| Retention worker | 6 hours | Remove old sensor readings, completed or expired queue entries, and old location logs. |

The sampling loop does not send network requests, write telemetry to SQLite, or acquire GPS. Publishers use a locked snapshot of the latest sensor data.

## API requests

| Endpoint | Trigger | Response used for |
| --- | --- | --- |
| `POST /sensors/location` | Location publisher | Location delivery. |
| `POST /sensors/telemetry` | Telemetry publisher | `config` with remote threshold overrides. |
| `POST /sensors/heartbeat` | Heartbeat publisher | `commands` for the device. |
| `POST /sensors/commands/ack` | A command received in a heartbeat response | Command acknowledgment. |

The acknowledgment endpoint is event-driven; it has no separate timer.

## Sensor and alarm flow

1. The main loop reads each sensor and calculates `smokeLevel` from MQ-2 and MQ-135 readings.
2. It resolves each active threshold from the remote configuration when available, otherwise from the local fallback. `windDangerThreshold` remains local.
3. After the configured number of consecutive critical readings, it sets `_emergency`, activates the critical siren level, and wakes the telemetry publisher for an immediate send.
4. When readings return to normal, it clears `_emergency`, returns the siren to normal, and restores the standard telemetry interval.
5. A sensor that fails initialization uses `NullSensor`; missing values do not by themselves trigger an alarm.

The heartbeat and location intervals stay fixed during an emergency. Siren control runs locally and does not wait for API responses.

## Telemetry and offline queue

1. The telemetry publisher copies `_latest_data` under a lock and calculates rainfall change since the previous telemetry delivery.
2. It saves the reading and full API payload to SQLite before sending.
3. On a network or server failure, it adds the payload to `api_queue`.
4. The queue worker checks connectivity every 120 seconds and retries a batch of up to 10 items in FIFO order. Successful items are marked sent. A 4xx response is marked failed so it cannot block later items; a renewed connection failure stops the batch.
5. Items are skipped after 10 failures. The retention worker cleans completed or expired entries every six hours.

The database stores `sensor_readings`, `api_queue`, and `location_log`. It does not store alarm levels or the backend's threshold decisions.

## Location fallback

On each location cycle, the modem attempts a GNSS fix. A successful fix is sent with source `gps`. If the current attempt fails after a previous fix, the cached position is sent as `gps_cached`. If the device has never obtained a fix, coordinates from `.env` are sent as `config`.

## Module responsibilities

| Path | Responsibility |
| --- | --- |
| `sensors/` | Sensor drivers, `NullSensor` fallback, and mock sensors for `EFWS_RUN_MODE=mock`. |
| `alarm/` | Relay driver and siren controller. Warning pulses the relay; critical keeps it on continuously. |
| `communication/` | A7670E/SIM7600 detection, modem support, REST publishing, and offline queue handling. |
| `database/` | SQLite readings, queue, and location log. |
| `config/` | Environment settings, local fallback thresholds, and per-field threshold resolution. |
| `main.py` | Initializes components and coordinates the six runtime loops. |
