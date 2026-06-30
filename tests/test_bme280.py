"""
TEST 4 — BME280 (Temperature / Humidity / Pressure, I2C)
Usage: python3 tests/test_bme280.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("  TEST BME280 (I2C)")
print("=" * 60)
print("Pastikan I2C sudah diaktifkan: sudo raspi-config -> Interface -> I2C -> Yes")
print("Lalu cek device terdeteksi: i2cdetect -y 1  (harus muncul 0x76 atau 0x77)\n")

try:
    from sensors.bme280 import BME280Sensor
    sensor = BME280Sensor()
    print("[OK] BME280 berhasil diinisialisasi.\n")
except Exception as e:
    print(f"[FAIL] Gagal inisialisasi: {e}")
    print("\nKemungkinan penyebab:")
    print("  - I2C belum diaktifkan")
    print("  - Alamat I2C salah (cek dengan i2cdetect -y 1, default 0x76)")
    print("  - Wiring SDA/SCL terbalik atau longgar")
    sys.exit(1)

print("Membaca tiap 2 detik selama 20 detik (Ctrl+C untuk stop)...\n")
try:
    for i in range(10):
        d = sensor.read()
        print(f"temp={d['temperature_c']}°C | humidity={d['humidity_percent']}% | "
              f"pressure={d['pressure_hpa']}hPa")
        time.sleep(2)
except KeyboardInterrupt:
    pass

print("\n[SELESAI] Nilai harus masuk akal (suhu ruangan 20-35°C) - kalau 0 atau angka aneh, cek wiring.")
