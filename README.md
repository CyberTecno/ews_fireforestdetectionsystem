# Forest Fire Early Warning System (EFWS)

IoT-based Forest Fire Early Warning System using Raspberry Pi 4.

## Features

- Smoke Detection (MQ-2 + MQ-135, combined smokeLevel)
- Temperature & Humidity Monitoring (BME280)
- Dual Soil Moisture Monitoring (surface + deep probe)
- Water Level Monitoring (submersible pressure sensor, 4-20mA loop)
- Wind Speed Monitoring (RS485 Anemometer)
- Battery Voltage Monitoring (DC 0-25V sensor module)
- 4G Communication (A7670E or SIM7600, auto-detected)
- REST API telemetry with local offline queue (SQLite) — data always
  saved locally first, sent immediately, auto-retried every 2 minutes
  while offline
- Local Alarm System (relay + siren, real-time — not network dependent)
- Solar Powered Operation

## Hardware

- Raspberry Pi 4
- MCP3008 ADC (SPI)
- 1x Logic Level Converter (min. 6-channel)
- MQ-2, MQ-135
- BME280 (I2C)
- 2x Soil moisture probe (surface + deep)
- Submersible pressure sensor (4-20mA loop, water level)
- DC 0-25V voltage sensor module (battery)
- RS485 Anemometer
- A7670E or SIM7600 4G LTE HAT (only one installed at a time)
- LiFePO4 Battery
- Solar Panel
- Relay + Siren (local alarm)

See `docs/Pinout.md` for full wiring reference.

## Project Structure

```text
efws/
├── sensors/        # sensor drivers + mock_sensors.py for testing without hardware
├── communication/  # SIM auto-detect, REST API publisher (offline queue)
├── database/       # SQLite local logger + offline queue
├── alarm/          # relay/siren controller
├── config/         # settings.py + thresholds.json (local siren triggering only)
├── docs/           # Pinout, Architecture, Deployment guides
├── tests/          # per-component + integration tests
├── logs/
└── main.py
```
