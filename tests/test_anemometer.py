"""
TEST 6 — RS485 Anemometer (Modbus RTU, via USB-RS485 converter)
Usage: python3 tests/test_anemometer.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("  TEST RS485 Anemometer")
print("=" * 60)
print("Check first USB-RS485 converter detected: ls /dev/ttyUSB*")
print("Also check the Modbus register & function code according to your unit's datasheet")
print("(beda merk anemometer biasanya beda register address - lihat config/settings.py)\n")

try:
    from sensors.anemometer import AnemometerSensor
    sensor = AnemometerSensor()
    print("[OK] Anemometer initialized successfully.\n")
except Exception as e:
    print(f"[FAIL] Failed initialization:{e}")
    print("\nPossible causes:")
    print("- Wrong port (check EFWS_ANEM_PORT in .env, usually /dev/ttyUSB0)")
    print("  - RS485 A/B (D+/D-) wiring is reversed")
    print("- Incorrect Modbus slave ID (default 1, check dip-switch/manual unit)")
    sys.exit(1)

print("Read every 2 seconds for 20 seconds (Ctrl+C to stop). Blow on the sensor to see the change.\n")
try:
    for i in range(10):
        d = sensor.read()
        if d.get("error"):
            print(f"[ERROR] {d['error']}")
        else:
            print(f"wind_speed={d['speed_ms']} m/s")
        time.sleep(2)
except KeyboardInterrupt:
    pass
