# EFWS — Wiring & Pinout Reference (MCP3008 + Logic Level Converter + A7670E)

Update wiring untuk hardware aktual:
**Raspberry Pi 4, A7670E/SIM7670E (4G LTE Cat-1), MCP3008 (ADC SPI),
Logic Level Converter, MQ-2, MQ-135, Flame Sensor 4-wire, BME280,
Soil Moisture Probe, RS485 Anemometer, Relay 5V + Sirine 12V 120dB.**

## Ringkasan arsitektur sinyal

```
                         ┌─────────────────────────────┐
   MQ-2 (5V AOUT) ───┐   │                             │
   MQ-135 (5V AOUT)──┤   │   Logic Level Converter     │   3.3V sisi LV
   Soil probe (5V)───┼──►│   (HV=5V sisi sensor,       │──────────────┐
   Flame AO (5V)──────┘  │    LV=3.3V sisi Pi/MCP3008) │              │
                         └─────────────────────────────┘              │
                                                                      ▼
                                                              ┌──────────────┐
                                                              │   MCP3008    │
                                                              │ (SPI0, CE0)  │
                                                              │ CH0=MQ2      │──► SPI ──► Raspberry Pi 4
                                                              │ CH1=MQ135    │
                                                              │ CH2=Soil     │
                                                              │ CH3=FlameAO  │
                                                              └──────────────┘

   Flame DO (5V) ────► Logic Level Converter ────► GPIO17 (3.3V)
   BME280 (I2C, modul breakout biasanya sudah 3.3V regulator onboard) ──► I2C langsung ke Pi
   RS485 Anemometer ──► USB-RS485 converter ──► USB port Pi (tidak perlu level converter)
   A7670E/SIM7670E ──► USB atau UART ──► Pi (4G data + AT command + GNSS)
   Relay 5V (kontrol GPIO27) ──► men-switch 12V ke Sirine 120dB+LED flasher
```

## 1. MCP3008 (ADC SPI 8-channel)

| Pin MCP3008 | Hubung ke                      | Catatan |
|-------------|--------------------------------|---------|
| VDD         | Pi 3.3V (pin 1 atau 17)        | **JANGAN 5V** — VDD MCP3008 menentukan range output digital |
| VREF        | Pi 3.3V (sama dengan VDD)      | Jadi skala ADC 0-1023 = 0-3.3V |
| AGND        | Pi GND                         | Ground analog |
| CLK         | GPIO11 (SCLK)                  | Pin fisik 23 |
| DOUT        | GPIO9 (MISO)                   | Pin fisik 21 |
| DIN         | GPIO10 (MOSI)                  | Pin fisik 19 |
| CS/SHDN     | GPIO8 (CE0)                    | Pin fisik 24 |
| DGND        | Pi GND                         | Ground digital |
| CH0-CH7     | Sinyal analog dari sensor (lewat logic level converter) | Lihat tabel channel di bawah |

**Channel mapping default** (bisa diubah lewat `.env`: `EFWS_ADC_MQ2`, dst):

| Channel MCP3008 | Sensor                     |
|------------------|---------------------------|
| CH0              | MQ-2 (AOUT)               |
| CH1              | MQ-135 (AOUT)             |
| CH2              | Soil moisture probe (AOUT)|
| CH3              | Flame sensor (AO, opsional) |
| CH4-CH7          | Cadangan/ekspansi         |

Aktifkan SPI dulu sebelum wiring/testing:
```bash
sudo raspi-config   # Interface Options -> SPI -> Yes
ls /dev/spidev*     # harus muncul /dev/spidev0.0
```

## 2. Logic Level Converter (WAJIB untuk semua sinyal analog 5V)

MQ-2, MQ-135, soil probe, dan flame sensor (AO & DO) semuanya output **0-5V**,
sedangkan MCP3008/GPIO Pi hanya tahan **3.3V max**. Logic level converter
WAJIB dipasang di antara keduanya — tanpa ini, channel ADC akan clipping
(nilai mentok di ~3.3V terus, tidak bisa baca range penuh) dan berisiko
merusak chip MCP3008/GPIO dalam jangka panjang.

| Sisi HV (High Voltage, 5V) | Sisi LV (Low Voltage, 3.3V) |
|------------------------------|-------------------------------|
| HV (power)                  | ke 5V Pi                      |
| GND (HV)                    | GND bersama (HV & LV sama-sama ke GND Pi) |
| HV1 ← MQ-2 AOUT             | LV1 → MCP3008 CH0             |
| HV2 ← MQ-135 AOUT           | LV2 → MCP3008 CH1             |
| HV3 ← Soil probe AOUT       | LV3 → MCP3008 CH2             |
| HV4 ← Flame sensor AO       | LV4 → MCP3008 CH3             |
| HV5 ← Flame sensor DO       | LV5 → Pi GPIO17               |
| LV (power)                   | ke 3.3V Pi                    |

Modul logic level converter umum (mis. TXS0108E / BSS138 4-channel) punya
4-8 channel — pastikan cukup untuk 5 sinyal di atas (4 analog + 1 digital DO),
atau pakai 2 modul kecil kalau channel-nya kurang.

## 3. Sensor analog (lewat MCP3008 + logic level converter)

| Sensor              | Pin sensor | Hubung ke |
|----------------------|------------|-----------|
| MQ-2                | VCC        | 5V Pi |
|                      | GND        | GND Pi |
|                      | AOUT       | Logic level converter HV1 → MCP3008 CH0 |
| MQ-135              | VCC        | 5V Pi |
|                      | GND        | GND Pi |
|                      | AOUT       | Logic level converter HV2 → MCP3008 CH1 |
| Soil Moisture Probe (waterproof) | VCC | 5V Pi (atau 3.3V jika probe Anda support — cek datasheet) |
|                      | GND        | GND Pi |
|                      | AOUT       | Logic level converter HV3 → MCP3008 CH2 |

## 4. Flame Sensor (4-wire: VCC, GND, DO, AO)

| Pin       | Hubung ke |
|-----------|-----------|
| VCC       | 5V Pi |
| GND       | GND Pi |
| DO (digital, aktif-LOW) | Logic level converter HV5 → GPIO17 (Pin fisik 11) |
| AO (analog, opsional)   | Logic level converter HV4 → MCP3008 CH3 |

Kalau AO tidak dikabel, set `read_analog=False` saat membuat `FlameSensor()`
(default sudah `False` di `main.py`/mock — cukup aman dibiarkan, DO saja
sudah cukup untuk deteksi ya/tidak ada api).

## 5. BME280 (Temperature/Humidity/Pressure, I2C)

| Pin BME280 | Hubung ke |
|------------|-----------|
| VIN        | 3.3V Pi (Pin 1) — **kebanyakan breakout BME280 sudah punya regulator onboard, JANGAN kasih 5V kecuali modul Anda eksplisit support** |
| GND        | GND Pi |
| SCL        | GPIO3 / SCL1 (Pin fisik 5) |
| SDA        | GPIO2 / SDA1 (Pin fisik 3) |

BME280 modul breakout biasanya **tidak perlu** logic level converter karena
sudah didesain untuk 3.3V I2C langsung. Cek datasheet modul spesifik Anda.

Aktifkan I2C dulu:
```bash
sudo raspi-config   # Interface Options -> I2C -> Yes
i2cdetect -y 1       # harus muncul 0x76 (atau 0x77)
```

## 6. RS485 Anemometer

| Pin Anemometer | Hubung ke |
|------------------|-----------|
| A (D+)           | USB-RS485 converter A |
| B (D-)           | USB-RS485 converter B |
| VCC              | Sumber daya sesuai datasheet (5V atau 12V — banyak anemometer RS485 butuh 12V) |
| GND              | GND bersama |

USB-RS485 converter tancap ke port USB Pi langsung (muncul sebagai
`/dev/ttyUSB0` atau serupa) — **tidak perlu** logic level converter karena
USB-RS485 converter sudah handle level sendiri.

```bash
ls /dev/ttyUSB*   # cek converter terdeteksi
```

## 7. A7670E / SIM7670E (4G LTE Cat-1 + GNSS)

| Koneksi | Detail |
|---------|--------|
| Power   | Sesuai modul (banyak board A7670E HAT punya regulator onboard, terima 5V dari Pi atau baterai Li-ion terpisah) |
| Data    | USB (paling mudah — modul muncul sebagai beberapa `/dev/ttyUSBx`) ATAU UART langsung (GPIO14 TXD / GPIO15 RXD, perlu disable serial console Pi dulu) |
| SIM card | Pasang sebelum power-on |
| Antena LTE | WAJIB dipasang untuk sinyal 4G |
| Antena GNSS | WAJIB dipasang terpisah untuk fitur GPS |

Setelah boot, cek port mana yang dipakai untuk AT command:
```bash
ls /dev/ttyUSB*
# Biasanya: ttyUSB0=diagnostic, ttyUSB1=GPS NMEA, ttyUSB2=AT command, ttyUSB3=modem PPP
```
Set port yang benar di `.env` -> `EFWS_SIM_PORT=/dev/ttyUSBx`.

**Catatan command GNSS**: A7670E/SIM7670E pakai `AT+CGNSSPWR=1` (BUKAN
`AT+CGPS=1` seperti SIM7600) — ini sudah disesuaikan di
`communication/sim7600.py`.

## 8. Relay 5V → Sirine 12V/24V/220V 120dB (dengan LED flasher)

| Sisi kontrol (Pi)     | Hubung ke |
|--------------------------|-----------|
| Relay VCC                | 5V Pi |
| Relay GND                | GND Pi |
| Relay IN                 | GPIO27 (Pin fisik 13) — kebanyakan modul relay (dengan optocoupler) sudah kompatibel 3.3V logic, biasanya **tidak perlu** level converter, tapi cek datasheet modul relay Anda |

| Sisi daya tinggi (sirine) | Hubung ke |
|------------------------------|-----------|
| Sumber 12V (+)               | Relay COM |
| Relay NO (Normally Open)     | Sirine (+) |
| Sirine (-)                   | Sumber 12V (-) / GND |

**PERINGATAN KESELAMATAN:**
- Jalur 12V sirine **TIDAK PERNAH** boleh tersambung langsung ke pin Pi
  manapun — hanya lewat kontak kering relay (COM/NO).
- Sirine 120dB **sangat keras** — uji di tempat yang aman, beri tahu orang
  sekitar sebelum trigger test (lihat `tests/test_relay_siren.py`).
- Kalau modul relay Anda tidak punya flyback diode bawaan di coil-nya,
  tambahkan satu (kebanyakan modul relay jadi sudah include ini).

## 9. Checklist sebelum power-on pertama kali

1. [ ] SPI aktif (`sudo raspi-config` → Interface → SPI)
2. [ ] I2C aktif (`sudo raspi-config` → Interface → I2C)
3. [ ] Semua sinyal analog 5V (MQ-2, MQ-135, soil, flame AO/DO) **sudah**
       lewat logic level converter sebelum masuk MCP3008/GPIO — cek ulang,
       ini penyebab kerusakan paling umum kalau terlewat
4. [ ] VDD & VREF MCP3008 di 3.3V (bukan 5V)
5. [ ] Ground semua modul (Pi, MCP3008, logic level converter, sensor,
       A7670E, relay) **disatukan** — common ground, kalau tidak pembacaan
       analog akan ngaco
6. [ ] Jalur 12V sirine HANYA lewat kontak relay (COM/NO), tidak pernah
       menyentuh pin Pi manapun
7. [ ] Antena LTE + GNSS A7670E sudah terpasang
8. [ ] `ls /dev/spidev*`, `i2cdetect -y 1`, `ls /dev/ttyUSB*` semua
       menunjukkan device yang diharapkan SEBELUM menjalankan test script apapun
