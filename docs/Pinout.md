# Pinout and wiring

This guide maps the Raspberry Pi GPIO pins, MCP3008 inputs, sensors, modem, relay, and siren. Check the [power guide](PowerSystem.md) before wiring and the [sensor specifications](SensorSpecification.md) for device ratings.

EFWS uses one relay and one siren. The local alarm controller pulses the relay for warnings and holds it on for critical alarms. The backend maintains the authoritative alarm record.

> **Corrections from the Indonesian source:** MCP3008 inputs are numbered CH0–CH7 in `config/settings.py`; the source guide labels several of them one higher. The source also reverses the Pi's UART TX/RX labels. This guide follows the application channel settings and the [Raspberry Pi UART pinout](https://www.raspberrypi.com/documentation/computers/configuration.html#primary-and-secondary-uarts). Verify wiring before powering the unit.

---

## 1. Raspberry Pi 4 pins (BCM numbering)

|Function| GPIO (BCM) |Physical Pins|Information|
|--------|-----------|-----------|------------|
| SPI SCLK (MCP3008) | GPIO11 | Pin 23 | Clock SPI |
| SPI MISO (MCP3008) | GPIO9  | Pin 21 |Data from MCP3008|
| SPI MOSI (MCP3008) | GPIO10 | Pin 19 |Data to MCP3008|
| SPI CE0  (MCP3008) | GPIO8  | Pin 24 | Chip Select |
| I2C SDA (BME280 + Rainfall) | GPIO2  | Pin 3  |Data I2C, bus shared|
| I2C SCL (BME280 + Rainfall) | GPIO3  | Pin 5  |Clock I2C, bus is shared|
| UART TXD (Wind Direction) | GPIO14 | Pin 8 | Send to the sensor's RX (green; rarely used) |
| UART RXD (Wind Direction) | GPIO15 | Pin 10 | Receive from the sensor's TX (yellow) |
|Siren Relay (output)| GPIO27 | Pin 13 |To IN relay 5V|
| Status LED (output, optional) | GPIO23 | Pin 16 | Heartbeat indicator |
| 5V Rail | — | Pin 2 & 4 |Power LLC HV (not from here if the current is large)|
| 3.3V Rail | — | Pin 1 & 17 |Power LLC LV, MCP3008 VDD/VREF, BME280, Rainfall, Wind Direction, Battery sensor (logic side), Flame sensor|
| GND | — | Pin 6, 9, 14, 20, 25, 30, 34, 39 | Common ground |

Enable the interfaces:

```bash
sudo raspi-config
# Interface Options → SPI → Yes
# Interface Options → I2C → Yes
# Interface Options → Serial Port → login shell via serial: No, hardware serial: Yes
```
Then add `dtoverlay=disable-bt` in `/boot/config.txt` and
`sudo systemctl disable hciuart`. The wind direction section below explains why.

---

## 2. BME280 and rainfall sensor (shared I2C bus)

Both sensors connect directly to the Pi's I2C bus, without the MCP3008 or level converter. They share SDA and SCL but use different addresses.

### BME280 (ambient temperature, humidity, and pressure)

| Pin BME280 |Connect to|
|-----------|-----------|
| VIN | Pi 3.3V |
| GND | Common ground |
| SCL | GPIO3 (Pin 5) |
| SDA | GPIO2 (Pin 3) |

I2C address: `0x76` (or `0x77` depending on the module jumper soldering).

### DFRobot Gravity rainfall sensor (SEN0575)

| Pin sensor |Connect to|
|-----------|-----------|
| VCC | Pi 3.3V |
| GND | Common ground |
| SCL |GPIO3 (Pin 5) — **same as BME280**|
| SDA |GPIO2 (Pin 3) — **same as BME280**|

The rainfall sensor uses address `0x1D` (`RAINFALL_I2C_ADDRESS` in `config/settings.py`). The BME280 uses `0x76` or `0x77`, so no I2C multiplexer is needed.

```bash
i2cdetect -y 1     # TWO addresses should appear: 0x76 (BME280) and 0x1D (Rainfall)
python3 tests/test_bme280.py
python3 tests/test_rainfall.py
```

---

## 3. MCP3008 wiring

| Pin MCP3008 |Connect to|Notes|
|-------------|-----------|---------|
| VDD (pin 16) | Pi 3.3V |**DO NOT 5V**|
| VREF (pin 15) | Pi 3.3V | ADC scale 0-3.3V = raw 0-1023 |
| AGND (pin 14) | Common ground | |
| CLK (pin 13)  | GPIO11 (SCLK) | |
| DOUT (pin 12) | GPIO9 (MISO)  | |
| DIN (pin 11)  | GPIO10 (MOSI) | |
| CS/SHDN (pin 10) | GPIO8 (CE0) | |
| DGND (pin 9)  | Common ground | |
| CH0–CH3 |See §4 — via LLC| MQ-2, MQ-135, Soil Surface, Soil Deep |
| CH4 |Pressure sensor, **directly without LLC**|Via R_BURDEN 100Ω|
| CH5 |Battery/voltage sensor, **directly without LLC**|Native 3.3V signal|
| CH6 |Flame sensor (AO), **directly without LLC**|Native 3.3V signal|
| CH7 | Spare; not wired | The level converter's four channels are used on CH0–CH3 |

Verification: `ls /dev/spidev*` → should appear `/dev/spidev0.0`

---

## 4. MCP3008 channel map and logic-level converter

The four-channel level converter in the original design is intended for digital signals. It does not translate a continuous analog voltage linearly.

> **Calibration warning:** MQ-2, MQ-135, and both soil probes are currently routed through this converter. Their ADC readings may jump or distort instead of following the sensor voltage smoothly. Verify their behavior during calibration. The pressure, battery, and flame inputs bypass the converter because their outputs stay within the MCP3008's 3.3 V input range.

| LLC channel | Sensor side (5 V) | MCP3008 side (3.3 V) | Signal |
|-----|---------------------------|------------------------------|---------|
| CH1 | MQ-2 **AOUT** | **MCP3008 CH0** | Smoke/gas analog |
| CH2 | MQ-135 **AOUT** | **MCP3008 CH1** |Air quality analog|
| CH3 | Soil Surface **AOUT** | **MCP3008 CH2** | Moisture at 0–30 cm |
| CH4 | Soil Deep **AOUT** | **MCP3008 CH3** | Moisture at 30–60 cm |

All four converter channels are assigned. The pressure, battery, and flame signals bypass it, as described below.

### Level converter power connections

```
LLC:
HV pin ←── 5V (from buck converter / Pi pin 2/4)
LV pin ←── 3.3V (from Pi pin 1/17)
  GND HV   ←── Common ground
  GND LV   ←── Common ground
```

---

## 5. Sensor wiring details

### MQ-2 (Smoke / Combustible Gas)
| Pin sensor |Connect to|
|-----------|-----------|
| VCC |5V (directly from the source, not from the Pi GPIO 5V)|
| GND | Common ground |
| AOUT | LLC **CH1** → MCP3008 **CH0** |

> Heater ~150mA — power directly from the buck converter, not from the Pi GPIO 5V.

### MQ-135 (Air Quality)
| Pin sensor |Connect to|
|-----------|-----------|
| VCC |5V (direct from source)|
| GND | Common ground |
| AOUT | LLC **CH2** → MCP3008 **CH1** |

### Soil Moisture Probe — Surface (0-30cm)
| Pin probe |Connect to|
|----------|-----------|
| VCC | 5V |
| GND | Common ground |
| AOUT | LLC **CH3** → MCP3008 **CH2** |

### Soil Moisture Probe — Deep (30-60cm)
| Pin probe |Connect to|
|----------|-----------|
| VCC | 5V |
| GND | Common ground |
| AOUT | LLC **CH4** → MCP3008 **CH3** |

> Mandatory calibration per probe (see `sensors/soil.py`): dry_raw in dry air, wet_raw submerged in water.

### Submersible pressure sensor — 4–20 mA loop, direct to ADC

This two-wire sensor produces a 4–20 mA current loop. A 100 Ω burden resistor (`PRESSURE_BURDEN_OHM` in `config/settings.py`) converts that current to 0.4–2.0 V, within the MCP3008's 3.3 V input range. Connect the resistor junction directly to CH4; do not route it through the level converter.

| Connection | Wire to |
| --- | --- |
| 12–24 V loop supply (+) | Sensor loop V+ |
| Sensor loop return | Top of the 100 Ω burden resistor |
| Burden resistor top | MCP3008 CH4 (0.4–2.0 V) |
| Burden resistor bottom | Common ground and loop supply (−) |

| Connection point |Connect to|
|-------|-----------|
| Loop V+ |PSU 12-24V (+) — **not** from Pi/buck 5V converter|
|Exit loop (after sensor)|Top end R_BURDEN (100Ω)|
| Bottom end of R_BURDEN | Common ground and PSU (−) |
| Sensor/resistor junction |**DIRECT** to MCP3008 **CH4** (without LLC)|

**Why 100 Ω?**
- 4mA × 100Ω = **0.4V** → “empty” level (0m)
- 20mA × 100Ω = **2.0V** → “full” level (`PRESSURE_RANGE_M`, default 3m — adjust your sensor datasheet)

The 0.4–2.0 V signal stays below the 3.3 V reference throughout the 4–20 mA range.

The conversion formula is in `sensors/pressure.py`. **Customize** `EFWS_PRESSURE_RANGE_M`
in `.env` with the depth/pressure range of your physical sensor (many variants: 0–3 m,
0–5 m, 0–10 m). The API payload sends `waterLevel` (meters)
and `pressure` (bar, hydrostatic conversion).

### DC voltage sensor module (battery) — direct to ADC

The module contains a fixed 1:5 resistor divider. Its output connects directly to MCP3008 CH5. Although the module may be labeled \"0–25 V,\", that full range assumes a 5 V ADC reference. With this project's 3.3 V MCP3008 reference, the maximum measurable input is 16.5 V. The documented 14.4 V battery maximum is below that limit.

This module has **5 connection points, on two different sides** — don't confuse them:

| Module pins | Side |Connect to|
|-----------|------|-----------|
| **+** |Output/logic (to Pi)|3.3V Pi (Pin 1 or 17)|
| **−** | Output/logic (to Pi) | Common ground |
| **S** |Output/logic (to Pi)|**DIRECT** to MCP3008 **CH5** (without LLC)|
| **anode / IN+** | Input (measured) | Battery+ (12 V LiFePO4, maximum 14.4 V) |
| **cathode / IN−** |Input (measured)| Terminal Battery− |

The conversion formula is in `sensors/battery.py`. Set `EFWS_BATTERY_MAX_V` and `EFWS_BATTERY_MIN_V` in `.env` for your battery. Their current defaults are 14.4 V and 10.7 V.

### Flame sensor (analog output) — direct to ADC

| Pin sensor |Connect to|
|-----------|-----------|
| VCC |As per module datasheet (usually 3.3-5V)|
| GND | Common ground |
| AO | Directly to MCP3008 **CH6** (without LLC) |

The documented AO signal is within the 3.3 V ADC range. The default `FLAME_AO_THRESHOLD_V` of 1.65 V is a placeholder; follow the calibration notes in `sensors/flame.py` before deployment. This implementation reads AO through the MCP3008 and does not use the sensor's digital output.

### RS485 Anemometer (Modbus RTU) — Wind Speed
|Connection|Connect to|
|---------|-----------|
| A (D+) | USB-RS485 converter terminal A |
| B (D−) | USB-RS485 converter terminal B |
| VCC |12V or 5V according to unit datasheet|
| GND | Common ground |

USB-RS485 → USB Pi port → appears as `/dev/ttyUSB0`. **No need for LLC.**
Modbus parameters **CONFIRMED** (proven successful in the field):
Port `/dev/ttyUSB0`, Slave ID `2`, Baudrate `9600` — already default in
`config/settings.py` (`ANEMOMETER_PORT`/`ANEMOMETER_SLAVE_ID`/`ANEMOMETER_BAUDRATE`).

### Wind Direction — UART (GPIO14/15), NOT via MCP3008/LLC

| Cable | Connect to |
|-------|-----------|
| Red (VCC) | Supply specified by the installed sensor module; the Indonesian source conflicts between 3.3 V and 5 V |
| Black (GND) | GND |
| Yellow (sensor TX) | Pi RXD: GPIO15 / physical pin 10 |
| Green (sensor RX) | Pi TXD: GPIO14 / physical pin 8 |

The sensor sends text lines in the form `*<code>#` over `/dev/serial0`. Codes 1–8 represent N, NE, E, SE, S, SW, W, and NW. The default baud rate is 9,600 (`EFWS_WIND_DIR_BAUD`).

> The Pi's UART input is 3.3 V tolerant. If the sensor transmits at 5 V, use an appropriate level converter before connecting its TX wire to GPIO15.

> **Serial setup:** On Raspberry Pi 4, Bluetooth can occupy the stable PL011 UART, leaving GPIO14/15 on the clock-sensitive mini-UART. To give this sensor a stable serial port:
> 1. `sudo raspi-config` → Interface Options → Serial Port → login shell
>    via serial: **No**, hardware serial port: **Yes**.
> 2. Add `dtoverlay=disable-bt` in `/boot/config.txt`, then
>    `sudo systemctl disable hciuart`, then reboot.
> 3. After rebooting, verify that `/dev/serial0` points to PL011.
>
> If this step has not been done, the sensor may "appear" to be running
> but the data is random/intermittent.

### A7670E OR SIM7600 (choose one)

No need for different wiring between the two — **just install one of the modules**,
`communication/sim_detector.py` will auto-detect which ones are installed
(`AT+CGNSSPWR` → A7670E, `AT+CGPS` → SIM7600) and the software adjusts itself.

|Connection| Detail |
|---------|--------|
|Power|Fits HAT board (usually 5V from Pi or separate 3.7-4.2V Li-ion)|
| Data |USB to Pi — appears as multiple `/dev/ttyUSBx`|
| LTE antenna |Must|
| GNSS antenna |Must be separate|
| SIM card |Install before power on|

```bash
ls /dev/ttyUSB*
python3 tests/test_sim_detector.py   # confirm which module is detected
```

### 5V Relay → 12V Siren

| Relay control connection | Wire to |
| --- | --- |
| Relay IN | Pi GPIO27 (3.3 V control signal; verify relay input compatibility) |
| Relay VCC | 5 V supply |
| Relay GND | Common ground |

| Siren power connection | Wire to |
| --- | --- |
| Relay COM | Battery+ (12 V) |
| Relay NO | Siren positive terminal |
| Siren negative terminal | Battery− |

> ⚠️ The siren's 12V line should **never** touch any of the Pi pins.
> There is no separate buzzer — this one relay handles 2 levels of escalation
> (WARNING = slowly pulsing, CRITICAL = continuously on), see `alarm/siren.py`.

---

## 6. Signal path summary

| Device | Path to Raspberry Pi |
| --- | --- |
| MQ-2, MQ-135, surface and deep soil probes | Analog output → four-channel level converter → MCP3008 CH0–CH3 → SPI |
| Submersible pressure sensor | 4–20 mA loop → 100 Ω burden resistor → MCP3008 CH4 → SPI |
| Battery voltage sensor | Sensor output → MCP3008 CH5 → SPI |
| Flame sensor | Analog output → MCP3008 CH6 → SPI |
| BME280 and SEN0575 rainfall sensor | Shared I2C bus, addresses 0x76/0x77 and 0x1D |
| RS485 anemometer | USB-RS485 converter |
| Wind direction sensor | UART on GPIO14/15 |
| A7670E or SIM7600 modem | USB |
| Siren | GPIO27 → relay control; 12 V battery bus → relay contacts → siren |

The main loop evaluates alarms locally. The telemetry publisher saves a reading to SQLite before sending it to the API. See [Architecture.md](Architecture.md) for the runtime flow.

---

## 7. Power Supply for Each Load

| Load |Voltage|Source|Notes|
|-------|---------|--------|---------|
| Raspberry Pi 4 | 5 V | Buck converter output | Supply through USB-C with a suitable regulated source |
| MCP3008 VDD/VREF | 3.3V | Pi 3.3V rail | |
| BME280 | 3.3V | Pi 3.3V rail |I2C directly, without LLC|
| Rainfall SEN0575 | 3.3V | Pi 3.3V rail |The bus is the same as BME280|
| LLC LV | 3.3V | Pi 3.3V rail |Only for 4 channels: MQ-2/MQ-135/Soil x2|
| LLC HV | 5V | Buck converter / Pi 5V rail |Only for 4 channels: MQ-2/MQ-135/Soil x2|
|MQ-2 / MQ-135 heaters| 5V |Direct buck converter|~150mA each|
| Soil probe ×2 |5V or 3.3V|According to the probe datasheet| |
| Submersible pressure sensor | 12-24V (loop) |**PSU is separate**, not from Pi/buck 5V|Loop-powered, R_BURDEN 100Ω, direct to CH4|
| Battery voltage module | Battery+/Battery− measurement terminals; 3.3 V/GND on the documented Pi-side pins | Pi 3.3 V rail for the Pi-side pins | Sensor output `S` goes directly to CH5; confirm the module's pin labels before wiring |
| Flame sensor |3.3-5V according to datasheet|According to the module datasheet|AO native 3.3V, direct to CH6|
| Wind direction sensor | Per installed module datasheet | Verify before wiring | Pi RX on GPIO15 accepts 3.3 V UART signals; convert a 5 V sensor TX |
| RS485 anemometer |12V or 5V|According to the unit datasheet| Slave ID 2, Baudrate 9600 |
| A7670E/SIM7600 | Per modem/HAT specification | HAT or regulated external supply | Install only one modem |
|Relay coils| 5V | Pi 5V rail | |
|Siren| 12V | Battery (via relay NO/COM) | |

---

## 8. Checklist Before First Power-On

```
[ ] SPI active (raspi-config → Interface → SPI)
[ ] I2C active (raspi-config → Interface → I2C)
[ ] Common ground: Pi, MCP3008, LLC, all sensors, relays, PSU pressure sensor → one GND
[ ] LLC: HV=5V, LV=3.3V, ONLY 4 channels used (LLC CH1–CH4: MQ-2/MQ-135/Soil x2)
[ ] MCP3008 VDD & VREF to 3.3V (not 5V)
[ ] MCP3008 CH7 intentionally empty (spare)
[ ] R_BURDEN 100Ω is installed correctly in the loop pressure sensor, tap DIRECTLY to MCP3008 CH4 (WITHOUT LLC)
[ ] PSU loop pressure sensor separate from Pi/buck 5V converter
[ ] Voltage sensor module: measuring side (anode/cathode) taps directly to Battery+/− (not via relay); logic side ("+"/"−") to 3.3V/GND Pi; "S" DIRECTLY to MCP3008 CH5 (WITHOUT LLC)
[ ] Flame sensor AO DIRECTLY to MCP3008 CH6 (WITHOUT LLC) — threshold has NOT been calibrated, check sensors/flame.py before deploy
[ ] BME280 (addr 0x76) and Rainfall SEN0575 (addr 0x1D) share the same bus I2C — different addresses, safe
[ ] The 12V siren line only goes through relay COM/NO, does not touch the Pi
[ ] Only ONE module installed: A7670E OR SIM7600 (not both)
[ ] LTE + GNSS antenna installed
[ ] The SIM card is installed before the module is turned on
[ ] Anemometer RS485: Slave ID 2, Baudrate 9600 (default in settings.py)
[ ] Wind Direction: dtoverlay=disable-bt is set on /boot/config.txt, console-over-serial is disabled

Software checks:
[ ] ls /dev/spidev*    → /dev/spidev0.0 exists
[ ] i2cdetect -y 1 → TWO addresses appear: 0x76 (BME280) and 0x1D (Rainfall)
[ ] ls /dev/ttyUSB*    → several ports exist (modem + anemometer)
[ ] python3 tests/test_all_sensors.py → all sensors OK
[ ] python3 tests/test_offline_queue_integrity.py → queue integrity OK
[ ] python3 tests/test_sim_detector.py → SIM module identified
```
