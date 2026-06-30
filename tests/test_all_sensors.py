"""
TEST 10 — Semua sensor sekaligus (mode hardware, satu putaran baca)

Jalankan ini PALING TERAKHIR, setelah semua test individual (test_mcp3008,
test_gas_sensors, test_flame, test_bme280, test_soil, test_anemometer)
lulus satu-satu. Ini mensimulasikan persis apa yang main.py lakukan tiap
siklus baca, TANPA mengirim ke API dan TANPA trigger alarm fisik.

Usage: python3 tests/test_all_sensors.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("  TEST SEMUA SENSOR (mode hardware, real)")
print("=" * 60)

results = {}

tests = [
    ("MQ-2 (asap/gas)",        "sensors.mq2",        "MQ2Sensor"),
    ("MQ-135 (kualitas udara)", "sensors.mq135",      "MQ135Sensor"),
    ("Flame sensor",            "sensors.flame",      "FlameSensor"),
    ("BME280",                  "sensors.bme280",     "BME280Sensor"),
    ("Soil moisture",           "sensors.soil",       "SoilMoistureSensor"),
    ("Anemometer (RS485)",      "sensors.anemometer", "AnemometerSensor"),
]

for name, module_path, class_name in tests:
    print(f"\n--- {name} ---")
    try:
        module = __import__(module_path, fromlist=[class_name])
        cls = getattr(module, class_name)
        sensor = cls()
        reading = sensor.read()
        print(f"OK: {reading}")
        results[name] = "OK"
    except Exception as e:
        print(f"GAGAL: {e}")
        results[name] = "GAGAL"

print("\n" + "=" * 60)
print("  RINGKASAN")
print("=" * 60)
for name, status in results.items():
    icon = "✅" if status == "OK" else "❌"
    print(f"  {icon} {status:6s} {name}")

if "GAGAL" in results.values():
    print("\nUntuk sensor yang GAGAL, cek:")
    print("  1. Wiring sesuai docs/Pinout.md")
    print("  2. SPI aktif (untuk MQ-2/MQ-135/soil): ls /dev/spidev*")
    print("  3. I2C aktif (untuk BME280): i2cdetect -y 1")
    print("  4. Paket pip terinstall: pip install -r requirements.txt")
    print("  5. Pin GPIO/channel benar di .env atau config/settings.py")
    sys.exit(1)
else:
    print("\nSemua sensor OK. Lanjut ke tests/test_relay_siren.py lalu jalankan main.py.")
