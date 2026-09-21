"""
TEST — BME280 (ambient temperature/humidity/pressure, I2C)

Check first before running:
  sudo raspi-config → Interface Options → I2C → Yes
i2cdetect -y 1 → should display 0x76 (or 0x77 if the address is different)

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
    print(f"❌ Initialization failed:{e}")
    print("Check: i2cdetect -y 1 should show the BME280 address (0x76/0x77)")
    sys.exit(1)

print("Reading 5x, every 2 seconds (Ctrl+C to stop early)...\n")
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
    print("\n✅ BME280 reads fine.")
except KeyboardInterrupt:
    print("\nStopped by user.")
