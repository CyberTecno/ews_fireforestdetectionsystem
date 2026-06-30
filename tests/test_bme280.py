"""
TEST 4 — BME280 (Temperature / Humidity / Pressure)

Continuous Monitoring
Ctrl+C untuk keluar

Usage:
    python3 tests/test_bme280.py
"""

import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 70)
print("              TEST BME280 (I2C)")
print("=" * 70)
print("Pastikan I2C aktif:")
print("  sudo raspi-config -> Interface -> I2C -> Yes")
print()
print("Cek alamat sensor:")
print("  i2cdetect -y 1")
print("Harus muncul 0x76 atau 0x77")
print()

try:
    from sensors.bme280 import BME280Sensor

    sensor = BME280Sensor()

except Exception as e:

    print(f"[ERROR] Gagal inisialisasi BME280")
    print(e)

    print("\nKemungkinan penyebab:")
    print("- I2C belum aktif")
    print("- Wiring SDA/SCL salah")
    print("- Alamat I2C salah")
    print("- Sensor rusak")

    sys.exit(1)


def check_temperature(t):
    if t is None:
        return "ERROR"

    if t < -40 or t > 85:
        return "ERROR"

    if t < 0 or t > 60:
        return "WARNING"

    return "OK"


def check_humidity(h):
    if h is None:
        return "ERROR"

    if h < 0 or h > 100:
        return "ERROR"

    return "OK"


def check_pressure(p):
    if p is None:
        return "ERROR"

    if p < 300 or p > 1100:
        return "WARNING"

    return "OK"


print("Monitoring dimulai...")
print("Tekan Ctrl+C untuk berhenti.")

try:

    while True:

        os.system("clear")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data = sensor.read()

        temp = data["temperature_c"]
        hum = data["humidity_percent"]
        pres = data["pressure_hpa"]

        print("=" * 70)
        print("LIVE BME280 MONITOR")
        print("=" * 70)

        print(f"Waktu : {now}")
        print()

        print(f"Temperature : {temp:.2f} °C")
        print(f"Humidity    : {hum:.2f} %")
        print(f"Pressure    : {pres:.2f} hPa")

        print()

        print("Status")

        print(f"Temperature : {check_temperature(temp)}")
        print(f"Humidity    : {check_humidity(hum)}")
        print(f"Pressure    : {check_pressure(pres)}")

        print()

        if (
            check_temperature(temp) == "OK"
            and check_humidity(hum) == "OK"
            and check_pressure(pres) == "OK"
        ):
            print("✓ Sensor bekerja normal")

        else:
            print("⚠ Periksa sensor atau wiring")

        print()
        print("Ctrl+C untuk keluar")

        time.sleep(2)

except KeyboardInterrupt:

    print("\n")
    print("=" * 70)
    print("Monitoring dihentikan.")
    print("=" * 70)