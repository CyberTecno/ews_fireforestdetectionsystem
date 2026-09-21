# EFWS — Power System

The system operates completely off-grid, relying on solar panels as an energy source
main with LiFePO4 battery as buffer. All components are supplied from the voltage rail
which is derived from the 12 V battery bus.

---

## Power Flow Diagrams

```
[Solar Panel 100 W]
        │ ~18–22 V (Vmp)
        ▼
[Solar Charge Controller 20 A PWM]  ← proteksi overcharge, overdischarge, polaritas
        │
        ├──── 12 V Bus (Battery+/−) ────────────────────────────────────────────┐
        │       │                                                               │
        │       ├─ [Voltage Sensor Module] ─── MCP3008 CH5 ──► RPi (monitoring) │
        │       ├─ [Submersible Pressure Sensor] (12 V, 4-20 mA loop)           │
        │       ├─ [RS485 Anemometer] (12 V)                                    │
        │       └─ [Siren 12 V, ~1 A] ◄── via Relay Module (GPIO27)             │
        │                                                                       │
        └──── [Buck Converter 12V → 5V, 3–5A, η>90%]                            │
                │ 5 V DC                                                        │
                ├─ [Raspberry Pi 4] (via USB-C, max. 3 A)                      │
│ │ 3.3 V Rail (from Pi onboard regulator) │
                │     ├─ BME280                                                 │
                │     ├─ Rainfall Sensor SEN0575 (I2C)                          │
                │     ├─ Wind Direction Sensor JL-FSX2 (UART)                   │
                │     ├─ MCP3008 VDD & VREF                                     │
                │     ├─ Logic Level Converter — sisi LV                        │
│ ├─ Flame Sensor AO (direct to MCP3008 CH6) │
                │     └─ Voltage Sensor Module — sisi logic "+"                 │
                │                                                               │
                ├─ Logic Level Converter — sisi HV (5 V)                        │
                │     ├─ MQ-2 (5 V)                                             │
                │     ├─ MQ-135 (5 V)                                           │
                │     ├─ Soil Moisture Surface (5 V)                            │
                │     └─ Soil Moisture Deep (5 V)                               │
└─ Relay Module 5 V (GPIO27 control) │
                                                                                │
[12V LiFePO4 Battery] ◄──────────────────────────── ────────────────────────────┘
(cloud current buffer & supply/malam)
```

---

## 1. Panel Surya

| Parameter |Mark|
|-----------|-------|
| Tipe | Monokristalin |
|Peak power| 100 W |
|Max power point voltage (Vmp)| ~18–22 V (tipikal panel 100 W mono) |
|Max power point current (Imp)| ~5–6 A |
| Aplikasi |The main off-grid energy source|

---

## 2. Solar Charge Controller

| Parameter |Mark|
|-----------|-------|
| Teknologi | Intelligent PWM |
|Current rating| 20 A |
|System voltage|12 V / 24 V (automatic detection)|
| Display | LCD graphical |
| Proteksi |Over-temperature, low battery voltage, reverse polarity|
| USB output |Dual USB 5 V (external device charging)|
| Fitur |Charge voltage setting, low-voltage disconnect, battery type selection|

> **Setting notes:** Make sure the battery type is set to **LiFePO4** (not Lead-Acid/AGM)
> so that the charging and cut-off voltages match the chemical characteristics of LiFePO4
> (charge ≈ 14.4 V, cut-off ≈ 10–11 V).

---

## 3. LiFePO4 battery

| Parameter |Mark|Source|
|-----------|-------|--------|
| Kimia | LiFePO4 (Lithium Iron Phosphate) |user confirmed|
|Nominal voltage| 12 V | — |
|FULL voltage (charge cutoff)| **14.4 V** | `settings.BATTERY_MAX_V` |
|EMPTY voltage (discharge cutoff)| **9.0 V** | `settings.BATTERY_MIN_V` ¹ |
|Bus voltage| 12 V (Battery+ / Battery−) | — |

> ¹ **NOTE:** The 9.0 V value for 12 V LiFePO4 is too deep — safe point blank
> for LiFePO4 it is usually **10–11 V** (discharging to 9 V risks damaging the cells). This value
> has not been reconfirmed when `BATTERY_MAX_V` is changed from 12.6 V to 14.4 V. Adjust
> `EFWS_BATTERY_MIN_V` in `.env` after confirming with your specific battery datasheet.

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

| Parameter |Mark|
|-----------|-------|
| Input | 6–36 V DC |
| Output | 5 V DC |
|Output max current| 3–5 A |
| Efisiensi | > 90% |
|Function|Supplying Raspberry Pi (via USB-C) and HV side Logic Level Converter|

---

## 5. Distribution & Power Consumption Estimation

| Komponen |Voltage|Typical Flow|Power|
|----------|----------|-------------|------|
| Raspberry Pi 4 (idle-moderate) | 5 V | ~0.6–1.0 A | ~3–5 W |
| A7670E (LTE transmit) | ~3.7 V (internal) | ~0.5 A puncak | ~2 W puncak |
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
- Siren (~1 A @ 12 V) **NOT** can be powered from GPIO directly — must be via relay.
