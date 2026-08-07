# EFWS — Pinout & Wiring Reference

Hardware final:
**Raspberry Pi 4 · MCP3008 (SPI ADC 8-ch) · 1x Logic Level Converter I2C-style
(4-channel, bi-directional, 3.3~5.0V) · MQ-2 · MQ-135 · BME280 (I2C) ·
Soil Probe Surface · Soil Probe Deep · Submersible Pressure Sensor (loop
4-20mA) · Modul Sensor Tegangan DC (baterai) · Flame Sensor (analog) ·
DFRobot Gravity Rainfall Sensor SEN0575 (I2C) · RS485 Anemometer ·
Wind Direction (UART GPIO14/15) · A7670E ATAU SIM7600 (auto-detect, hanya
salah satu dipasang) · Relay 5V · Sirine 12V**

> Tidak ada buzzer terpisah — cukup satu relay + sirine (2 tingkat eskalasi
> lewat pola berdenyut vs nyala terus, lihat `alarm/siren.py`). Threshold &
> keputusan alarm level dievaluasi lokal HANYA untuk menyalakan sirine
> real-time — tidak disimpan ke database lokal, karena evaluasi alarm
> "resmi" ada di backend.

---

## 1. Raspberry Pi 4 — Pin yang Digunakan (BCM Numbering)

| Fungsi | GPIO (BCM) | Pin Fisik | Keterangan |
|--------|-----------|-----------|------------|
| SPI SCLK (MCP3008) | GPIO11 | Pin 23 | Clock SPI |
| SPI MISO (MCP3008) | GPIO9  | Pin 21 | Data dari MCP3008 |
| SPI MOSI (MCP3008) | GPIO10 | Pin 19 | Data ke MCP3008 |
| SPI CE0  (MCP3008) | GPIO8  | Pin 24 | Chip Select |
| I2C SDA (BME280 + Rainfall) | GPIO2  | Pin 3  | Data I2C, bus dipakai bersama |
| I2C SCL (BME280 + Rainfall) | GPIO3  | Pin 5  | Clock I2C, bus dipakai bersama |
| UART RXD (Wind Direction) | GPIO14 | Pin 8  | Terima dari TX sensor (kuning) |
| UART TXD (Wind Direction) | GPIO15 | Pin 10 | Kirim ke RX sensor (hijau) — jarang dipakai, sensor ini one-way |
| Relay Sirine (output) | GPIO27 | Pin 13 | Ke IN relay 5V |
| Status LED (output, opsional) | GPIO23 | Pin 16 | Indikator heartbeat |
| 5V Rail | — | Pin 2 & 4 | Power LLC HV (jangan dari sini kalau arus besar) |
| 3.3V Rail | — | Pin 1 & 17 | Power LLC LV, MCP3008 VDD/VREF, BME280, Rainfall, Wind Direction, Battery sensor (sisi logic), Flame sensor |
| GND | — | Pin 6, 9, 14, 20, 25, 30, 34, 39 | Ground bersama |

Aktifkan interface:
```bash
sudo raspi-config
# Interface Options → SPI → Yes
# Interface Options → I2C → Yes
# Interface Options → Serial Port → login shell lewat serial: No, hardware serial: Yes
```
Lalu tambahkan `dtoverlay=disable-bt` di `/boot/config.txt` dan
`sudo systemctl disable hciuart` — detail & alasannya di bagian
"Wind Direction" pada §5 di bawah.

---

## 2. BME280 & Rainfall Sensor — Wiring I2C (bus dipakai bersama)

Kedua sensor ini I2C native, langsung ke Pi (**tidak lewat MCP3008/LLC**),
dan **berbagi bus I2C yang sama** (SDA/SCL). Ini aman karena alamat I2C
keduanya BEDA — tidak akan saling bentrok.

### BME280 (ambient: suhu / kelembaban / tekanan)
| Pin BME280 | Hubung ke |
|-----------|-----------|
| VIN | Pi 3.3V |
| GND | GND bersama |
| SCL | GPIO3 (Pin 5) |
| SDA | GPIO2 (Pin 3) |

Alamat I2C: `0x76` (atau `0x77` tergantung solder jumper modul).

### DFRobot Gravity Rainfall Sensor (SEN0575) — Tipping Bucket
| Pin sensor | Hubung ke |
|-----------|-----------|
| VCC | Pi 3.3V |
| GND | GND bersama |
| SCL | GPIO3 (Pin 5) — **sama seperti BME280** |
| SDA | GPIO2 (Pin 3) — **sama seperti BME280** |

Alamat I2C: `0x1D` (`RAINFALL_I2C_ADDRESS` di `config/settings.py`) —
**beda dari BME280 (`0x76`/`0x77`)**, jadi wiring paralel di bus I2C yang
sama aman, tidak perlu multiplexer.

```bash
i2cdetect -y 1     # harus muncul DUA alamat: 0x76 (BME280) dan 0x1D (Rainfall)
python3 tests/test_bme280.py
python3 tests/test_rainfall.py
```

---

## 3. MCP3008 — Wiring ke Raspberry Pi

| Pin MCP3008 | Hubung ke | Catatan |
|-------------|-----------|---------|
| VDD (pin 16) | Pi 3.3V | **JANGAN 5V** |
| VREF (pin 15) | Pi 3.3V | Skala ADC 0-3.3V = raw 0-1023 |
| AGND (pin 14) | GND bersama | |
| CLK (pin 13)  | GPIO11 (SCLK) | |
| DOUT (pin 12) | GPIO9 (MISO)  | |
| DIN (pin 11)  | GPIO10 (MOSI) | |
| CS/SHDN (pin 10) | GPIO8 (CE0) | |
| DGND (pin 9)  | GND bersama | |
| CH0 | *(spare, tidak dikabel)* | LLC cuma 4 channel, sudah penuh di CH1-4 |
| CH1-CH4 | Lihat §4 — lewat LLC | MQ-2, MQ-135, Soil Surface, Soil Deep |
| CH5 | Pressure sensor, **langsung tanpa LLC** | Lewat R_BURDEN 100Ω |
| CH6 | Battery/voltage sensor, **langsung tanpa LLC** | Sinyal native 3.3V |
| CH7 | Flame sensor (AO), **langsung tanpa LLC** | Sinyal native 3.3V |

Verifikasi: `ls /dev/spidev*` → harus muncul `/dev/spidev0.0`

---

## 4. Peta Channel MCP3008 — Logic Level Converter (4-channel)

Modul LLC yang dipakai project ini: **"I2C Logic Level Converter" 4-channel,
bi-directional, level data 3.3~5.0V** — didesain untuk sinyal DIGITAL
(I2C/UART/SPI antar board, mis. Arduino↔Pi), BUKAN untuk menerjemahkan
tegangan analog kontinu secara linear.

> ⚠️ **Keterbatasan yang DISADARI & DITERIMA (keputusan user):** MQ-2,
> MQ-135, dan kedua soil probe tetap dikabel lewat LLC ini meski sinyalnya
> analog, bukan digital. Konsekuensinya: pembacaan ADC ke-4 channel ini
> berpotensi tidak sepenuhnya linear/proporsional terhadap tegangan sensor
> sebenarnya (chip level-shifter jenis ini bekerja dengan deteksi ambang
> HIGH/LOW, bukan translasi tegangan kontinu). Ini bukan bug yang belum
> ditemukan — ini trade-off yang sudah diputuskan dengan sadar. Kalau
> nanti pembacaan ke-4 sensor ini terlihat "loncat-loncat"/tidak halus
> dibanding perubahan fisik sensornya, ini penyebab yang paling mungkin
> dicek duluan.
>
> Pressure, Battery, dan Flame sengaja DIKELUARKAN dari LLC ini (lihat
> §5) — baik karena sinyalnya sudah native 3.3V (Battery, Flame) atau
> karena tegangan burden resistor-nya sudah otomatis dalam rentang aman
> tanpa perlu step-down (Pressure).

| LLC | Sisi HV (5V) ← dari sensor | Sisi LV (3.3V) → ke MCP3008 | Channel |
|-----|---------------------------|------------------------------|---------|
| CH1 | MQ-2 **AOUT** | **MCP3008 CH1** | Smoke/gas analog |
| CH2 | MQ-135 **AOUT** | **MCP3008 CH2** | Air quality analog |
| CH3 | Soil Surface **AOUT** | **MCP3008 CH3** | Kelembaban 0-30cm |
| CH4 | Soil Deep **AOUT** | **MCP3008 CH4** | Kelembaban 30-60cm |

*(Modul LLC fisik cuma 4 channel — sudah penuh terpakai di atas. Pressure/
Battery/Flame TIDAK lewat modul ini sama sekali, lihat §5.)*

### Wiring modul LLC

```
LLC:
  HV  pin  ←── 5V  (dari buck converter / Pi pin 2/4)
  LV  pin  ←── 3.3V (dari Pi pin 1/17)
  GND HV   ←── GND bersama
  GND LV   ←── GND bersama
```

---

## 5. Sensor per Sensor — Detail Wiring

### MQ-2 (Smoke / Combustible Gas)
| Pin sensor | Hubung ke |
|-----------|-----------|
| VCC | 5V (langsung dari sumber, bukan dari Pi GPIO 5V) |
| GND | GND bersama |
| AOUT | LLC **CH1** → MCP3008 **CH1** |

> Heater ~150mA — power langsung dari buck converter, jangan dari Pi GPIO 5V.

### MQ-135 (Air Quality)
| Pin sensor | Hubung ke |
|-----------|-----------|
| VCC | 5V (langsung dari sumber) |
| GND | GND bersama |
| AOUT | LLC **CH2** → MCP3008 **CH2** |

### Soil Moisture Probe — Surface (0-30cm)
| Pin probe | Hubung ke |
|----------|-----------|
| VCC | 5V |
| GND | GND bersama |
| AOUT | LLC **CH3** → MCP3008 **CH3** |

### Soil Moisture Probe — Deep (30-60cm)
| Pin probe | Hubung ke |
|----------|-----------|
| VCC | 5V |
| GND | GND bersama |
| AOUT | LLC **CH4** → MCP3008 **CH4** |

> Kalibrasi wajib per probe (lihat `sensors/soil.py`): dry_raw di udara kering, wet_raw terendam air.

### Submersible Pressure Sensor — loop 4-20mA (Ketinggian Air) — TIDAK lewat LLC

Sensor ini **loop-powered 2-kabel** (bukan 0-5V langsung), jadi wiring-nya beda
dari 4 sensor analog di atas: butuh **burden resistor** untuk mengubah arus
loop menjadi tegangan yang bisa dibaca ADC. Dengan R_BURDEN **100Ω**
(`PRESSURE_BURDEN_OHM` di `config/settings.py`), tegangan yang dihasilkan
sudah otomatis berada di rentang aman 0-3.3V — **tidak perlu LLC sama sekali**,
langsung ke MCP3008.

```
PSU 12-24V (+) ──────────► Sensor Loop V+
                                  │
                    Sensor (variabel 4-20mA sesuai tekanan/kedalaman)
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  R_BURDEN = 100Ω        │
                    │  (presisi, low-drift)   │
                    └────────────┬────────────┘
                                 │ tap di titik ini → 0.4-2.0V
                                 ▼
                    LANGSUNG ke MCP3008 CH5 (TANPA LLC)
                                 │
                                 ▼
                      Ground bersama & PSU (−)
```

| Titik | Hubung ke |
|-------|-----------|
| Loop V+ | PSU 12-24V (+) — **bukan** dari Pi/buck converter 5V |
| Loop keluar (setelah sensor) | Ujung atas R_BURDEN (100Ω) |
| Ujung bawah R_BURDEN | GND bersama & PSU (−) |
| Titik sambung sensor/R_BURDEN | **LANGSUNG** ke MCP3008 **CH5** (tanpa LLC) |

**Kenapa 100Ω?**
- 4mA × 100Ω = **0.4V** → level "kosong" (0m)
- 20mA × 100Ω = **2.0V** → level "penuh" (`PRESSURE_RANGE_M`, default 3m — sesuaikan datasheet sensor Anda)

Rentang 0.4-2.0V ini sudah jauh di bawah VREF (3.3V), jadi aman dibaca
langsung tanpa level-shifting apa pun.

Formula konversi ada di `sensors/pressure.py`. **Sesuaikan** `EFWS_PRESSURE_RANGE_M`
di `.env` dengan rentang kedalaman/tekanan sensor fisik Anda (banyak varian: 0-3m,
0-5m, 0-10m). Payload API mengirim dua nilai dari sensor ini: `waterLevel` (meter)
dan `pressure` (bar, konversi hidrostatik).

### Modul Sensor Tegangan DC (Battery) — TIDAK lewat LLC

Modul ini sudah punya voltage divider resistif internal PASIF (rasio 1:5
tetap), tidak perlu buat sendiri. **Sama seperti Pressure, modul ini TIDAK
dikabel lewat LLC** — sinyal keluarannya sudah native 3.3V (lihat catatan
di `sensors/battery.py`, rujukan: osoyoo.com/2024/09/08/lesson-13-voltage-
sensor-for-raspberry-pi/). Rating pabrikan modul ini sering ditulis "0-25V",
tapi itu cuma berlaku kalau ADC-nya diberi VREF 5V. Di project ini (MCP3008
VREF 3.3V), **batas aman input yang benar adalah 16.5V** (3.3V x rasio 5) —
baterai Anda (max 14.4V) masih di bawah batas ini dengan headroom ~2.1V, aman.

Modul ini punya **5 titik sambung, di DUA sisi berbeda** — jangan tertukar:

| Pin modul | Sisi | Hubung ke |
|-----------|------|-----------|
| **+** | Output/logic (ke Pi) | 3.3V Pi (Pin 1 atau 17) |
| **−** | Output/logic (ke Pi) | GND bersama |
| **S** | Output/logic (ke Pi) | **LANGSUNG** ke MCP3008 **CH6** (tanpa LLC) |
| **anode / IN+** | Input (yang diukur) | Terminal Battery+ (12V LiFePO4/sejenis, max 14.4V) |
| **cathode / IN−** | Input (yang diukur) | Terminal Battery− |

Formula konversi ada di `sensors/battery.py`. Kalibrasi `BATTERY_MAX_V` /
`BATTERY_MIN_V` di `.env` sesuai spesifikasi baterai Anda — **`BATTERY_MAX_V`
sudah di-set 14.4V** (dikonfirmasi). `BATTERY_MIN_V` (default 9.0V) **belum**
ikut dikonfirmasi ulang — untuk pack LiFePO4 12V, titik kosong yang aman
biasanya ~10-11V, bukan 9V (terlalu dalam). Mohon dicek/disesuaikan.

### Flame Sensor (AO, analog) — TIDAK lewat LLC

| Pin sensor | Hubung ke |
|-----------|-----------|
| VCC | Sesuai datasheet modul (biasanya 3.3-5V) |
| GND | GND bersama |
| AO | **LANGSUNG** ke MCP3008 **CH7** (channel terakhir, tanpa LLC) |

Sinyal AO modul ini native 3.3V, tidak butuh step-down. **Threshold voltase
belum dikalibrasi ke unit fisik** (`FLAME_AO_THRESHOLD_V`, placeholder 1.65V)
— lihat prosedur kalibrasi di docstring `sensors/flame.py`. TIDAK pakai
GPIO/DO — sensor ini murni dibaca lewat MCP3008.

### RS485 Anemometer (Modbus RTU) — Wind Speed
| Koneksi | Hubung ke |
|---------|-----------|
| A (D+) | USB-RS485 converter terminal A |
| B (D−) | USB-RS485 converter terminal B |
| VCC | 12V atau 5V sesuai datasheet unit |
| GND | GND bersama |

USB-RS485 → port USB Pi → muncul sebagai `/dev/ttyUSB0`. **Tidak perlu LLC.**
Parameter Modbus **DIKONFIRMASI** (sudah terbukti berhasil di lapangan):
Port `/dev/ttyUSB0`, Slave ID `2`, Baudrate `9600` — sudah jadi default di
`config/settings.py` (`ANEMOMETER_PORT`/`ANEMOMETER_SLAVE_ID`/`ANEMOMETER_BAUDRATE`).

### Wind Direction — UART (GPIO14/15), BUKAN lewat MCP3008/LLC

| Kabel | Hubung ke |
|-------|-----------|
| Merah (VCC) | 3.3V (pin 1 atau 17) |
| Hitam (GND) | GND |
| Kuning (TX sensor) | GPIO14 / pin 8 (RXD Pi) |
| Hijau (RX sensor) | GPIO15 / pin 10 (TXD Pi) |

Protokol: baris teks `*<kode>#` lewat UART software `/dev/serial0`, kode
1-8 = N/NE/E/SE/S/SW/W/NW. Baudrate default 9600 (`EFWS_WIND_DIR_BAUD`).

> ⚠️ **Wajib dicek sebelum pasang:** di Raspberry Pi 4, GPIO14/15 secara
> default dipakai Bluetooth (mini-UART yang baudrate-nya ikut ngambang
> mengikuti frekuensi VPU). Supaya sensor ini stabil:
> 1. `sudo raspi-config` → Interface Options → Serial Port → login shell
>    lewat serial: **No**, hardware serial port: **Yes**.
> 2. Tambahkan `dtoverlay=disable-bt` di `/boot/config.txt`, lalu
>    `sudo systemctl disable hciuart`, lalu reboot.
> 3. Setelah reboot, `/dev/serial0` akan otomatis nyambung ke PL011 (full
>    UART) yang stabil, bukan mini-UART.
>
> Kalau langkah ini belum dilakukan, sensor bisa saja "kelihatan" jalan
> tapi datanya acak/putus-putus.

### A7670E ATAU SIM7600 (pilih salah satu)

Tidak perlu wiring berbeda antara keduanya — **hanya pasang salah satu modul**,
`communication/sim_detector.py` akan auto-detect mana yang terpasang
(`AT+CGNSSPWR` → A7670E, `AT+CGPS` → SIM7600) dan software menyesuaikan sendiri.

| Koneksi | Detail |
|---------|--------|
| Power | Sesuai board HAT (biasanya 5V dari Pi atau 3.7-4.2V Li-ion terpisah) |
| Data | USB ke Pi — muncul sebagai beberapa `/dev/ttyUSBx` |
| Antena LTE | Wajib |
| Antena GNSS | Wajib terpisah |
| SIM card | Pasang sebelum power-on |

```bash
ls /dev/ttyUSB*
python3 tests/test_sim_detector.py   # konfirmasi modul mana yang terdeteksi
```

### Relay 5V → Sirine 12V

```
Sisi kontrol (Pi 3.3V GPIO):          Sisi daya tinggi (12V):
  GPIO27 ──────────────► IN relay       Battery+ ─── relay COM
  5V     ──────────────► VCC relay            Relay NO ─── Sirine (+)
  GND    ──────────────► GND relay            Sirine (−) ─── Battery−
```

> ⚠️ Jalur 12V sirine **tidak pernah** boleh menyentuh pin Pi manapun.
> Tidak ada buzzer terpisah — satu relay ini menangani 2 tingkat eskalasi
> (WARNING = berdenyut pelan, CRITICAL = nyala terus), lihat `alarm/siren.py`.

---

## 6. Diagram Blok Sinyal Lengkap

```
MQ-2 AOUT (5V)      ──┐
MQ-135 AOUT (5V)    ──┤    LLC (1 modul, 4 channel — SEMUA terpakai)
Soil-S AOUT (5V)    ──┤    CH1-4 (5V) → (3.3V)
Soil-D AOUT (5V)    ──┘         │
                                ▼
                     MCP3008 CH1-CH4  (SPI0)
                                │
Pressure via R_BURDEN 100Ω (native 3.3V, TANPA LLC) ──► MCP3008 CH5 ──┤
Battery Sensor S (native 3.3V, TANPA LLC)          ──► MCP3008 CH6 ──┤
Flame Sensor AO (native 3.3V, TANPA LLC)           ──► MCP3008 CH7 ──┤
                                                                       │
BME280 (I2C, addr 0x76) ───────────────────────────────────────────┤
Rainfall SEN0575 (I2C, addr 0x1D — bus sama dgn BME280) ───────────┤
RS485 Anemometer (USB, Slave ID 2) ─────────────────────────────────┤
Wind Direction (UART GPIO14/15) ────────────────────────────────────┤
A7670E / SIM7600 (USB) ──────────────────────────────────────────────┤
                                ▼
                       Raspberry Pi 4 — main.py
                       1) baca semua sensor
                       2) SIMPAN ke SQLite dulu (sensor_readings)
                       3) evaluasi lokal → sirine (real-time, tidak disimpan)
                       4) coba kirim ke API — gagal? masuk antrian (api_queue)
                       5) cek sinyal ulang tiap 2 menit → auto-flush antrian
                                │ GPIO27
                                ▼
                        Relay 5V ──► Sirine 12V
```

---

## 7. Catu Daya Tiap Beban

| Beban | Tegangan | Sumber | Catatan |
|-------|---------|--------|---------|
| Raspberry Pi 4 | 5V | Buck converter output | Via GPIO pin 2/4 atau USB-C |
| MCP3008 VDD/VREF | 3.3V | Pi 3.3V rail | |
| BME280 | 3.3V | Pi 3.3V rail | I2C langsung, tanpa LLC |
| Rainfall SEN0575 | 3.3V | Pi 3.3V rail | Bus sama dgn BME280 |
| LLC LV | 3.3V | Pi 3.3V rail | Hanya untuk 4 channel: MQ-2/MQ-135/Soil x2 |
| LLC HV | 5V | Buck converter / Pi 5V rail | Hanya untuk 4 channel: MQ-2/MQ-135/Soil x2 |
| MQ-2 / MQ-135 heater | 5V | Buck converter langsung | ~150mA masing-masing |
| Soil probe ×2 | 5V atau 3.3V | Sesuai datasheet probe | |
| Submersible pressure sensor | 12-24V (loop) | **PSU terpisah**, bukan dari Pi/buck 5V | Loop-powered, R_BURDEN 100Ω, langsung ke CH5 |
| Modul sensor tegangan (battery) | Sisi ukur: pasif, tap Battery+/−. Sisi logic ("+"/"−"): **3.3V dari Pi** | Pi 3.3V rail (untuk pin "+"/"−" logic-nya) | **BUKAN tanpa suplai** — pin "+"/"−" wajib ke 3.3V/GND Pi, langsung ke CH6 |
| Flame sensor | 3.3-5V sesuai datasheet | Sesuai datasheet modul | AO native 3.3V, langsung ke CH7 |
| RS485 anemometer | 12V atau 5V | Sesuai datasheet unit | Slave ID 2, Baudrate 9600 |
| A7670E/SIM7600 | 5V atau 3.7-4.2V | Sesuai board HAT | |
| Relay coil | 5V | Pi 5V rail | |
| Sirine | 12V | Battery (via relay NO/COM) | |

---

## 8. Checklist Sebelum Power-On Pertama

```
[ ] SPI aktif (raspi-config → Interface → SPI)
[ ] I2C aktif (raspi-config → Interface → I2C)
[ ] Common ground: Pi, MCP3008, LLC, semua sensor, relay, PSU pressure sensor → satu GND
[ ] LLC: HV=5V, LV=3.3V, HANYA 4 channel terpakai (CH1-CH4: MQ-2/MQ-135/Soil x2)
[ ] MCP3008 VDD & VREF ke 3.3V (bukan 5V)
[ ] MCP3008 CH0 sengaja kosong (spare)
[ ] R_BURDEN 100Ω terpasang benar di loop pressure sensor, tap LANGSUNG ke MCP3008 CH5 (TANPA LLC)
[ ] PSU loop pressure sensor terpisah dari Pi/buck converter 5V
[ ] Modul sensor tegangan: sisi ukur (anode/cathode) tap langsung ke Battery+/− (bukan lewat relay); sisi logic ("+"/"−") ke 3.3V/GND Pi; "S" LANGSUNG ke MCP3008 CH6 (TANPA LLC)
[ ] Flame sensor AO LANGSUNG ke MCP3008 CH7 (TANPA LLC) — threshold BELUM dikalibrasi, cek sensors/flame.py sebelum deploy
[ ] BME280 (addr 0x76) dan Rainfall SEN0575 (addr 0x1D) berbagi bus I2C yang sama — alamat beda, aman
[ ] Jalur 12V sirine hanya lewat relay COM/NO, tidak menyentuh Pi
[ ] Hanya SATU modul terpasang: A7670E ATAU SIM7600 (jangan dua-duanya)
[ ] Antena LTE + GNSS terpasang
[ ] SIM card terpasang sebelum modul dinyalakan
[ ] Anemometer RS485: Slave ID 2, Baudrate 9600 (sudah default di settings.py)
[ ] Wind Direction: dtoverlay=disable-bt sudah di-set di /boot/config.txt, console-over-serial dimatikan

Verifikasi software:
[ ] ls /dev/spidev*    → /dev/spidev0.0 ada
[ ] i2cdetect -y 1     → DUA alamat muncul: 0x76 (BME280) dan 0x1D (Rainfall)
[ ] ls /dev/ttyUSB*    → beberapa port ada (modem + anemometer)
[ ] python3 tests/test_all_sensors.py     → semua sensor OK
[ ] python3 tests/test_offline_queue_integrity.py → integritas queue OK
[ ] python3 tests/test_sim_detector.py    → modul SIM teridentifikasi
```
