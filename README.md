# Forest Fire Early Warning System (EWS)

IoT-based Forest Fire Early Warning System using Raspberry Pi 4.

## Features

- Smoke Detection (MQ-2)
- Air Quality Monitoring (MQ-135)
- Temperature & Humidity Monitoring (BME280)
- Wind Speed Monitoring (RS485 Anemometer)
- Rain Detection
- Water Level Monitoring
- 4G Communication (SIM7600)
- MQTT Data Transmission
- Local Alarm System
- Solar Powered Operation

## Hardware

- Raspberry Pi 4
- MCP3008 ADC
- MQ-2
- MQ-135
- BME280
- RS485 Anemometer
- SIM7600 4G HAT
- LiFePO4 Battery
- Solar Panel

## Project Structure

```text
ews/
├── sensors/
├── communication/
├── database/
├── alarm/
├── logs/
├── config/
└── main.py
