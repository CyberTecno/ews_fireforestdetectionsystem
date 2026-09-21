"""
TEST — IR Flame Sensor (AO analog via MCP3008, DO NOT use GPIO/DO)
Usage: python3 tests/test_flame.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.flame import FlameSensor

print("=" * 60)
print("  TEST IR Flame Sensor (AO analog via MCP3008)")
print("=" * 60)

try:
    sensor = FlameSensor()
    print(f"[OK] Flame sensor initialized (CH{sensor.channel}, "
          f"threshold={sensor.threshold_v}V, trigger_below={sensor.trigger_below}).\n")
except Exception as e:
    print(f"[FAIL] Failed initialization:{e}")
    sys.exit(1)

print("NOT CALIBRATED YET -- note down the AO value in normal conditions FIRST, then")
print("bring a safe small fire close and note again, then set")
print("EFWS_FLAME_AO_THRESHOLD_V is between the two (see sensors/flame.py).")
print("Reads every 0.5 seconds for 20 seconds (Ctrl+C to stop)...\n")

try:
    for i in range(40):
        d = sensor.read()
        flag = "🔥 API DETECTED!" if d["flame_detected"] else "normal"
        print(f"AO={d['analog_voltage']:.3f}V | flame_detected={d['flame_detected']!s:5}  {flag}")
        time.sleep(0.5)
except KeyboardInterrupt:
    pass

print("\n[NOTE] If flame_detected is ALWAYS True even though there is no fire, perhaps:")
print("- Wrong threshold direction -> try FlameSensor(trigger_below=False)")
print("- FLAME_AO_THRESHOLD_V has not been calibrated to your physical unit")
