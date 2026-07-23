"""
TEST — Gravity Rainfall Sensor (DFRobot SEN0575)

Usage:

python3 tests/test_rainfall.py
"""

import os
import sys
import time
from datetime import datetime

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from sensors.rainfall import RainfallSensor

print("=" * 80)
print(" TEST — Gravity Rainfall Sensor SEN0575")
print("=" * 80)

try:

    sensor = RainfallSensor()

except Exception as e:

    print("Sensor gagal diinisialisasi")
    print(e)
    sys.exit(1)

print()

print("Tekan CTRL+C untuk berhenti.\n")

try:

    while True:

        data = sensor.read()

        print("=" * 80)

        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        print()

        print(f"Total Rainfall   : {data['rainfall_total_mm']:.4f} mm")

        print(f"1 Hour Rainfall  : {data['rainfall_1h_mm']:.4f} mm")

        print(f"Rainfall Delta   : {data['rainfall_delta_mm']:.4f} mm")

        print(f"Rain Rate        : {data['rain_rate_mmh']:.2f} mm/hour")

        print(f"Tip Counter      : {data['raw_tip_count']}")

        print(f"Working Time     : {data['working_time_hours']:.2f} hour")

        if data["is_raining"]:
            print("\nStatus           : 🌧️  RAINING")
        else:
            print("\nStatus           : ☀️  NO RAIN")

        print()

        time.sleep(2)

except KeyboardInterrupt:

    print("\nProgram dihentikan.")