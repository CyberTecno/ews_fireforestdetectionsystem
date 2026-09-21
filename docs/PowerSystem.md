# EFWS — Power System

The system operates entirely off-grid. A solar panel provides the primary energy source,
with a LiFePO4 battery as a buffer. All components draw power from rails derived from
the 12 V battery bus.

---

## Power Flow Diagrams

```
[100 W solar panel]
        │ approximately 18–22 V at maximum power
        ▼
[20 A PWM solar charge controller]
        │
        ├──► [12 V LiFePO4 battery] ──► 12 V bus ──┬──► pressure sensor loop
        │                                           ├──► RS485 anemometer
        │                                           ├──► siren through relay
        │                                           └──► battery voltage sensor
        │                                                   │
        │                                                   ▼
        │                                               MCP3008 CH5
        │
        └──► [12 V to 5 V buck converter] ──► 5 V bus
                                                   ├──► Raspberry Pi 4 (USB-C)
                                                   │      └──► 3.3 V rail
                                                   │             ├──► MCP3008 VDD/VREF
                                                   │             ├──► BME280 and SEN0575
                                                   │             └──► LLC low-voltage side
                                                   ├──► MQ-2 and MQ-135
                                                   ├──► LLC high-voltage side
                                                   └──► relay module

All connected components share the required common ground. Check the installed
wind direction module's voltage rating before choosing its supply.
```

---

## 1. Solar Panel

| Parameter | Value |
|-----------|-------|
| Type | Monocrystalline |
|Peak power| 100 W |
|Max power point voltage (Vmp)| ~18–22 V (typical 100 W monocrystalline panel) |
|Max power point current (Imp)| ~5–6 A |
| Application | Primary off-grid energy source |

---

## 2. Solar Charge Controller

| Parameter | Value |
|-----------|-------|
| Technology | Intelligent PWM |
|Current rating| 20 A |
|System voltage|12 V / 24 V (automatic detection)|
| Display | LCD graphical |
| Protections | Over-temperature, low battery voltage, reverse polarity |
| USB output |Dual USB 5 V (external device charging)|
| Features | Charge voltage setting, low-voltage disconnect, battery type selection |

> **Setting notes:** Make sure the battery type is set to **LiFePO4** (not Lead-Acid/AGM)
> so that the charging and cut-off voltages match the chemical characteristics of LiFePO4
> (charge ≈ 14.4 V, cut-off ≈ 10–11 V).

---

## 3. LiFePO4 battery

| Parameter | Value |Source|
|-----------|-------|--------|
| Chemistry | LiFePO4 (lithium iron phosphate) | Confirmed by project owner |
|Nominal voltage| 12 V | — |
|FULL voltage (charge cutoff)| **14.4 V** | `settings.BATTERY_MAX_V` |
|EMPTY voltage (discharge cutoff)| **9.0 V** | `settings.BATTERY_MIN_V` ¹ |
|Bus voltage| 12 V (Battery+ / Battery−) | — |

> ¹ **NOTE:** The 9.0 V value for 12 V LiFePO4 is too deep — safe cutoff
> for LiFePO4 it is usually **10–11 V** (discharging to 9 V risks damaging the cells). This value
> has not been reconfirmed when `BATTERY_MAX_V` is changed from 12.6 V to 14.4 V. Adjust
> `EFWS_BATTERY_MIN_V` in `.env` after confirming with your specific battery datasheet.

### How EFWS Reads Battery Level

The DC 0–25 V voltage sensor module taps directly to **Battery+ / Battery−**
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

| Component | Voltage | Typical current | Power |
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
> for battery charging. This estimate assumes the siren is normally off.

---

## 6. Safety Notes

- **Do not connect** the load directly to the solar panel terminal without going through the charge controller.
- **Battery polarity** must be checked before wiring — the controller has reverse polarity protection, but other modules (buck converter, relay) can be permanently damaged if reversed.
- **Grounding:** make sure all GND are connected to a common ground point (common ground) to avoid ground loops that cause noisy ADC readings.
- The siren (~1 A at 12 V) **cannot** be powered directly from GPIO — must be via relay.
