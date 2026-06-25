# EFWS Wiring & Pinout Reference

## Power architecture
```
Solar Panel 80-100W ──> PV Pi HAT (5V regulator + MPPT/charge) ──> 12V LiFePO4 pack
                                                                  └─> 18650 Li-ion bank (via UPS Power HAT)
UPS Power HAT (18650 expansion board) ──> stacks on RPi4 40-pin header ──> 5V to RPi4
12V LiFePO4 pack ──> directly powers: 12V Siren (through relay), RS485 anemometer (if 12V variant)
```
Keep the UPS HAT, SIM7600 HAT, and any other I2C add-ons on separate I2C addresses (UPS HATs commonly
use a fuel-gauge IC like the INA219/MAX17048 on the I2C bus too) - run `i2cdetect -y 1` after stacking
everything to confirm there's no address collision with BME280 (0x76) or ADS1115 (0x48) before wiring sensors.

## Digital / Analog sensors -> Raspberry Pi 4 (BCM GPIO numbering)

| Component                         | Interface | RPi4 Pin (BCM)        | Physical Pin | Notes |
|-----------------------------------|-----------|------------------------|---------------|-------|
| BME280 (Temp/Humidity/Pressure)   | I2C       | SDA1 (GPIO2), SCL1 (GPIO3) | Pin 3, Pin 5 | Address 0x76 (or 0x77) |
| ADS1115 ADC module                | I2C       | SDA1 (GPIO2), SCL1 (GPIO3) | Pin 3, Pin 5 | Address 0x48, shared I2C bus with BME280 |
| ── MQ-2 (Smoke/Gas)  -> ADS1115 A0 | Analog    | via ADC channel 0      | -             | MQ-2 AOUT -> ADS1115 A0 |
| ── MQ-135 (Air Quality) -> ADS1115 A1 | Analog | via ADC channel 1      | -             | MQ-135 AOUT -> ADS1115 A1 |
| ── Soil Moisture Probe -> ADS1115 A2  | Analog | via ADC channel 2      | -             | Probe AOUT -> ADS1115 A2 |
| IR Flame Sensor (LM393 digital out)| Digital  | GPIO17                 | Pin 11        | Active-LOW on most modules |
| 5V Relay Module (drives 12V siren)| Digital   | GPIO27                 | Pin 13        | Relay COM/NO wired to 12V siren + battery |
| Active Buzzer (warning tier)      | Digital   | GPIO22                 | Pin 15        | Direct drive, no relay needed |
| Status LED (optional)             | Digital   | GPIO23                 | Pin 16        | Heartbeat indicator |
| RS485 Anemometer                  | USB-RS485 | USB port -> /dev/ttyUSB0 | -           | RPi4 has no native RS485; use a USB-RS485 (MAX485) adapter |
| SIM7600E-H 4G HAT                 | UART/USB  | stacks on 40-pin header, AT port usually /dev/ttyUSB2 | - | Confirm exact /dev/ttyUSBx with `ls /dev/ttyUSB*` after boot |

## Power wiring summary

| Load                  | Voltage | Source                                  |
|------------------------|---------|------------------------------------------|
| Raspberry Pi 4 + HATs  | 5V      | UPS Power HAT (18650 bank, solar-charged)|
| MQ-2 / MQ-135 heater   | 5V      | Pi 5V rail (check current draw - MQ sensors pull ~150mA each, prefer powering from UPS HAT 5V rail not Pi GPIO 5V pin directly if total draw is high) |
| BME280, ADS1115, Soil probe | 3.3V or 5V (module-dependent) | Pi 3.3V/5V rail |
| Flame sensor module    | 3.3V/5V | Pi rail (check module spec)              |
| Relay module coil      | 5V      | Pi 5V rail (logic side only)             |
| 12V Siren              | 12V     | LiFePO4 pack, switched THROUGH the relay's NO/COM contacts - never wire 12V directly to the Pi |
| RS485 Anemometer       | 12V or 5V (model-dependent) | LiFePO4 pack or Pi 5V, check your unit's spec |

**Critical safety notes:**
- The 12V siren must be powered from the LiFePO4 pack, switched by the relay's dry contacts (COM/NO) -
  never connect 12V into any RPi GPIO or 5V pin.
- Add a flyback/snubber diode across the relay coil if your module doesn't already have one onboard
  (most pre-built relay modules already include this).
- Use the cable glands for all sensor cables penetrating the IP65 box; keep the MQ-2/MQ-135 sensors
  ventilated but shielded from direct rain ingress (a small vented cap helps gas exchange while
  blocking water).
- Mount the heat sink + fan on the RPi4 SoC; in an IP65 sealed box in direct sun, thermal buildup is
  the most common failure mode for fanless setups - confirm fan airflow path inside the box, or add a
  passive convection vent with a hydrophobic membrane if a fan is impractical in a sealed enclosure.

## I2C / GPIO conflict check
Before final wiring, run:
```bash
i2cdetect -y 1
```
You should see entries for `0x48` (ADS1115) and `0x76` (BME280). If your UPS HAT or SIM7600 HAT also
use I2C for battery/status monitoring, confirm their address doesn't collide with these two.
