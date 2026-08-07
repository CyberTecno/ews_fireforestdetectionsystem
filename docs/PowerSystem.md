# EFWS — Power System

Sistem beroperasi sepenuhnya off-grid, mengandalkan panel surya sebagai sumber energi
utama dengan baterai LiFePO4 sebagai penyangga. Semua komponen dicatu dari rel tegangan
yang diderivasikan dari bus baterai 12 V.

---

## Diagram Alir Daya

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
                ├─ [Raspberry Pi 4] (via USB-C, maks. 3 A)                      │
                │     │ 3.3 V Rail (dari Pi onboard regulator)                  │
                │     ├─ BME280                                                 │
                │     ├─ Rainfall Sensor SEN0575 (I2C)                          │
                │     ├─ Wind Direction Sensor JL-FSX2 (UART)                   │
                │     ├─ MCP3008 VDD & VREF                                     │
                │     ├─ Logic Level Converter — sisi LV                        │
                │     ├─ Flame Sensor AO (langsung ke MCP3008 CH6)              │
                │     └─ Voltage Sensor Module — sisi logic "+"                 │
                │                                                               │
                ├─ Logic Level Converter — sisi HV (5 V)                        │
                │     ├─ MQ-2 (5 V)                                             │
                │     ├─ MQ-135 (5 V)                                           │
                │     ├─ Soil Moisture Surface (5 V)                            │
                │     └─ Soil Moisture Deep (5 V)                               │
                └─ Relay Module 5 V (kontrol GPIO27)                            │
                                                                                │
[Baterai LiFePO4 12 V] ◄────────────────────────────────────────────────────────┘
  (buffer & catu saat awan/malam)
```

---

## 1. Panel Surya

| Parameter | Nilai |
|-----------|-------|
| Tipe | Monokristalin |
| Daya puncak | 100 W |
| Tegangan titik daya maks (Vmp) | ~18–22 V (tipikal panel 100 W mono) |
| Arus titik daya maks (Imp) | ~5–6 A |
| Aplikasi | Sumber energi utama off-grid |

---

## 2. Solar Charge Controller

| Parameter | Nilai |
|-----------|-------|
| Teknologi | Intelligent PWM |
| Rating arus | 20 A |
| Tegangan sistem | 12 V / 24 V (deteksi otomatis) |
| Display | LCD graphical |
| Proteksi | Over-temperature, tegangan rendah baterai, polaritas terbalik |
| USB output | Dual USB 5 V (pengisian perangkat eksternal) |
| Fitur | Pengaturan charge voltage, low-voltage disconnect, pemilihan tipe baterai |

> **Catatan pengaturan:** Pastikan tipe baterai di-set ke **LiFePO4** (bukan Lead-Acid/AGM)
> agar tegangan pengisian dan cut-off sesuai dengan karakteristik kimia LiFePO4
> (charge ≈ 14.4 V, cut-off ≈ 10–11 V).

---

## 3. Baterai LiFePO4

| Parameter | Nilai | Sumber |
|-----------|-------|--------|
| Kimia | LiFePO4 (Lithium Iron Phosphate) | dikonfirmasi user |
| Tegangan nominal | 12 V | — |
| Tegangan PENUH (charge cutoff) | **14.4 V** | `settings.BATTERY_MAX_V` |
| Tegangan KOSONG (discharge cutoff) | **9.0 V** | `settings.BATTERY_MIN_V` ¹ |
| Bus tegangan | 12 V (Battery+ / Battery−) | — |

> ¹ **CATATAN:** Nilai 9.0 V untuk LiFePO4 12 V terlalu dalam — titik kosong yang aman
> untuk LiFePO4 biasanya **10–11 V** (discharge ke 9 V berisiko merusak sel). Nilai ini
> belum dikonfirmasi ulang ketika `BATTERY_MAX_V` diubah dari 12.6 V ke 14.4 V. Sesuaikan
> `EFWS_BATTERY_MIN_V` di `.env` setelah dikonfirmasi dengan datasheet baterai spesifik Anda.

### Cara EFWS Membaca Level Baterai

Sensor tegangan modul DC 0-25 V (lihat §6) di-tap langsung ke **Battery+ / Battery−**
(bukan dari output buck converter). Kalkulasi di `sensors/battery.py`:

```
V_battery = (raw_ADC / 1023) × BATTERY_SENSOR_MAX_V
battery%  = (V_battery − BATTERY_MIN_V) / (BATTERY_MAX_V − BATTERY_MIN_V) × 100
```

Dengan `BATTERY_SENSOR_MAX_V = 16.5 V` (= VREF 3.3 V × rasio divider 1:5 modul).

---

## 4. Buck Converter (12 V → 5 V)

| Parameter | Nilai |
|-----------|-------|
| Input | 6–36 V DC |
| Output | 5 V DC |
| Arus maks output | 3–5 A |
| Efisiensi | > 90% |
| Fungsi | Mencatu Raspberry Pi (via USB-C) dan Logic Level Converter sisi HV |

---

## 5. Distribusi & Estimasi Konsumsi Daya

| Komponen | Tegangan | Arus Tipikal | Daya |
|----------|----------|-------------|------|
| Raspberry Pi 4 (idle-moderate) | 5 V | ~0.6–1.0 A | ~3–5 W |
| A7670E (LTE transmit) | ~3.7 V (internal) | ~0.5 A puncak | ~2 W puncak |
| MQ-2 + MQ-135 (heater aktif) | 5 V | ~150 mA masing-masing | ~1.5 W total |
| RS485 Anemometer | 12 V | ~50 mA | ~0.6 W |
| Submersible Pressure Sensor | 12 V | ~20–30 mA (loop 4-20 mA) | ~0.3 W |
| Siren (saat alarm aktif) | 12 V | ~600–1200 mA | ~7–14 W |
| Relay Module | 5 V | ~70–80 mA (coil aktif) | ~0.4 W |
| Sensor lain (BME280, soil, dll.) | 3.3 V | < 10 mA total | < 0.1 W |
| **Total (tanpa siren)** | — | — | **~8–10 W** |
| **Total (siren aktif)** | — | — | **~15–24 W** |

> Panel 100 W pada kondisi irradiasi baik (~5 jam peak sun/hari) menghasilkan
> ~500 Wh/hari. Konsumsi normal ~8–10 W × 24 jam = ~192–240 Wh/hari → surplus
> untuk pengisian baterai. Siren diasumsikan tidak aktif terus-menerus.

---

## 6. Catatan Keselamatan

- **Jangan hubungkan** beban langsung ke terminal panel surya tanpa melalui charge controller.
- **Polaritas baterai** wajib diperiksa sebelum wiring — controller punya proteksi polaritas terbalik, tapi modul lain (buck converter, relay) bisa rusak permanen jika terbalik.
- **Grounding:** pastikan semua GND terhubung ke titik ground bersama (common ground) untuk menghindari ground loop yang menyebabkan pembacaan ADC noise.
- Siren (~1 A @ 12 V) **TIDAK** boleh dicatu dari GPIO langsung — wajib melalui relay.
