"""
TEST 2 — MQ-2 & MQ-135 Continuous Monitor

- Berjalan terus hingga Ctrl+C
- Menampilkan Raw ADC, Voltage, dan estimasi PPM
- Memberikan warning jika wiring/sensor bermasalah

Usage:
    python3 tests/test_gas_sensors.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.mq2 import MQ2Sensor
from sensors.mq135 import MQ135Sensor

print("=" * 70)
print("        MQ-2 & MQ-135 LIVE MONITOR")
print("=" * 70)
print("Tekan Ctrl+C untuk berhenti.\n")

try:
    mq2 = MQ2Sensor()
    mq135 = MQ135Sensor()

except Exception as e:
    print(f"[ERROR] Gagal inisialisasi sensor : {e}")
    sys.exit(1)


def check_sensor(name, data):
    """
    Analisa sederhana terhadap hasil pembacaan sensor.
    """

    voltage = data["voltage"]
    ppm = data["ppm"]

    # Jika class sensor menyediakan nilai raw ADC, gunakan.
    raw = data.get("raw", None)

    if raw is None:
        raw_text = "-"
    else:
        raw_text = str(raw)

    status = "OK"

    if raw is not None:

        if raw == 0:
            status = "⚠ ADC = 0 (kemungkinan sensor belum tersambung / VCC hilang / AO short ke GND)"

        elif raw >= 1023:
            status = "⚠ ADC = MAX (AO ke 3.3V, wiring salah, atau sensor saturasi)"

        elif raw < 5:
            status = "⚠ Nilai sangat rendah"

        elif raw > 1018:
            status = "⚠ Nilai sangat tinggi"

    else:

        if voltage < 0.02:
            status = "⚠ Tegangan hampir 0V"

        elif voltage > 3.25:
            status = "⚠ Tegangan mendekati VREF"

    return raw_text, voltage, ppm, status


try:

    while True:

        os.system("clear")

        print("=" * 70)
        print("        MQ-2 & MQ-135 LIVE MONITOR")
        print("=" * 70)

        mq2_data = mq2.read()
        mq135_data = mq135.read()

        raw, volt, ppm, status = check_sensor("MQ2", mq2_data)

        print("MQ-2")
        print("-----------------------------------------------")
        print(f"RAW      : {raw}")
        print(f"Voltage  : {volt:.3f} V")
        print(f"PPM      : {ppm:.1f}")
        print(f"Status   : {status}")

        print()

        raw, volt, ppm, status = check_sensor("MQ135", mq135_data)

        print("MQ-135")
        print("-----------------------------------------------")
        print(f"RAW      : {raw}")
        print(f"Voltage  : {volt:.3f} V")
        print(f"PPM      : {ppm:.1f}")
        print(f"Status   : {status}")

        print("\n" + "=" * 70)

        print("Interpretasi:")

        print("✓ Voltage berubah saat diberi asap/gas      -> Sensor bekerja")
        print("✓ PPM berubah                              -> Pembacaan normal")
        print("⚠ Voltage = 0V terus                       -> AO/GND/VCC bermasalah")
        print("⚠ Voltage = 3.3V terus                     -> AO short/VCC/saturasi")
        print("⚠ Tidak berubah sama sekali                -> Sensor belum panas atau wiring salah")

        time.sleep(1)

except KeyboardInterrupt:

    print("\n")
    print("=" * 70)
    print("Monitoring dihentikan.")
    print("=" * 70)