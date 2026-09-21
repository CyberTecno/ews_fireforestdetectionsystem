"""
TEST — Submersible Pressure Sensor (water level, 4-20mA loop via burden resistor)

Check first before running:
ls /dev/spidev* → there must be /dev/spidev0.0
R_BURDEN 100Ω is installed in the loop, the tap is DIRECTLY to MCP3008 CH4 (WITHOUT
LLC -- burden voltage 0.4-2.0V is automatically within the safe range ADC)
PSU loop 12-24V is already on (this sensor is loop-powered, NOT from Pi/buck 5V)

What to check:
1. Sensors can be read without exception.
2. current_ma is in the reasonable range of 4-20mA (beyond that = strange signal /loop is problematic).
3. fault_open_loop is not on continuously (if it is → the loop is probably broken).
4. reasonable depth_m (0 to PRESSURE_RANGE_M).

Usage: python3 tests/test_pressure.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from sensors.pressure import PressureWaterSensor

print("=" * 60)
print("  TEST — Submersible Pressure Sensor (MCP3008 CH4)")
print("=" * 60)
print(f"R_BURDEN    : {settings.PRESSURE_BURDEN_OHM}Ω")
print(f"mA range:{settings.PRESSURE_MIN_MA}-{settings.PRESSURE_MAX_MA}mA")
print(f"Range depth : 0-{settings.PRESSURE_RANGE_M}m (adjust EFWS_PRESSURE_RANGE_M if datasheet is different)\n")

try:
    sensor = PressureWaterSensor()
except Exception as e:
    print(f"❌ Initialization failed:{e}")
    print("Check: ls /dev/spidev* should show /dev/spidev0.0")
    sys.exit(1)

N = 5
fault_count = 0
readings = []

print(f"Read{N}x, every 2 seconds (Ctrl+C to stop early)...\n")
try:
    for i in range(N):
        r = sensor.read()
        readings.append(r)
        if r["fault_open_loop"]:
            fault_count += 1
        flag = "  ⚠️ fault_open_loop!" if r["fault_open_loop"] else ""
        print(f"  [{i+1}] current={r['current_ma']}mA  depth={r['depth_m']}m  "
              f"pressure={r['pressure_bar']}bar{flag}")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nStopped by user.")
    sys.exit(0)

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

problems = []

ma_values = [r["current_ma"] for r in readings]
out_of_range = [ma for ma in ma_values if ma < 3.5 or ma > 21.0]
if out_of_range:
    problems.append(f"There is a current_ma reading outside the reasonable range of 4-20mA:{out_of_range}")
else:
    print(f"✅ current_ma are all in a reasonable range ({min(ma_values)}-{max(ma_values)}mA)")

if fault_count == N:
    problems.append("fault_open_loop occurs on ALL readings — the loop may be broken/not connected")
elif fault_count > 0:
    print(f"  ⚠️  fault_open_loop occurred {fault_count}/{N} times — check the loop connection if this is unexpected")
else:
    print("✅ No fault_open_loop during test")

depth_values = [r["depth_m"] for r in readings]
if any(d < 0 or d > settings.PRESSURE_RANGE_M for d in depth_values):
    problems.append(f"There is a depth_m outside the range 0-{settings.PRESSURE_RANGE_M}m")
else:
    print(f"✅ depth_m all in the range 0-{settings.PRESSURE_RANGE_M}m ({min(depth_values)}-{max(depth_values)}m)")

print()
if problems:
    print("❌ Something to check:")
    for p in problems:
        print(f"   - {p}")
    print("\nSee docs/Pinout.md section 'Submersible Pressure Sensor' for wiring details.")
    sys.exit(1)
else:
    print("✅ Submersible pressure sensor reads well.")
