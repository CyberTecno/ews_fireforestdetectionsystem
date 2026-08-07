# EFWS — Sensor Specification

Referensi lengkap semua komponen hardware yang digunakan dalam EFWS. Untuk wiring dan
pin assignment, lihat [`docs/Pinout.md`](Pinout.md). Untuk konfigurasi software (channel
ADC, alamat I2C, port serial), lihat [`config/settings.py`](../config/settings.py).

---

## 1. Raspberry Pi 4 Model B

| Parameter | Nilai |
|-----------|-------|
| SoC | Broadcom BCM2711 Quad-Core Cortex-A72 (ARM v8) 64-bit @ 1.5 GHz |
| RAM | 8 GB LPDDR4-3200 |
| Storage | MicroSD 32 GB |
| Ethernet | Gigabit Ethernet |
| Wireless | Wi-Fi 802.11ac (2.4 + 5 GHz), Bluetooth 5.0 BLE |
| USB | 2× USB 3.0, 2× USB 2.0 |
| GPIO | 40-pin header (BCM numbering) |
| Display | 2× Micro HDMI (hingga dual 4K@60fps) |
| Catu daya | USB-C 5 V / 3 A |
| Interface yang dipakai EFWS | SPI (MCP3008), I2C (BME280 + Rainfall), UART (Wind Direction), USB (A7670E + RS485), GPIO (Relay, LED) |

### Breakout: GPIO T-Cobbler
Kabel akan memfasilitasi koneksi GPIO ke breadboard selama
pengembangan/prototyping. Ke PCB pada instalasi permanen.

---

## 2. ADC — MCP3008

| Parameter | Nilai |
|-----------|-------|
| Tipe | 10-bit SAR ADC, 8-channel single-ended |
| Interface | SPI (bus 0, CE0) |
| VREF | 3.3 V (= VDD) |
| Resolusi | 1023 step (0–3.3 V per step ≈ 3.23 mV) |
| Penggunaan | Baca MQ-2, MQ-135, Soil×2, Pressure, Battery, Flame |

**Channel mapping (lihat `config/settings.py`):**

| CH | Sensor | Via LLC | Catatan |
|----|--------|---------|---------|
| 0 | MQ-2 AOUT | ✅ (5V→3.3V) | `ADC_CHANNEL_MQ2` |
| 1 | MQ-135 AOUT | ✅ (5V→3.3V) | `ADC_CHANNEL_MQ135` |
| 2 | Soil Surface AOUT | ✅ (5V→3.3V) | `ADC_CHANNEL_SOIL_SURFACE` |
| 3 | Soil Deep AOUT | ✅ (5V→3.3V) | `ADC_CHANNEL_SOIL_DEEP` |
| 4 | Pressure Sensor | ❌ (via R_BURDEN 100 Ω) | `ADC_CHANNEL_PRESSURE` |
| 5 | Battery Voltage | ❌ (native 3.3V output) | `ADC_CHANNEL_BATTERY` |
| 6 | Flame Sensor AO | ❌ (native 3.3V output) | `ADC_CHANNEL_FLAME_AO` |
| 7 | — | — | Spare, tidak dikabel |

---

## 3. Logic Level Converter (LLC)

| Parameter | Nilai |
|-----------|-------|
| Tipe | Bidirectional, 4-channel |
| Tegangan sisi HV | 5 V (dari Rail 5 V) |
| Tegangan sisi LV | 3.3 V (dari Rail 3.3 V Pi) |
| Channel yang terpakai | 4 dari 4 (MQ-2, MQ-135, Soil Surface, Soil Deep) |

> **Penting:** LLC ini adalah level-shifter **analog linear** untuk sinyal ADC.
> Jangan gunakan tipe digital (TXS0108E, dll.) untuk jalur ini — chip logic-level-shifter
> digital hanya mendeteksi ambang HIGH/LOW, tidak menerjemahkan tegangan analog secara linear.

---

## 4. MQ-2 — Gas & Smoke Sensor

| Parameter | Nilai |
|-----------|-------|
| Gas yang dideteksi | LPG, Butane, Propane, Methane, Hydrogen, Smoke |
| Tegangan kerja | 5 V DC |
| Output dipakai | AOUT (analog) → LLC CH1 → MCP3008 CH0 |
| Output tidak dipakai | DOUT (digital, tidak dikabel) |
| Driver | `sensors/mq2.py` |
| Setting | `config/settings.py`: `ADC_CHANNEL_MQ2`, `SMOKE_MQ2_CRIT_PPM`, `SMOKE_WEIGHT_MQ2` |

**Peran dalam `smokeLevel`:**

```
smokeLevel = (mq2_ppm / MQ2_CRIT_PPM × W_MQ2 + mq135_ppm / MQ135_CRIT_PPM × W_MQ135) × 100
```

Default: `MQ2_CRIT_PPM = 1000`, `W_MQ2 = 0.55` (bobot 55%).

> **Catatan:** Sensor MQ memerlukan warm-up ~2 menit setelah power-on untuk pembacaan
> stabil. Nilai pada menit pertama setelah boot dapat tidak akurat.

---

## 5. MQ-135 — Air Quality Sensor

| Parameter | Nilai |
|-----------|-------|
| Gas yang dideteksi | NH₃, NOx, Alcohol, Benzene, Smoke, CO₂ (indikatif) |
| Tegangan kerja | 5 V DC |
| Output dipakai | AOUT (analog) → LLC CH2 → MCP3008 CH1 |
| Output tidak dipakai | DOUT (digital, tidak dikabel) |
| Driver | `sensors/mq135.py` |
| Setting | `config/settings.py`: `ADC_CHANNEL_MQ135`, `SMOKE_MQ135_CRIT_PPM`, `SMOKE_WEIGHT_MQ135` |

**Peran dalam `smokeLevel`:** bobot 45% (`W_MQ135 = 0.45`), `MQ135_CRIT_PPM = 1000`.

---

## 6. BME280 — Suhu, Kelembapan, Tekanan Udara

| Parameter | Nilai |
|-----------|-------|
| Rentang suhu | −40 hingga +85 °C |
| Akurasi suhu | ±1 °C (tipikal) |
| Rentang kelembapan | 0–100 % RH |
| Akurasi kelembapan | ±3 % RH |
| Rentang tekanan | 300–1100 hPa |
| Tegangan kerja | 3.3 V |
| Interface | I2C (shared bus dengan Rainfall Sensor) |
| Alamat I2C | `0x76` (default; `0x77` jika jumper di-solder) — `EFWS_BME280_ADDR` |
| Driver | `sensors/bme280.py` |

**Field yang dikirim ke API:** `temp`, `humidity` (dalam payload telemetry).
Kolom `pressure_hpa` disimpan di SQLite (`sensor_readings`) tapi tidak dikirim ke API
(tidak ada field pressure ambient di kontrak telemetry).

---

## 7. Soil Moisture Sensor — Tipe Resistif

| Parameter | Nilai |
|-----------|-------|
| Tipe | Resistif (dua probe logam) |
| Tegangan kerja | 5 V DC |
| Output dipakai | AOUT (analog) → LLC → MCP3008 |
| Jumlah probe | 2 (Surface CH2, Deep CH3) |
| Driver | `sensors/soil.py` |

**Konfigurasi dua probe:**

| Probe | Fungsi | Channel | Kedalaman |
|-------|--------|---------|-----------|
| Surface | Kelembapan permukaan | MCP3008 CH2 (via LLC CH3) | 0–30 cm |
| Deep | Kelembapan dalam | MCP3008 CH3 (via LLC CH4) | 30–60 cm |

**Output:** `moisture_percent` (0–100 %). Nilai **rendah = kering = berbahaya**
(`lower_is_worse=True`, threshold default: surface & deep < 10 %).

> **Keterbatasan sensor resistif:** Rentan korosi probe jangka panjang di tanah basah.
> Pertimbangkan kalibrasi ulang setelah 3–6 bulan instalasi di lapangan.

---

## 8. Gravity Tipping Bucket Rainfall Sensor — DFRobot SEN0575

| Parameter | Nilai |
|-----------|-------|
| Resolusi | ±0.2794 mm per tipping |
| Interface | I2C |
| Alamat I2C | `0x1D` — shared bus dengan BME280, tidak bentrok (`RAINFALL_I2C_ADDRESS`) |
| Tegangan kerja | 3.3 V |
| Driver | `sensors/rainfall.py` |
| PID/VID validasi | `0x100C0` / `0x3343` (dicek saat `__init__`) |

**Field yang tersedia dari sensor:**

| Field | Keterangan |
|-------|-----------|
| `rainfall_total_mm` | Counter kumulatif sejak sensor power-on (tidak pernah reset otomatis) |
| `rainfall_last_hour_mm` | Akumulasi dalam window 1 jam (dikonfigurasi lewat `set_rainfall_window(1)`) |
| `tip_counter` | Jumlah tipping raw |
| `working_time_hours` | Uptime sensor |

**Yang dikirim ke API (`payload.telemetry[].rainfall`):**
Delta kumulatif sejak pengiriman telemetry *sebelumnya* (`_rainfall_delta()` di `main.py`),
bukan window 1 jam — agar sesuai dengan interval kirim aktual (30 menit normal / 10 menit emergency).

**Yang dipakai untuk evaluasi alarm threshold:**
`rainfall_last_hour_mm` (window 1 jam dari sensor) — karena evaluasi alarm jalan tiap siklus
sampling (3 menit), bukan tiap pengiriman telemetry.

---

## 9. Submersible Pressure Sensor — Water Level

| Parameter | Nilai |
|-----------|-------|
| Prinsip | Tekanan hidrostatis → arus 4–20 mA |
| Rentang kedalaman | 0–3 m |
| Output | 4–20 mA (current loop) |
| Catu daya | 12 V DC |
| Interface ke Pi | Burden resistor 100 Ω → tegangan 1–5 V → MCP3008 CH4 |
| Driver | `sensors/pressure.py` |
| Setting | `PRESSURE_BURDEN_OHM=100`, `PRESSURE_RANGE_M=3.0` |

**Konversi arus ke kedalaman:**
```
V_burden = current_ma × R_burden / 1000
pct      = (current_ma − 4.0) / 16.0          # 4 mA = 0%, 20 mA = 100%
depth_m  = pct × PRESSURE_RANGE_M
pressure_bar = depth_m × 0.0980665
```

**Fault detection:** `fault_open_loop=True` jika tegangan burden mendekati 0 V
(kabel putus atau sensor tidak terendam / tidak bertekanan).

> **Catatan wiring:** Sensor ini **tidak** melalui LLC. Output burden resistor sudah
> dalam rentang 1–5 V, masih sedikit di atas VREF MCP3008 (3.3 V) pada current > 16.8 mA —
> perhatikan bahwa pembacaan akan saturasi di atas ~2.7 m jika VREF = 3.3 V.
> Jika rentang penuh 3 m dibutuhkan, pastikan VREF di-set ke 5 V atau gunakan burden
> 165 Ω agar 20 mA → 3.3 V persis.

---

## 10. RS485 Anemometer — Kecepatan Angin

| Parameter | Nilai |
|-----------|-------|
| Protokol | RS485 Modbus RTU |
| Catu daya | 12 V DC |
| Slave ID default | `2` (`EFWS_ANEM_SLAVE`) |
| Baudrate | 9600 bps (`EFWS_ANEM_BAUD`) |
| Register kecepatan | `0x0000` (`EFWS_ANEM_REGISTER`) |
| Desimal | 1 digit (`EFWS_ANEM_DECIMALS`) — nilai raw dibagi 10 |
| Interface ke Pi | Industrial USB-to-RS485 converter → `/dev/ttyUSB0` |
| Driver | `sensors/anemometer.py` (`minimalmodbus`) |

**Proteksi scan port:** `scan_ports()` di `sim_detector.py` mengecualikan
`ANEMOMETER_PORT` dari kandidat scan modem 4G, karena mengirim `AT` ke port Modbus
akan merusak frame RTU yang sedang berjalan.

---

## 11. Industrial USB to RS485 Converter

| Parameter | Nilai |
|-----------|-------|
| Konversi | USB ↔ RS485 |
| Protokol | Mendukung Modbus RTU |
| Proteksi | ESD, isolasi galvanik |
| Port di Pi | `/dev/ttyUSB0` (default, bisa beda tergantung urutan enumerate USB) |

---

## 12. Wind Direction Sensor — JL-FSX2

| Parameter | Nilai |
|-----------|-------|
| Prinsip | Hall Effect (sensor A3144) + 1 magnet per posisi |
| Arah terdeteksi | 8 arah (N, NE, E, SE, S, SW, W, NW) |
| Tegangan kerja | 5 V DC |
| Interface | UART TTL (RX/TX) |
| Baudrate | 9600 bps (`EFWS_WIND_DIR_BAUD`) |
| Port di Pi | `/dev/serial0` (GPIO14/GPIO15) — `EFWS_WIND_DIR_PORT` |
| Protokol frame | `*<kode>#` → kode 1–8 |
| Material housing | PLA+ (indoor/prototype) atau ASA (outdoor, tahan UV) |
| Panjang kabel | ±40 cm |
| Driver | `sensors/wind_direction.py` |

**Wiring UART:**
```
Sensor VCC  (merah)  → 3.3 V Pi
Sensor GND  (hitam)  → GND
Sensor TX   (kuning) → GPIO14 (Pin 8, RXD Pi)
Sensor RX   (hijau)  → GPIO15 (Pin 10, TXD Pi)
```

**Prasyarat RPi wajib** (lihat detail di `docs/Pinout.md`):
- `dtoverlay=disable-bt` di `/boot/config.txt` → memindahkan PL011 UART ke GPIO14/15
- Console serial login dimatikan via `raspi-config`
- Tanpa keduanya: baudrate drift / data acak akibat mini-UART clock ikut VPU

---

## 13. Voltage Sensor Module — DC 0–25 V (Battery Monitor)

| Parameter | Nilai |
|-----------|-------|
| Rentang input | 0–25 V (hardware), aman hingga **16.5 V** saat VREF 3.3 V |
| Prinsip | Voltage divider internal rasio 1:5 (TETAP) |
| Output "S" | 0–3.3 V (native, tidak perlu LLC) |
| Tegangan supply sisi logic | 3.3 V Pi |
| Channel ADC | MCP3008 CH5 (`ADC_CHANNEL_BATTERY`) |
| Driver | `sensors/battery.py` |
| Setting | `BATTERY_SENSOR_MAX_V = 16.5 V` (= 3.3 V × 5) |

**Kalkulasi tegangan baterai:**
```
V_battery = (raw_ADC / 1023) × 16.5
```

> **Batas aman input:** 16.5 V (= VREF 3.3 V × rasio 5). Nilai "25 V" yang tercetak
> di modul berlaku jika ADC-nya diberi VREF 5 V — bukan kasus project ini.
> Baterai LiFePO4 max 14.4 V masih dalam batas aman (headroom ~2.1 V).

---

## 14. IR Flame Sensor

| Parameter | Nilai |
|-----------|-------|
| Prinsip | IR photodiode — mendeteksi radiasi IR dari api (750–1100 nm) |
| Output dipakai | AO (analog) → MCP3008 CH6 (langsung, native 3.3 V, tanpa LLC) |
| Output tidak dipakai | DO (digital, tidak dikabel) |
| Tegangan output | Turun saat ada api (default `trigger_below=True`) |
| Threshold deteksi | `FLAME_AO_THRESHOLD_V = 1.65 V` (**PERKIRAAN AWAL, wajib dikalibrasi!**) |
| Driver | `sensors/flame.py` |

**Prosedur kalibrasi lapangan:**
1. `python sensors/flame.py` → catat nilai AO saat kondisi normal (tidak ada api)
2. Dekatkan api kecil (korek api / lilin, jarak aman) → catat nilai AO saat ada api
3. Set `EFWS_FLAME_AO_THRESHOLD_V` di `.env` ke nilai di antara keduanya
4. Jika AO **naik** saat ada api (modul tertentu berbeda polaritas): set `trigger_below=False`

---

## 15. Relay Module — 5 V 1-Channel

| Parameter | Nilai |
|-----------|-------|
| Tegangan kontrol | 5 V (sinyal GPIO Pi melalui transistor driver onboard) |
| GPIO kontrol | GPIO27 (Pin 13) — `EFWS_GPIO_RELAY` |
| Kontak | NO (Normally Open) / NC (Normally Closed) / COM |
| Kapasitas kontak | 10 A / 250 VAC atau 10 A / 30 VDC |
| Beban | Siren 12 V (~1 A) |
| Driver | `alarm/relay.py`, `alarm/siren.py` |

**Logika pulsing alarm (dari `alarm/siren.py`):**

| Level | Perilaku Relay |
|-------|---------------|
| `none` | OFF |
| `warning` | Pulse: ON 0.4 s / OFF 1.6 s (background thread) |
| `critical` | ON terus-menerus |

---

## 16. Siren 12 V

| Parameter | Nilai |
|-----------|-------|
| Tegangan kerja | 12 V DC |
| Konsumsi daya | ~15–20 W |
| Konsumsi arus | ~600–1200 mA (~1 A tipikal) |
| Intensitas suara | ±120 dB |
| Kontrol | Via Relay Module (GPIO27) |

> Siren dicatu langsung dari **bus baterai 12 V** (bukan dari buck converter 5 V),
> dikontrol relay. Konsumsi ~1 A tidak boleh dialirkan lewat GPIO Pi secara langsung
> (batas GPIO Pi ~16 mA per pin).

---

## 17. SIMCom A7670E — 4G LTE Modem

| Parameter | Nilai |
|-----------|-------|
| Standar | LTE Cat-1 |
| Fallback | GSM / GPRS |
| GNSS | Tersedia (tergantung varian — konfirmasi dengan label hardware) |
| Interface | UART (AT Command), USB |
| Tegangan kerja | 3.4–4.2 V (regulasi internal modul / HAT) |
| Port AT | `/dev/ttyUSB2` (default `EFWS_SIM_PORT`, auto-detect via `sim_detector.py`) |
| Baudrate | 115200 bps (`EFWS_A7670E_BAUD`) |
| Driver | `communication/a7670e.py` |

**Command set yang dipakai EFWS:**

| Fungsi | AT Command |
|--------|-----------|
| Cek modul | `AT` |
| Identifikasi | `ATI` (untuk auto-detect di `sim_detector.py`) |
| Signal quality | `AT+CSQ` |
| Network registration | `AT+CREG?` |
| Set APN | `AT+CGDCONT=1,"IP","<APN>"` |
| Nyalakan GNSS | `AT+CGNSSPWR=1` |
| Baca posisi GPS | `AT+CGPSINFO` |
| Matikan GNSS | `AT+CGNSSPWR=0` |

> **Catatan kompatibilitas SIM7600:** Jika dipakai SIM7600 (legacy), command GNSS berbeda:
> `AT+CGPS=1` / `AT+CGPS=0`. Penanganannya otomatis lewat `communication/sim7600_legacy.py`
> + `sim_detector.py` (auto-detect berdasarkan respons `ATI`).
