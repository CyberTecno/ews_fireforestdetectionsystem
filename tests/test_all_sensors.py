"""
TEST — Semua sensor sekaligus (hardware, satu putaran baca)

Jalankan PALING TERAKHIR setelah semua test individual lulus.
Mensimulasikan satu siklus baca lengkap seperti yang dilakukan main.py,
termasuk kalkulasi smokeLevel dari MQ-2 + MQ-135.

Usage: python3 tests/test_all_sensors.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

def smoke(mq2, mq135):
    n2   = min(mq2   / settings.SMOKE_MQ2_CRIT_PPM,   1.5)
    n135 = min(mq135 / settings.SMOKE_MQ135_CRIT_PPM, 1.5)
    return round(min((n2 * settings.SMOKE_WEIGHT_MQ2 + n135 * settings.SMOKE_WEIGHT_MQ135) * 100, 100.0), 2)

print("=" * 60)
print("  TEST SEMUA SENSOR (hardware, satu putaran)")
print("=" * 60)

TESTS = [
    ("MQ-2",              "sensors.mq2",       "MQ2Sensor"),
    ("MQ-135",            "sensors.mq135",      "MQ135Sensor"),
    ("BME280",            "sensors.bme280",     "BME280Sensor"),
    ("Soil (dual)",       "sensors.soil",       "SoilMoistureSensor"),
    ("Anemometer",        "sensors.anemometer", "AnemometerSensor"),
    ("Submersible Pressure", "sensors.pressure", "PressureWaterSensor"),
    ("Battery Voltage",   "sensors.battery",    "BatterySensor"),
]

results = {}
sensor_data = {}
for name, mod_path, cls_name in TESTS:
    print(f"\n  {name}")
    try:
        mod = __import__(mod_path, fromlist=[cls_name])
        sensor = getattr(mod, cls_name)()
        reading = sensor.read()
        print(f"  → {reading}")
        results[name] = "OK"
        sensor_data[name] = reading
    except Exception as e:
        print(f"  → GAGAL: {e}")
        results[name] = "GAGAL"

# smokeLevel dari MQ-2 + MQ-135
if "MQ-2" in sensor_data and "MQ-135" in sensor_data:
    sl = smoke(sensor_data["MQ-2"].get("ppm",0), sensor_data["MQ-135"].get("ppm",0))
    sl_status = "CRITICAL" if sl>=70 else "WARNING" if sl>=60 else "normal"
    print(f"\n  smokeLevel (gabungan MQ-2+MQ-135): {sl}%  [{sl_status}]")
    print(f"    MQ2={settings.SMOKE_WEIGHT_MQ2*100:.0f}% weight + MQ135={settings.SMOKE_WEIGHT_MQ135*100:.0f}% weight")
    print(f"    Warning≥{settings.SMOKE_WARNING_PCT}%, Critical≥{settings.SMOKE_CRITICAL_PCT}%")

print("\n" + "=" * 60)
print("  RINGKASAN")
print("=" * 60)
for name, status in results.items():
    print(f"  {'✅' if status=='OK' else '❌'} {status:6s}  {name}")

if "GAGAL" in results.values():
    print("\nUntuk sensor GAGAL:")
    print("  - SPI: ls /dev/spidev*  (MQ-2/MQ-135/soil/pressure — semua lewat MCP3008)")
    print("  - I2C: i2cdetect -y 1   (BME280)")
    print("  - USB: ls /dev/ttyUSB*  (anemometer RS485)")
    print("  - Cek docs/Pinout.md untuk wiring lengkap")
    sys.exit(1)
else:
    print("\n✅ Semua sensor OK. Siap jalankan main.py.")
