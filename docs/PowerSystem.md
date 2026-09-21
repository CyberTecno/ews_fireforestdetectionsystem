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
| Pi 3.3 V rail | MCP3008 VDD/VREF, BME280, rainfall sensor, and low-voltage side of the level converter | Supplies verified 3.3 V devices. Check the wind direction module's voltage requirements separately. |
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

> **Controller settings:** Select the LiFePO4 battery profile and confirm charging and disconnect voltages against the specific battery and controller manuals. The application's percentage references below do not set the controller's cutoff.

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

### How EFWS reads battery level

The battery voltage module measures **Battery+ / Battery−**, rather than the buck converter output. `sensors/battery.py` calculates:

```
V_battery = (raw_ADC / 1023) × BATTERY_SENSOR_MAX_V
battery%  = (V_battery − BATTERY_MIN_V) / (BATTERY_MAX_V − BATTERY_MIN_V) × 100
```

With `BATTERY_SENSOR_MAX_V = 16.5 V` (= VREF 3.3 V × 1:5 divider ratio module).

---

## 4. Buck converter (12 V → 5 V)

| Parameter | Value |
|-----------|-------|
| Input | 6–36 V DC |
| Output | 5 V DC |
|Output max current| 3–5 A |
| Efficiency | > 90% |
| Function | Supplies the Raspberry Pi through USB-C and other verified 5 V loads |

---

## 5. Power consumption estimate

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

> With five peak-sun hours, a 100 W panel has a theoretical yield of about 500 Wh/day before controller, wiring, temperature, and weather losses. An 8–10 W continuous load uses about 192–240 Wh/day. Size the battery and panel for local conditions and modem transmit peaks; the siren adds a temporary load.

---

## 6. Safety notes

- **Do not connect** the load directly to the solar panel terminal without going through the charge controller.
- **Battery polarity** must be checked before wiring — the controller has reverse polarity protection, but other modules (buck converter, relay) can be permanently damaged if reversed.
- **Grounding:** connect the Pi, ADC, sensors, and loop supply to the common reference required by the wiring design. Check for ground loops that could add noise to ADC readings.
- The siren (~1 A at 12 V) must be powered through the relay, never from a Pi GPIO pin.
