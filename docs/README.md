# EFWS documentation

These guides cover the Raspberry Pi hardware, deployment, and runtime behavior of the Forest Fire Early Warning System.

## Start here

1. Review the [sensor specifications](SensorSpecification.md) to identify the modules and their voltage requirements.
2. Check the [power system](PowerSystem.md) and [pinout](Pinout.md) before wiring the device.
3. Follow the [deployment guide](Deployment.md) to configure Raspberry Pi OS, test sensors, and install the services.
4. If you use a SIM7600E-H modem, follow the [4G connection guide](Setup-SIM7600.md).

## Reference

| Guide | Contents |
| --- | --- |
| [Architecture](Architecture.md) | Runtime loops, API endpoints, alarm flow, and offline queue. |
| [Sensor specifications](SensorSpecification.md) | Sensor and supporting hardware specifications. |
| [Pinout and wiring](Pinout.md) | GPIO, MCP3008 channel map, sensor connections, and pre-power checklist. |
| [Power system](PowerSystem.md) | Solar charging, battery, voltage rails, and power budget. |
| [Deployment](Deployment.md) | Installation, configuration, service setup, and troubleshooting. |
| [SIM7600E-H setup](Setup-SIM7600.md) | 4G primary connection with Wi-Fi fallback. |

The [project README](../README.md) gives a brief overview of the application.
