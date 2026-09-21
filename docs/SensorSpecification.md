# EFWS — Sensor Specification

Complete reference of all hardware components used in EFWS. For wiring and
pin assignment, see [`docs/Pinout.md`](Pinout.md). For software configuration (channel
ADC, address I2C, serial port), see [`config/settings.py`](../config/settings.py).

---

## 1. Raspberry Pi 4 Model B

> **Source correction:** The Indonesian `main` document reverses Raspberry Pi
> GPIO14/GPIO15 UART direction and gives an incorrect 1–5 V range for a 100 Ω
> burden resistor at 4–20 mA. The corrections below match the hardware
> mapping used in [`Pinout.md`](Pinout.md).

| Parameter | Value |
|-----------|-------|
| SoC | Broadcom BCM2711 Quad-Core Cortex-A72 (ARM v8) 64-bit @ 1.5 GHz |
| RAM | 8 GB LPDDR4-3200 |
| Storage | MicroSD 32 GB |
| Ethernet | Gigabit Ethernet |
| Wireless | Wi-Fi 802.11ac (2.4 + 5 GHz), Bluetooth 5.0 BLE |
| USB | 2× USB 3.0, 2× USB 2.0 |
| GPIO | 40-pin header (BCM numbering) |
| Display |2× Micro HDMI (up to dual 4K@60fps)|
|Power supplies| USB-C 5 V / 3 A |
| Interfaces used by EFWS | SPI (MCP3008), I2C (BME280 + Rainfall), UART (Wind Direction), USB (A7670E + RS485), GPIO (Relay, LED) |

### Breakout: GPIO T-Cobbler
The T-Cobbler connects GPIO pins to a breadboard during prototyping.
Use a PCB for a permanent installation.

---

## 2. ADC — MCP3008

| Parameter | Value |
|-----------|-------|
| Type | 10-bit SAR ADC, 8-channel single-ended |
| Interface | SPI (bus 0, CE0) |
| VREF | 3.3 V (= VDD) |
| Resolution | 1023 step (0–3.3 V per step ≈ 3.23 mV) |
|Use|Read MQ-2, MQ-135, Soil×2, Pressure, Battery, Flame|

**Channel mapping (see `config/settings.py`):**

| CH | Sensor | Via LLC |Notes|
|----|--------|---------|---------|
| 0 | MQ-2 AOUT | ✅ (5V→3.3V) | `ADC_CHANNEL_MQ2` |
| 1 | MQ-135 AOUT | ✅ (5V→3.3V) | `ADC_CHANNEL_MQ135` |
| 2 | Soil Surface AOUT | ✅ (5V→3.3V) | `ADC_CHANNEL_SOIL_SURFACE` |
| 3 | Soil Deep AOUT | ✅ (5V→3.3V) | `ADC_CHANNEL_SOIL_DEEP` |
| 4 | Pressure Sensor | ❌ (via R_BURDEN 100 Ω) | `ADC_CHANNEL_PRESSURE` |
| 5 | Battery Voltage | ❌ (native 3.3V output) | `ADC_CHANNEL_BATTERY` |
| 6 | Flame Sensor AO | ❌ (native 3.3V output) | `ADC_CHANNEL_FLAME_AO` |
| 7 | — | — |Spare, not wired|

---

## 3. Logic Level Converter (LLC)

| Parameter | Value |
|-----------|-------|
| Type | Bidirectional, 4-channel |
|HV side voltage|5 V (from 5 V Rail)|
|LV side voltage|3.3 V (from Rail 3.3 V Pi)|
|Channels used|4 of 4 (MQ-2, MQ-135, Soil Surface, Soil Deep)|

> **Important:** This LLC is a **linear analog** level-shifter for the signal ADC.
> Do not use digital type (TXS0108E, etc.) for this line — logic-level-shifter chip
> digital only detects the threshold HIGH/LOW, it does not translate the analog voltage linearly.

---

## 4. MQ-2 — Gas & Smoke Sensor

| Parameter | Value |
|-----------|-------|
|Detected gas| LPG, Butane, Propane, Methane, Hydrogen, Smoke |
|Working voltage| 5 V DC |
|Output is used| AOUT (analog) → LLC CH1 → MCP3008 CH0 |
|Output is not used|DOUT (digital, unwired)|
| Driver | `sensors/mq2.py` |
| Setting | `config/settings.py`: `ADC_CHANNEL_MQ2`, `SMOKE_MQ2_CRIT_PPM`, `SMOKE_WEIGHT_MQ2` |

**Role in `smokeLevel`:**

```
smokeLevel = (mq2_ppm / MQ2_CRIT_PPM × W_MQ2 + mq135_ppm / MQ135_CRIT_PPM × W_MQ135) × 100
```

Default: `MQ2_CRIT_PPM = 1000`, `W_MQ2 = 0.55` (55% weight).

> **Note:** MQ sensors need approximately two minutes to warm up after power-on.
> Early readings may be inaccurate. Values ​​in the first minutes after booting may be inaccurate.

---

## 5. MQ-135 — Air Quality Sensor

| Parameter | Value |
|-----------|-------|
|Detected gas| NH₃, NOx, Alcohol, Benzene, Smoke, CO₂ (indicative) |
|Working voltage| 5 V DC |
|Output is used| AOUT (analog) → LLC CH2 → MCP3008 CH1 |
|Output is not used|DOUT (digital, unwired)|
| Driver | `sensors/mq135.py` |
| Setting | `config/settings.py`: `ADC_CHANNEL_MQ135`, `SMOKE_MQ135_CRIT_PPM`, `SMOKE_WEIGHT_MQ135` |

**Role in `smokeLevel`:** 45% weight (`W_MQ135 = 0.45`), `MQ135_CRIT_PPM = 1000`.

---

## 6. BME280 — Temperature, Humidity, Air Pressure

| Parameter | Value |
|-----------|-------|
|Temperature range|−40 to +85 °C|
|Temperature accuracy| ±1 °C (typical) |
|Humidity range| 0–100 % RH |
|Humidity accuracy| ±3 % RH |
|Pressure range| 300–1100 hPa |
|Working voltage| 3.3 V |
| Interface |I2C (shared bus with Rainfall Sensor)|
|Address I2C|`0x76` (default; `0x77` if jumper is soldered) — `EFWS_BME280_ADDR`|
| Driver | `sensors/bme280.py` |

**Fields sent to API:** `temp`, `humidity` (in telemetry payload).
Column `pressure_hpa` is saved in SQLite (`sensor_readings`) but not sent to API
(no ambient pressure field in the telemetry contract).

---

## 7. Soil Moisture Sensor — Resistive Type

| Parameter | Value |
|-----------|-------|
| Type | Resistive (two metal probes) |
|Working voltage| 5 V DC |
|Output is used| AOUT (analog) → LLC → MCP3008 |
|Number of probes| 2 (Surface CH2, Deep CH3) |
| Driver | `sensors/soil.py` |

**Two probe configuration:**

| Probe |Function| Channel |Depth|
|-------|--------|---------|-----------|
| Surface |Surface moisture| MCP3008 CH2 (via LLC CH3) | 0–30 cm |
| Deep |Internal moisture| MCP3008 CH3 (via LLC CH4) | 30–60 cm |

**Output:** `moisture_percent` (0–100 %). **low value = dry = dangerous**
(`lower_is_worse=True`, threshold default: surface & deep < 10 %).

> **Limitations of resistive sensors:** Susceptible to long-term probe corrosion in wet soil.
> Consider recalibration after 3–6 months of field installation.

---

## 8. Gravity Tipping Bucket Rainfall Sensor — DFRobot SEN0575

| Parameter | Value |
|-----------|-------|
| Resolution | ±0.2794 mm per tipping |
| Interface | I2C |
|Address I2C|`0x1D` — shared bus with BME280, no conflict (`RAINFALL_I2C_ADDRESS`)|
|Working voltage| 3.3 V |
| Driver | `sensors/rainfall.py` |
| Validated PID/VID |`0x100C0` / `0x3343` (checked when `__init__`)|

**Available fields of the sensor:**

| Field |Information|
|-------|-----------|
| `rainfall_total_mm` |Cumulative counter since sensor power-on (never auto reset)|
| `rainfall_last_hour_mm` |Accumulation in 1 hour window (configured via `set_rainfall_window(1)`)|
| `tip_counter` |Raw tipping amount|
| `working_time_hours` | Uptime sensor |

**What was sent to API (`payload.telemetry[].rainfall`):**
Cumulative delta since *previous* telemetry sending (`_rainfall_delta()` at `main.py`),
not a 1 hour window — to match the actual send interval (30 minutes normal / 10 minutes emergency).

**What is used to evaluate the alarm threshold:**
`rainfall_last_hour_mm` (1 hour window from sensor) — because the alarm is evaluated on every sampling cycle (3 minutes), not every telemetry transmission.

---

## 9. Submersible Pressure Sensor — Water Level

| Parameter | Value |
|-----------|-------|
| Principle |Hydrostatic pressure → current 4–20 mA|
|Depth range| 0–3 m |
| Output | 4–20 mA (current loop) |
|Power supplies| 12 V DC |
|Interface to Pi|Burden resistor 100 Ω → voltage 0.4–2.0 V → MCP3008 CH4|
| Driver | `sensors/pressure.py` |
| Setting | `PRESSURE_BURDEN_OHM=100`, `PRESSURE_RANGE_M=3.0` |

**Current to depth conversion:**
```
V_burden = current_ma × R_burden / 1000
pct      = (current_ma − 4.0) / 16.0          # 4 mA = 0%, 20 mA = 100%
depth_m  = pct × PRESSURE_RANGE_M
pressure_bar = depth_m × 0.0980665
```

**Fault detection:** `fault_open_loop=True` if the burden voltage is close to 0 V
(cable broken or sensor not submerged / not pressurized).

> **Wiring note:** This sensor does **not** go through the LLC. The burden resistor
> produces 0.4–2.0 V at 4–20 mA, below the MCP3008's 3.3 V reference.
> Do not raise MCP3008 VREF to 5 V while it is connected to the Pi at 3.3 V.

---

## 10. RS485 Anemometer — Wind Speed

| Parameter | Value |
|-----------|-------|
| Protocol | RS485 Modbus RTU |
|Power supplies| 12 V DC |
| Slave ID default | `2` (`EFWS_ANEM_SLAVE`) |
| Baudrate | 9600 bps (`EFWS_ANEM_BAUD`) |
| Speed register | `0x0000` (`EFWS_ANEM_REGISTER`) |
| Decimal places |1 digit (`EFWS_ANEM_DECIMALS`) — raw value divided by 10|
|Interface to Pi| Industrial USB-to-RS485 converter → `/dev/ttyUSB0` |
| Driver | `sensors/anemometer.py` (`minimalmodbus`) |

**Port scan protection:** `scan_ports()` in `sim_detector.py` excludes
`ANEMOMETER_PORT` of the 4G modem scan candidate, as it sends `AT` to the Modbus port
could disrupt an RTU frame.

---

## 11. Industrial USB to RS485 Converter

| Parameter | Value |
|-----------|-------|
| Conversion | USB ↔ RS485 |
| Protocol | Supports Modbus RTU |
| Protection | ESD, galvanic isolation |
|Ports on the Pi|`/dev/ttyUSB0` (default, can be different depending on the enumeration order USB)|

---

## 12. Wind Direction Sensor — JL-FSX2

| Parameter | Value |
|-----------|-------|
| Principle | Hall Effect (sensor A3144) + one magnet per position |
|Direction detected|8 directions (N, NE, E, SE, S, SW, W, NW)|
|Working voltage| 5 V DC |
| Interface | UART TTL (RX/TX) |
| Baudrate | 9600 bps (`EFWS_WIND_DIR_BAUD`) |
|Ports on the Pi| `/dev/serial0` (GPIO14/GPIO15) — `EFWS_WIND_DIR_PORT` |
| Frame protocol | `*<code>#` → codes 1–8 |
| Material housing |PLA+ (indoor/prototype) or ASA (outdoor, UV resistant)|
|Cable length| ±40 cm |
| Driver | `sensors/wind_direction.py` |

**Wiring UART:**
```
Sensor VCC  (red)  → 3.3 V Pi
Sensor GND  (black)  → GND
Sensor TX   (yellow) → GPIO15 (Pin 10, RXD Pi)
Sensor RX   (green)  → GPIO14 (Pin 8, TXD Pi)
```

**Mandatory RPi prerequisites** (see details in `docs/Pinout.md`):
- `dtoverlay=disable-bt` in `/boot/config.txt` → move PL011 UART to GPIO14/15
- Console serial login is disabled via `raspi-config`
- Without both: baudrate drift / random data due to mini-UART clock following VPU

---

## 13. Voltage Sensor Module — DC 0–25 V (Battery Monitor)

| Parameter | Value |
|-----------|-------|
|Input range|0–25 V (hardware), safe up to **16.5 V** when VREF 3.3 V|
| Principle | Internal fixed 1:5 voltage divider |
| Output "S" |0–3.3 V (native, no need LLC)|
|Logic side supply voltage| 3.3 V Pi |
| Channel ADC | MCP3008 CH5 (`ADC_CHANNEL_BATTERY`) |
| Driver | `sensors/battery.py` |
| Setting | `BATTERY_SENSOR_MAX_V = 16.5 V` (= 3.3 V × 5) |

**Battery voltage calculation:**
```
V_battery = (raw_ADC / 1023) × 16.5
```

> **Input safe limit:** 16.5 V (= VREF 3.3 V × ratio 5). The "25 V" printed
> on the module applies if the ADC is assigned VREF 5 V — not the case for this project.
> LiFePO4 battery max 14.4 V is still within safe limits (headroom ~2.1 V).

---

## 14. IR Flame Sensor

| Parameter | Value |
|-----------|-------|
| Principle |IR photodiode — detects IR radiation from flames (750–1100 nm)|
|Output is used|AO (analog) → MCP3008 CH6 (direct, native 3.3 V, without LLC)|
|Output is not used|DO (digital, not wired)|
|Output voltage|Down when there is fire (default `trigger_below=True`)|
| Detection threshold |`FLAME_AO_THRESHOLD_V = 1.65 V` (**INITIAL ESTIMATE; calibration required!**)|
| Driver | `sensors/flame.py` |

**Field calibration procedure:**
1. `python sensors/flame.py` → record the AO value under normal conditions (no fire)
2. Bring a small flame (match / candle, safe distance) → record the AO value when there is a fire
3. Set `EFWS_FLAME_AO_THRESHOLD_V` in `.env` to a value between the two
4. If AO **rises** when there is fire (certain modules have different polarity): set `trigger_below=False`

---

## 15. Relay Module — 5 V 1-Channel

| Parameter | Value |
|-----------|-------|
|Control voltage|5 V (GPIO Pi signal via onboard driver transistor)|
|GPIO control| GPIO27 (Pin 13) — `EFWS_GPIO_RELAY` |
| Contacts | NO (Normally Open) / NC (Normally Closed) / COM |
| Contact rating |10 A / 250 VAC or 10 A / 30 VDC|
| Load | Siren 12 V (~1 A) |
| Driver | `alarm/relay.py`, `alarm/siren.py` |

**Pulsing alarm logic (from `alarm/siren.py`):**

| Level | Relay behavior |
|-------|---------------|
| `none` | OFF |
| `warning` | Pulse: ON 0.4 s / OFF 1.6 s (background thread) |
| `critical` |ON continuously|

---

## 16. Siren 12 V

| Parameter | Value |
|-----------|-------|
|Working voltage| 12 V DC |
|Power consumption| ~15–20 W |
|Current consumption| ~600–1200 mA (~1 A typical) |
| Sound level | ±120 dB |
|Control| Via Relay Module (GPIO27) |

> The siren is supplied directly from the **12 V battery bus** (not from the 5 V buck converter),
> relay controlled. The ~1 A consumption should not be fed through the GPIO Pi directly
> (GPIO Pi limits ~16 mA per pin).

---

## 17. SIMCom A7670E — 4G LTE Modem

| Parameter | Value |
|-----------|-------|
| Standardd | LTE Cat-1 |
| Fallback | GSM / GPRS |
| GNSS |Available (depending on variant — confirm with hardware label)|
| Interface | UART (AT Command), USB |
|Working voltage|3.4–4.2 V (module internal regulation / HAT)|
| Port AT | `/dev/ttyUSB2` (default `EFWS_SIM_PORT`, auto-detect via `sim_detector.py`) |
| Baudrate | 115200 bps (`EFWS_A7670E_BAUD`) |
| Driver | `communication/a7670e.py` |

**Command set used EFWS:**

|Function| AT Command |
|--------|-----------|
|Check the module| `AT` |
| Identify module |`ATI` (for auto-detect on `sim_detector.py`)|
| Signal quality | `AT+CSQ` |
| Network registration | `AT+CREG?` |
| Set APN | `AT+CGDCONT=1,"IP","<APN>"` |
|Turn on GNSS| `AT+CGNSSPWR=1` |
|Read position GPS| `AT+CGPSINFO` |
|Turn off GNSS| `AT+CGNSSPWR=0` |

> **SIM7600 compatibility note:** If SIM7600 (legacy) is used, the GNSS command is different:
> `AT+CGPS=1` / `AT+CGPS=0`. Handling is automatic via `communication/sim7600_legacy.py`
> + `sim_detector.py` (auto-detect based on response `ATI`).
