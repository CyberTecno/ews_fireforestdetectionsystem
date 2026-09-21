"""
TEST — DC Voltage Sensor Module (battery, DIRECT to MCP3008 CH5, WITHOUT LLC)

Check first before running:
ls /dev/spidev* → there must be /dev/spidev0.0
The S pin of the module is connected DIRECTLY to the MCP3008 CH5 (NOT via LLC -- signal
this module is native 3.3V, see sensors/battery.py)
Module "+"/"−" pin (logic side, DIFFERENT from measured IN+/IN−) to 3.3V/GND Pi

Usage: python3 tests/test_battery.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.battery import BatterySensor

print("=" * 60)
print("  TEST — Battery Voltage Sensor (MCP3008 CH5)")
print("=" * 60)

sensor = BatterySensor()
print("Reading 5x, every 2 seconds (Ctrl+C to stop early)...\n")
try:
    for i in range(5):
        reading = sensor.read()
        print(f"  [{i+1}] voltage={reading['voltage']}V  percent={reading['percent']}%")
        time.sleep(2)
    print("\n✅ Battery sensor reads well.")
except KeyboardInterrupt:
    print("\nStopped by user.")
