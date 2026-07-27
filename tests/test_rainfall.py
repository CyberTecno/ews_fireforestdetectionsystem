#!/usr/bin/env python3

import time

from sensors.rainfall import RainfallSensor


def main():

    sensor = RainfallSensor()

    print("=" * 60)
    print("DFRobot Rainfall Sensor Test")
    print("=" * 60)

    if not sensor.begin():
        print("❌ Rainfall sensor not detected.")
        return

    print("✅ Sensor detected")
    print("Firmware :", sensor.firmware_version())
    print()

    try:

        while True:

            data = sensor.read()

            print("=" * 60)
            print(f"Total Rainfall : {data['rainfall_total_mm']:.4f} mm")
            print(f"Last 1 Hour    : {data['rainfall_last_hour_mm']:.4f} mm")
            print(f"Tip Counter    : {data['tip_counter']}")
            print(f"Working Time   : {data['working_time_hours']:.2f} hours")

            time.sleep(2)

    except KeyboardInterrupt:

        print()
        print("Stopped by user.")


if __name__ == "__main__":
    main()