# EFWS Architecture Overview

```
                         ┌───────────────────────────┐
                         │   Solar 80-100W + LiFePO4  │
                         │   + 18650 UPS Power HAT    │
                         └─────────────┬─────────────┘
                                       5V/12V
                                        │
┌──────────────┐   I2C   ┌─────────────▼─────────────┐   GPIO    ┌────────────┐
│ BME280       │◄───────►│                            │──────────►│ Relay 5V   │──►12V Siren
│ ADS1115 ADC  │◄───────►│      Raspberry Pi 4        │           └────────────┘
│ (MQ2/MQ135/  │         │      (main.py orchestrator)│   GPIO    ┌────────────┐
│  Soil probe) │         │                            │──────────►│ Buzzer     │
└──────────────┘         │                            │           └────────────┘
┌──────────────┐  GPIO   │                            │
│ Flame sensor │◄───────►│                            │
└──────────────┘         │                            │
┌──────────────┐  USB    │                            │  USB/UART  ┌─────────────┐
│ RS485        │◄───────►│                            │───────────►│ SIM7600E-H  │──► 4G Network
│ Anemometer   │         │                            │            │ + outdoor   │
└──────────────┘         └─────────────┬──────────────┘            │ antenna     │
                                        │                          └─────────────┘
                          ┌─────────────┴─────────────┐
                          │   Evaluation against        │
                          │   config/thresholds.json    │
                          └─────────────┬─────────────┘
                     ┌──────────────────┼──────────────────┐
                     ▼                  ▼                  ▼
              SQLite (local log)   MQTT (JSON publish)  Telegram (critical alert)
```

## Module responsibilities
- **sensors/**: one driver class per physical sensor, each exposes a `.read()` returning a dict.
- **alarm/**: `relay.py` + `buzzer.py` are low-level GPIO drivers; `siren.py` (`AlarmController`)
  composes them into a two-tier warning/critical escalation policy.
- **communication/**: `mqtt_client.py` publishes JSON to the broker, `sim7600.py` is a diagnostic
  AT-command helper for the 4G HAT, `telegram.py` is the backup alert channel.
- **database/**: `db_manager.py` logs every reading and every alarm event locally, so data survives
  4G outages and can be backfilled/synced later if needed.
- **config/**: `settings.py` centralizes every pin/address/credential; `thresholds.json` centralizes
  every warning/critical boundary so they can be tuned without touching code.
- **main.py**: ties it all together in a read -> evaluate -> alarm -> publish -> log loop.
