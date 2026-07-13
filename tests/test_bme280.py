"""
TEST — BME280 (suhu / kelembaban / tekanan ambient, I2C)

Cek dulu sebelum run:
  sudo raspi-config → Interface Options → I2C → Yes
  i2cdetect -y 1     → harus muncul 0x76 (atau 0x77 kalau alamat berbeda)

Usage: python3 tests/test_bme280.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.bme280 import BME280Sensor

print("=" * 60)
print("  TEST — BME280 (I2C)")
print("=" * 60)

try:
    sensor = BME280Sensor()
except Exception as e:
    print(f"❌ Gagal inisialisasi: {e}")
    print("Cek: i2cdetect -y 1 harus menunjukkan alamat BME280 (0x76/0x77)")
    sys.exit(1)

print("Membaca 5x, tiap 2 detik (Ctrl+C untuk stop lebih awal)...\n")
try:
    for i in range(5):
        reading = sensor.read()
        if reading.get("error"):
            print(f"  [{i+1}] ❌ error: {reading['error']}")
        else:
            print(f"  [{i+1}] temp={reading['temperature_c']}°C  "
                  f"hum={reading['humidity_percent']}%  "
                  f"pressure={reading['pressure_hpa']}hPa")
        time.sleep(2)
    print("\n✅ BME280 terbaca dengan baik.")
except KeyboardInterrupt:
    print("\nDihentikan oleh user.")
