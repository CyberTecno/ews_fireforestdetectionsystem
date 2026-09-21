# EFWS — Pinout & Wiring Reference

Final hardware:
**Raspberry Pi 4 · MCP3008 (SPI ADC 8-ch) · 1x Logic Level Converter I2C-style
(4-channel, bi-directional, 3.3~5.0V) · MQ-2 · MQ-135 · BME280 (I2C) ·
Soil Probe Surface · Soil Probe Deep · Submersible Pressure Sensor (loop
4-20mA) · DC Voltage Sensor Module (battery) · Flame Sensor (analog) ·
DFRobot Gravity Rainfall Sensor SEN0575 (I2C) · RS485 Anemometer ·
Wind Direction (UART GPIO14/15) A7670E OR SIM7600 (auto-detect, only
one installed) · 5V Relay · 12V Siren**

> No separate buzzer — just one relay + siren (2 levels of escalation
> via pulsing vs. continuous on pattern, see `alarm/siren.py`). Thresholds &
> alarm decision level is evaluated locally ONLY to turn on the siren
> real-time — not saved to local database, due to alarm evaluation
> The backend maintains the authoritative alarm record.

---

## 1. Raspberry Pi 4 — Pins Used (BCM Numbering)

> **Source correction:** The Indonesian `main` document numbers MCP3008 inputs
> CH1–CH8 and reverses the Pi UART labels. The project configuration uses
> ADC CH0–CH6, with CH7 spare; Raspberry Pi GPIO14/pin 8 is TXD and
> GPIO15/pin 10 is RXD. The mappings below use the hardware and code numbering.
> The original connections and components are otherwise preserved.

|Function| GPIO (BCM) |Physical Pins|Information|
|--------|-----------|-----------|------------|
| SPI SCLK (MCP3008) | GPIO11 | Pin 23 | Clock SPI |
| SPI MISO (MCP3008) | GPIO9  | Pin 21 |Data from MCP3008|
| SPI MOSI (MCP3008) | GPIO10 | Pin 19 |Data to MCP3008|
| SPI CE0  (MCP3008) | GPIO8  | Pin 24 | Chip Select |
| I2C SDA (BME280 + Rainfall) | GPIO2  | Pin 3  |Data I2C, bus shared|
| I2C SCL (BME280 + Rainfall) | GPIO3  | Pin 5  |Clock I2C, bus is shared|
| UART TXD (Wind Direction) | GPIO14 | Pin 8 | Transmit to sensor RX (green; usually unused) |
| UART RXD (Wind Direction) | GPIO15 | Pin 10 | Receive from sensor TX (yellow) |
|Siren Relay (output)| GPIO27 | Pin 13 |To IN relay 5V|
| Status LED (output, optional) | GPIO23 | Pin 16 | indicator heartbeat |
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
`sudo systemctl disable hciuart` — details & reasons in section
"Wind Direction" in §5 below.

---

## 2. BME280 & Rainfall Sensor — Wiring I2C (bus shared)

These two sensors are native I2C, directly to the Pi (**not via MCP3008/LLC**),
and **share the same I2C bus** (SDA/SCL). This is safe because of the address I2C
both different — will not conflict with each other.

### BME280 (ambient temperature, humidity, and pressure)
| Pin BME280 |Connect to|
|-----------|-----------|
| VIN | Pi 3.3V |
| GND | Common ground |
| SCL | GPIO3 (Pin 5) |
| SDA | GPIO2 (Pin 3) |

I2C address: `0x76` (or `0x77` depending on the module jumper soldering).

### DFRobot Gravity Rainfall Sensor (SEN0575) — Tipping Bucket
| Pin sensor |Connect to|
|-----------|-----------|
| VCC | Pi 3.3V |
| GND | Common ground |
| SCL |GPIO3 (Pin 5) — **same as BME280**|
| SDA |GPIO2 (Pin 3) — **same as BME280**|

I2C Address: `0x1D` (`RAINFALL_I2C_ADDRESS` at `config/settings.py`) —
**different from BME280 (`0x76`/`0x77`)**, so parallel wiring on the I2C bus
safe without a multiplexer.

```bash
i2cdetect -y 1     # TWO addresses should appear: 0x76 (BME280) and 0x1D (Rainfall)
python3 tests/test_bme280.py
python3 tests/test_rainfall.py
```

---

## 3. MCP3008 — Wiring to Raspberry Pi

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
| CH0–CH3 | See §4 — via LLC | MQ-2, MQ-135, Soil Surface, Soil Deep |
| CH4 | Pressure sensor, **directly without LLC** |Via R_BURDEN 100Ω|
| CH5 | Battery/voltage sensor, **directly without LLC** |Native 3.3V signal|
| CH6 | Flame sensor (AO), **directly without LLC** |Native 3.3V signal|
| CH7 | *(spare, not wired)* |LLC only 4 channels, already full on CH0–CH3|

Verification: `ls /dev/spidev*` → should appear `/dev/spidev0.0`

---

## 4. MCP3008 Channel Map MCP3008 — Logic Level Converter (4-channel)

LLC module used in this project: **"I2C Logic Level Converter" 4-channel,
bi-directional, data level 3.3~5.0V** — designed for DIGITAL signals
(I2C/UART/SPI between boards, e.g. Arduino↔Pi), NOT to translate
linearly continuous analog voltage.

> ⚠️ **Known limitation (accepted for this design):** MQ-2,
> MQ-135, and both soil probes remain wired through an LLC even though their
> outputs are analog signals. The consequence: reading of ADC on all 4 channels
> may not be linear or proportional to the actual sensor voltage (this type of level-shifter chip works with threshold detection
> HIGH/LOW, rather than translating a continuous voltage). This is a known
> design trade-off. If
> If these readings jump instead of changing smoothly, check the converter first.
>
> Pressure, Battery, and Flame are deliberately EXCLUDED from this LLC (see
> §5) — either because the signal is native 3.3V (Battery, Flame) or
> because the burden resistor voltage is automatically within a safe range
> without the need for step-down (Pressure).

| LLC |HV side (5V) ← of the sensor|LV side (3.3V) → to MCP3008| Channel |
|-----|---------------------------|------------------------------|---------|
| CH1 | MQ-2 **AOUT** | **MCP3008 CH0** | Smoke/gas analog |
| CH2 | MQ-135 **AOUT** | **MCP3008 CH1** |Air quality analog|
| CH3 | Soil Surface **AOUT** | **MCP3008 CH2** | Moisture at 0–30 cm |
| CH4 | Soil Deep **AOUT** | **MCP3008 CH3** | Moisture at 30–60 cm |

*(The physical LLC module only has 4 channels — already fully used above. Pressure/
Battery/Flame NOT via this module altogether, see §5.)*

### LLC module wiring

```
LLC:
HV pin ←── 5V (from buck converter / Pi pin 2/4)
LV pin ←── 3.3V (from Pi pin 1/17)
  GND HV   ←── Common ground
  GND LV   ←── Common ground
```

---

## 5. Detailed Wiring by Sensor

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

### Submersible Pressure Sensor — 4-20mA loop (Water Level) — NOT via LLC

This **two-wire, loop-powered** sensor needs a burden resistor to convert its
4–20 mA output into a voltage the ADC can read. Its wiring differs from the
four analog sensors above. With R_BURDEN **100Ω**
(`PRESSURE_BURDEN_OHM` in `config/settings.py`), the resulting voltage
is automatically in the safe range 0-3.3V — **no need for LLC at all**,
go straight to MCP3008.

```
12–24 V loop supply (+) ─────► sensor V+
                                   │
                     Sensor output: 4–20 mA
                                   │
                                   ▼
                         100 Ω burden resistor
                                   │
                 Top junction: 0.4–2.0 V ─────► MCP3008 CH4
                                   │
                                   ▼
                      Common ground / supply (−)
```

| Point |Connect to|
|-------|-----------|
| Loop V+ |PSU 12-24V (+) — **not** from Pi/buck 5V converter|
|Exit loop (after sensor)|Top end R_BURDEN (100Ω)|
| Bottom end of R_BURDEN | Common ground and PSU (−) |
| Sensor/R_BURDEN junction |**DIRECT** to MCP3008 **CH4** (without LLC)|

**Why 100 Ω?**
- 4mA × 100Ω = **0.4V** → “empty” level (0m)
- 20mA × 100Ω = **2.0V** → “full” level (`PRESSURE_RANGE_M`, default 3m — adjust your sensor datasheet)

This 0.4-2.0V range is far below VREF (3.3V), so it is safe to read
straight away without any level-shifting.

The conversion formula is in `sensors/pressure.py`. **Customize** `EFWS_PRESSURE_RANGE_M`
in `.env` with the depth/pressure range of your physical sensor (many variants: 0–3 m,
0-5m, 0-10m). Payload API sends two values ​​from this sensor: `waterLevel` (meters)
and `pressure` (bar, hydrostatic conversion).

### DC Voltage Sensor Module (Battery) — NOT via LLC

This module has a built-in passive 1:5 resistive voltage divider. **Just like Pressure, this module is NOT
wired via LLC** — the output signal is natively 3.3V (see notes
at `sensors/battery.py`, reference: osoyoo.com/2024/09/08/lesson-13-voltage-
sensor-for-raspberry-pi/). The manufacturer's rating for this module is often written as "0-25V",
but that only applies if the ADC is given VREF 5V. In this project (MCP3008
VREF 3.3V), **correct input safe limit is 16.5V** (3.3V x ratio 5) —
Your battery (max 14.4V) is still below this limit with ~2.1V headroom, safe.

This module has **five connection points on two different sides** — don't confuse them:

| Module pins | Side | Connect to |
|-----------|------|-----------|
| **+** |Output/logic (to Pi)|3.3V Pi (Pin 1 or 17)|
| **−** | Output/logic (to Pi) | Common ground |
| **S** |Output/logic (to Pi)|**DIRECT** to MCP3008 **CH5** (without LLC)|
| **anode / IN+** |Input (measured)| Terminal Battery+ (12V LiFePO4/similar, max 14.4V) |
| **cathode / IN−** |Input (measured)| Terminal Battery− |

The conversion formula is in `sensors/battery.py`. Calibration `BATTERY_MAX_V` /
`BATTERY_MIN_V` in `.env` according to your battery specifications — **`BATTERY_MAX_V`
already set to 14.4V** (confirmed). `BATTERY_MIN_V` (default 10.7V)

### Flame Sensor (AO, analog) — NOT via LLC

| Pin sensor |Connect to|
|-----------|-----------|
| VCC |As per module datasheet (usually 3.3-5V)|
| GND | Common ground |
| AO | **DIRECTLY** to MCP3008 **CH6** (without LLC; CH7 remains spare) |

This module's AO signal is native 3.3V, no need for step-down. **Voltage threshold
not calibrated to physical unit** (`FLAME_AO_THRESHOLD_V`, 1.65V placeholder)
— see calibration procedure in docstring `sensors/flame.py`. DO NOT use
GPIO/DO — this sensor is purely read via MCP3008.

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
| Red (VCC) |3.3V (pin 1 or 17)|
| Black (GND) | GND |
| Yellow (sensor TX) | GPIO15 / pin 10 (RXD Pi) |
| Green (sensor RX) | GPIO14 / pin 8 (TXD Pi) |

Protocol: text line `*<code>#` via UART software `/dev/serial0`, code
1-8 = N/NE/E/SE/S/SW/W/NW. Baudrate default 9600 (`EFWS_WIND_DIR_BAUD`).

> ⚠️ **Must check before installing:** on Raspberry Pi 4, GPIO14/15
> the serial port can use a mini-UART whose baud rate depends on the VPU clock.
> To keep this sensor's serial connection stable:
> 1. `sudo raspi-config` → Interface Options → Serial Port → login shell
>    via serial: **No**, hardware serial port: **Yes**.
> 2. Add `dtoverlay=disable-bt` in `/boot/config.txt`, then
>    `sudo systemctl disable hciuart`, then reboot.
> 3. After rebooting, `/dev/serial0` will automatically connect to PL011 (full
>    stable UART), not mini-UART.
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

```
Control side (Pi / relay)             Siren power side (12 V)
GPIO27 ───────────────► relay IN       Battery+ ───► relay COM
5 V ──────────────────► relay VCC      relay NO ───► siren (+)
GND ──────────────────► relay GND      Siren (−) ──► Battery−
```

> ⚠️ The siren's 12V line should **never** touch any of the Pi pins.
> There is no separate buzzer — this one relay handles 2 levels of escalation
> (WARNING = slowly pulsing, CRITICAL = continuously on), see `alarm/siren.py`.

---

## 6. Complete Signal Block Diagram

```
MQ-2 AOUT (5 V) ──────┐
MQ-135 AOUT (5 V) ────┤  Four-channel level converter
Surface soil AOUT ────┤  LLC CH1–CH4 (5 V side → 3.3 V side)
Deep soil AOUT ───────┘              │
                                    ▼
                           MCP3008 CH0–CH3 ── SPI ──┐
Pressure loop → 100 Ω burden resistor → CH4 ────────┤
Battery voltage sensor → CH5 ────────────────────────┤
Flame AO → CH6 ──────────────────────────────────────┤
BME280 (I2C address 0x76) ──────────────────────────┤
SEN0575 rainfall (I2C address 0x1D) ────────────────┤
RS485 anemometer → USB-RS485 converter ─────────────┤
JL-FSX2 wind direction → UART GPIO14/15 ────────────┤
A7670E or SIM7600 modem → USB ───────────────────────┤
                                                     ▼
                                             Raspberry Pi 4
  1. Read sensors and evaluate local alarm → GPIO27 → relay → 12 V siren
  2. Save readings to SQLite before sending telemetry to the API
  3. Queue failed API payloads and retry every two minutes
```

---

## 7. Power Supply for Each Load

| Beban |Voltage|Source|Notes|
|-------|---------|--------|---------|
| Raspberry Pi 4 | 5V | Buck converter output |Via GPIO pin 2/4 or USB-C|
| MCP3008 VDD/VREF | 3.3V | Pi 3.3V rail | |
| BME280 | 3.3V | Pi 3.3V rail |I2C directly, without LLC|
| Rainfall SEN0575 | 3.3V | Pi 3.3V rail |The bus is the same as BME280|
| LLC LV | 3.3V | Pi 3.3V rail |Only for 4 channels: MQ-2/MQ-135/Soil x2|
| LLC HV | 5V | Buck converter / Pi 5V rail |Only for 4 channels: MQ-2/MQ-135/Soil x2|
|MQ-2 / MQ-135 heaters| 5V |Direct buck converter|~150mA each|
| Soil probe ×2 |5V or 3.3V|According to the probe datasheet| |
| Submersible pressure sensor | 12-24V (loop) |**PSU is separate**, not from Pi/buck 5V|Loop-powered, R_BURDEN 100Ω, direct to CH4|
|Voltage sensor module (battery)|Measuring side: passive, tap Battery+/−. Logic side ("+"/"−"): **3.3V from Pi**|Pi 3.3V rail (for its "+"/"−" logic pins)|**Supply required:** connect "+"/"−" pins to 3.3V/GND Pi, direct to CH5|
| Flame sensor |3.3-5V according to datasheet|According to the module datasheet|AO native 3.3V, direct to CH6|
| RS485 anemometer |12V or 5V|According to the unit datasheet| Slave ID 2, Baudrate 9600 |
| A7670E/SIM7600 |5V or 3.7-4.2V|Fits HAT board| |
|Relay coils| 5V | Pi 5V rail | |
|Siren| 12V | Battery (via relay NO/COM) | |

---

## 8. Checklist Before First Power-On

```
[ ] SPI active (raspi-config → Interface → SPI)
[ ] I2C active (raspi-config → Interface → I2C)
[ ] Common ground: Pi, MCP3008, LLC, all sensors, relays, PSU pressure sensor → one GND
[ ] LLC: HV=5V, LV=3.3V, ONLY 4 channels used (LLC CH1–CH4 → ADC CH0–CH3: MQ-2/MQ-135/Soil x2)
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

Software verification:
[ ] ls /dev/spidev*    → /dev/spidev0.0 exists
[ ] i2cdetect -y 1 → TWO addresses appear: 0x76 (BME280) and 0x1D (Rainfall)
[ ] ls /dev/ttyUSB*    → several ports exist (modem + anemometer)
[ ] python3 tests/test_all_sensors.py → all sensors OK
[ ] python3 tests/test_offline_queue_integrity.py → queue integrity OK
[ ] python3 tests/test_sim_detector.py → SIM module identified
```
