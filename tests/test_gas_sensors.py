"""
TEST 2 — MQ-2 (asap/gas) & MQ-135 (air quality)
Run AFTER test_mcp3008.py is successful.

IMPORTANT: MQ-2 and MQ-135 require time to HEAT (preheat) the internal heater
about 24-48 hours before the reading is stable & accurate. For wiring testing
course (not accuracy), wait at least 2-3 minutes after power-on.

Usage: python3 tests/test_gas_sensors.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.mq2 import MQ2Sensor
from sensors.mq135 import MQ135Sensor

print("=" * 60)
print("TEST MQ-2 & MQ-135 (via MCP3008)")
print("=" * 60)

try:
    mq2 = MQ2Sensor()
    mq135 = MQ135Sensor()
    print("[OK] Both sensors initialized successfully.\n")
except Exception as e:
    print(f"[FAIL] Failed initialization:{e}")
    sys.exit(1)

print("Read every 2 seconds for 20 seconds (Ctrl+C to stop)...")
print("Try holding a recently extinguished match (smoke) to MQ-2 to see the ppm rise.\n")

try:
    for i in range(10):
        d2 = mq2.read()
        d135 = mq135.read()
        print(f"MQ-2:   voltage={d2['voltage']:.3f}V  ppm={d2['ppm']:.1f}   |   "
              f"MQ-135: voltage={d135['voltage']:.3f}V  ppm={d135['ppm']:.1f}")
        time.sleep(2)
except KeyboardInterrupt:
    pass

print("\n[NOTE] The ppm values ​​above are NOT calibrated - just a linear approximation.")
print("For production, calibrate R0 in clean air according to datasheet MQ-2/MQ-135.")
