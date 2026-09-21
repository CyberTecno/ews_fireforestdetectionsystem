# Sensor specifications

This reference describes the hardware in the Indonesian `main/docs` source. For connections and corrected pin assignments, see [Pinout.md](Pinout.md). For configured ADC channels, I2C addresses, and serial ports, see [config/settings.py](../config/settings.py).

---

## 1. Raspberry Pi 4 Model B

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
| Power supply | USB-C 5 V / 3 A |
| Interfaces used by EFWS | SPI (MCP3008), I2C (BME280 and rainfall sensor), UART (wind direction), USB (modem and RS485), GPIO (relay and LED) |

### GPIO breakout

A GPIO T-Cobbler makes breadboard wiring easier during development. Use a suitable permanent board or enclosure for field installation.

---

## 2. ADC — MCP3008

| Parameter | Value |
|-----------|-------|
| Type | 10-bit SAR ADC, 8-channel single-ended |
| Interface | SPI (bus 0, CE0) |
| VREF | 3.3 V (= VDD) |
| Resolution | 1,024 codes (0–1,023), approximately 3.23 mV per code at 3.3 V VREF |
|Use|Read MQ-2, MQ-135, Soil×2, Pressure, Battery, Flame|

**Channel mapping (from `config/settings.py`):**

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

> **Hardware discrepancy:** The source guide describes a linear analog converter here, while its wiring guide specifies a four-channel I2C-style digital level converter. A digital converter does not preserve continuous analog voltage. The current wiring routes four analog sensors through it, so verify the actual installed part and calibrate the ADC readings. Never connect a 5 V sensor output directly to the 3.3 V MCP3008.

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

Defaults: `MQ2_CRIT_PPM = 1000` and `W_MQ2 = 0.55` (55% weight).

> **Warm-up:** Allow approximately two minutes after power-on before relying on MQ readings. Early readings may be inaccurate.

---

## 5. MQ-135 — Air Quality Sensor

| Parameter | Value |
|-----------|-------|
| Detected gases | NH₃, NOx, alcohol, benzene, smoke, and indicative CO₂ readings |
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

## 7. Resistive soil moisture sensor

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
| Resolution | Approximately 0.2794 mm per bucket tip |
| Interface | I2C |
|Address I2C|`0x1D` — shared bus with BME280, no conflict (`RAINFALL_I2C_ADDRESS`)|
|Working voltage| 3.3 V |
| Driver | `sensors/rainfall.py` |
| PID/VID validation | `0x100C0` / `0x3343` (checked during initialization) |

**Available fields of the sensor:**

| Field |Information|
|-------|-----------|
| `rainfall_total_mm` |Cumulative counter since sensor power-on (never auto reset)|
| `rainfall_last_hour_mm` |Accumulation in 1 hour window (configured via `set_rainfall_window(1)`)|
| `tip_counter` |Raw tipping amount|
| `working_time_hours` | Uptime sensor |

**Value sent to the API (`payload.telemetry[].rainfall`):** The cumulative increase since the previous telemetry delivery, calculated by `_rainfall_delta()` in `main.py`. This matches the variable 30-minute or 10-minute send interval.

**Value used for alarm evaluation:** `rainfall_last_hour_mm`, the sensor's rolling one-hour reading. The main loop checks it at each three-minute sampling cycle.

---

## 9. Submersible Pressure Sensor — Water Level

| Parameter | Value |
|-----------|-------|
| Principle |Hydrostatic pressure → current 4–20 mA|
|Depth range| 0–3 m |
| Output | 4–20 mA (current loop) |
| Power supply | 12 V DC |
|Interface to Pi|100 Ω burden resistor → 0.4–2.0 V at 4–20 mA → MCP3008 CH4|
| Driver | `sensors/pressure.py` |
| Setting | `PRESSURE_BURDEN_OHM=100`, `PRESSURE_RANGE_M=3.0` |

**Current to depth conversion:**
```
V_burden = current_ma × R_burden / 1000
pct      = (current_ma − 4.0) / 16.0          # 4 mA = 0%, 20 mA = 100%
depth_m  = pct × PRESSURE_RANGE_M
pressure_bar = depth_m × 0.0980665
```

**Fault detection:** `fault_open_loop=True` when the burden voltage is near 0 V, indicating an open or unpowered current loop. A healthy sensor at zero pressure should still produce approximately 4 mA.

> **Wiring note:** With the configured 100 Ω burden resistor, the 4–20 mA loop produces 0.4–2.0 V. This fits within the MCP3008's 3.3 V reference, so the pressure signal connects directly to CH4 without the logic-level converter. Keep MCP3008 VDD and VREF at 3.3 V.

---

## 10. RS485 Anemometer — Wind Speed

| Parameter | Value |
|-----------|-------|
| Protocol | RS485 Modbus RTU |
| Power supply | 12 V DC |
| Slave ID default | `2` (`EFWS_ANEM_SLAVE`) |
| Baudrate | 9600 bps (`EFWS_ANEM_BAUD`) |
| Speed register | `0x0000` (`EFWS_ANEM_REGISTER`) |
| Decimal places | 1 (`EFWS_ANEM_DECIMALS`); raw value divided by 10 |
|Interface to Pi| Industrial USB-to-RS485 converter → `/dev/ttyUSB0` |
| Driver | `sensors/anemometer.py` (`minimalmodbus`) |

**Port scan protection:** `scan_ports()` in `sim_detector.py` excludes `ANEMOMETER_PORT` from modem detection. Sending an `AT` command to the Modbus port could interrupt an RTU frame.

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
| Principle | Hall effect (A3144 sensor) with one magnet per position |
|Direction detected|8 directions (N, NE, E, SE, S, SW, W, NW)|
| Working voltage | Check the installed module datasheet; the source guide gives both 5 V and 3.3 V |
| Interface | UART TTL (RX/TX) |
| Baudrate | 9600 bps (`EFWS_WIND_DIR_BAUD`) |
|Ports on the Pi| `/dev/serial0` (GPIO14/GPIO15) — `EFWS_WIND_DIR_PORT` |
| Frame format | `*<code>#` → codes 1–8 |
| Material housing |PLA+ (indoor/prototype) or ASA (outdoor, UV resistant)|
|Cable length| ±40 cm |
| Driver | `sensors/wind_direction.py` |

**UART wiring:** Confirm the sensor's supply and signal voltages from its datasheet before connecting it. The Pi UART accepts 3.3 V signals; a 5 V sensor TX requires proper level conversion.

| Sensor wire | Raspberry Pi connection |
| --- | --- |
| Red (VCC) | Verified supply for the installed sensor module |
| Black (GND) | Common ground |
| Yellow (sensor TX) | Pi RXD, GPIO15 / physical pin 10 |
| Green (sensor RX) | Pi TXD, GPIO14 / physical pin 8 |

**Raspberry Pi prerequisites** (see [Pinout.md](Pinout.md)):
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

> **Input limit:** 16.5 V (= 3.3 V VREF × divider ratio 5). A printed 25 V module rating assumes a 5 V ADC reference, which this project does not use.
> LiFePO4 battery max 14.4 V is still within safe limits (headroom ~2.1 V).

---

## 14. IR Flame Sensor

| Parameter | Value |
|-----------|-------|
| Principle |IR photodiode — detects IR radiation from flames (750–1100 nm)|
|Output is used|AO (analog) → MCP3008 CH6 (direct, native 3.3 V, without LLC)|
|Output is not used|DO (digital, not wired)|
|Output voltage|Down when there is fire (default `trigger_below=True`)|
| Detection threshold |`FLAME_AO_THRESHOLD_V = 1.65 V` (initial estimate; calibration required)|
| Driver | `sensors/flame.py` |

**Field calibration:**
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
| Standard | LTE Cat-1 |
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
| Identification |`ATI` (for auto-detect on `sim_detector.py`)|
| Signal quality | `AT+CSQ` |
| Network registration | `AT+CREG?` |
| Set APN | `AT+CGDCONT=1,"IP","<APN>"` |
|Turn on GNSS| `AT+CGNSSPWR=1` |
|Read position GPS| `AT+CGPSINFO` |
|Turn off GNSS| `AT+CGNSSPWR=0` |

> **SIM7600 compatibility note:** If SIM7600 (legacy) is used, the GNSS command is different:
> `AT+CGPS=1` / `AT+CGPS=0`. Handling is automatic via `communication/sim7600_legacy.py`
> + `sim_detector.py` (auto-detect based on response `ATI`).
