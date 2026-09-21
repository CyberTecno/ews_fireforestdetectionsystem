# Power system

EFWS operates off grid. A solar panel charges a LiFePO4 battery, which supplies the 12 V bus. A buck converter provides 5 V for the Raspberry Pi and other low-voltage loads.

---

## Power flow

| Source | Destination | Purpose |
| --- | --- | --- |
| 100 W solar panel | 20 A PWM charge controller | Charges the battery under sufficient sunlight. |
| Charge controller | 12 V LiFePO4 battery | Manages charging and low-voltage protection. |
| 12 V battery bus | 12 V to 5 V buck converter | Supplies the Raspberry Pi and 5 V loads. |
| 12 V battery bus | Pressure sensor, RS485 anemometer, and siren through relay | Supplies 12 V loads. Check each device's rated voltage. |
| Pi 3.3 V rail | MCP3008 VDD/VREF, BME280, rainfall sensor, wind direction sensor, and low-voltage side of the level converter | Supplies 3.3 V devices. |
| 5 V rail | MQ-2, MQ-135, relay module, and high-voltage side of the level converter | Supplies 5 V devices. |
| Battery terminals | Voltage sensor module, then MCP3008 CH5 | Measures battery voltage without using the buck converter output. |

The pressure sensor's 4–20 mA loop uses a 100 Ω burden resistor and connects to MCP3008 CH4. The flame sensor connects to MCP3008 CH6. Follow the [pinout](Pinout.md) for complete wiring.

---

## 1. Solar panel

| Parameter | Value |
|-----------|-------|
| Type | Monocrystalline |
|Peak power| 100 W |
|Max power point voltage (Vmp)| ~18–22 V (typical panel 100 W mono) |
|Max power point current (Imp)| ~5–6 A |
| Purpose |The main off-grid energy source|

---

## 2. Solar Charge Controller

| Parameter | Value |
|-----------|-------|
| Technology | Intelligent PWM |
|Current rating| 20 A |
|System voltage|12 V / 24 V (automatic detection)|
| Display | LCD graphical |
| Protection |Over-temperature, low battery voltage, reverse polarity|
| USB output |Dual USB 5 V (external device charging)|
| Features |Charge voltage setting, low-voltage disconnect, battery type selection|

> **Setting notes:** Make sure the battery type is set to **LiFePO4** (not Lead-Acid/AGM)
> so that the charging and cut-off voltages match the chemical characteristics of LiFePO4
> (charge ≈ 14.4 V, cut-off ≈ 10–11 V).

---

## 3. LiFePO4 battery

| Parameter | Value | Source |
| --- | --- | --- |
| Chemistry | LiFePO4 (lithium iron phosphate) | Battery specification |
| Nominal voltage | 12 V | Battery specification |
| Full-voltage reference | 14.4 V | `settings.BATTERY_MAX_V` |
| Empty-voltage reference | 10.7 V | `settings.BATTERY_MIN_V` |
| Bus voltage | 12 V (Battery+ / Battery−) | Wiring |

The full and empty values above are used to estimate battery percentage. They do not configure the charge controller's physical cutoff. Set the controller for the specific battery and verify its limits against the battery datasheet.

### How EFWS Reads Battery Level

DC 0-25 V module voltage sensor (see §6) taps directly to **Battery+ / Battery−**
(not from the buck converter output). Calculation in `sensors/battery.py`:

```
V_battery = (raw_ADC / 1023) × BATTERY_SENSOR_MAX_V
battery%  = (V_battery − BATTERY_MIN_V) / (BATTERY_MAX_V − BATTERY_MIN_V) × 100
```

With `BATTERY_SENSOR_MAX_V = 16.5 V` (= VREF 3.3 V × 1:5 divider ratio module).

---

## 4. Buck Converter (12 V → 5 V)

| Parameter | Value |
|-----------|-------|
| Input | 6–36 V DC |
| Output | 5 V DC |
|Output max current| 3–5 A |
| Efficiency | > 90% |
|Function|Supplying Raspberry Pi (via USB-C) and HV side Logic Level Converter|

---

## 5. Distribution & Power Consumption Estimation

| Component |Voltage|Typical Flow|Power|
|----------|----------|-------------|------|
| Raspberry Pi 4 (idle-moderate) | 5 V | ~0.6–1.0 A | ~3–5 W |
| A7670E (LTE transmit) | ~3.7 V (internal) | ~0.5 A peak | ~2 W peak |
|MQ-2 + MQ-135 (active heater)| 5 V |~150 mA each| ~1.5 W total |
| RS485 Anemometer | 12 V | ~50 mA | ~0.6 W |
| Submersible Pressure Sensor | 12 V | ~20–30 mA (loop 4-20 mA) | ~0.3 W |
|Siren (when alarm is active)| 12 V | ~600–1200 mA | ~7–14 W |
| Relay Module | 5 V |~70–80 mA (active coil)| ~0.4 W |
|Other sensors (BME280, soil, etc.)| 3.3 V | < 10 mA total | < 0.1 W |
|**Total (without siren)**| — | — | **~8–10 W** |
|**Total (siren active)**| — | — | **~15–24 W** |

> A 100 W panel under good irradiation conditions (~5 peak-sun hours/day) produces
> ~500 Wh/day. Normal consumption is ~8–10 W × 24 hours = ~192–240 Wh/day → surplus
> for battery charging. Sirens are assumed to be permanently inactive.

---

## 6. Safety Notes

- **Do not connect** the load directly to the solar panel terminal without going through the charge controller.
- **Battery polarity** must be checked before wiring — the controller has reverse polarity protection, but other modules (buck converter, relay) can be permanently damaged if reversed.
- **Grounding:** make sure all GND are connected to a common ground point (common ground) to avoid ground loops that cause noisy ADC readings.
- The siren (~1 A at 12 V) must be powered through the relay, never from a Pi GPIO pin.
