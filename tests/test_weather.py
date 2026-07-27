#!/usr/bin/env python3
"""
Combined Weather Sensor Test

Tests:
- BME280
- DFRobot Rainfall Sensor (SEN0575)

Refresh interval: 2 seconds
Stop with CTRL + C
"""

import time

from sensors.bme280 import BME280Sensor
from sensors.rainfall import RainfallSensor


def print_separator():
    print("=" * 65)


def main():

    print_separator()
    print("EFWS Weather Sensor Test")
    print(print_separator())

    # -----------------------------
    # Initialize Sensors
    # -----------------------------

    try:
        bme = BME280Sensor()
        print("✅ BME280 initialized")
    except Exception as e:
        print(f"❌ BME280 initialization failed: {e}")
        return

    try:
        rain = RainfallSensor()

        if rain.begin():
            print("✅ Rainfall sensor initialized")
            print(f"Firmware : {rain.firmware_version()}")
        else:
            print("❌ Rainfall sensor not detected")
            return

    except Exception as e:
        print(f"❌ Rainfall initialization failed: {e}")
        return

    print_separator()

    try:

        while True:

            bme_data = bme.read()
            rain_data = rain.read()

            print_separator()

            print("🌡 Ambient Conditions")
            print(f"Temperature      : {bme_data['temperature_c']:.2f} °C")
            print(f"Humidity         : {bme_data['humidity_percent']:.2f} %")
            print(f"Pressure         : {bme_data['pressure_hpa']:.2f} hPa")

            print()

            print("🌧 Rainfall Sensor")
            print(f"Total Rainfall   : {rain_data['rainfall_total_mm']:.4f} mm")
            print(f"Rain (Last Hour) : {rain_data['rainfall_last_hour_mm']:.4f} mm")
            print(f"Tip Counter      : {rain_data['tip_counter']}")
            print(f"Working Time     : {rain_data['working_time_hours']:.2f} hours")

            print()

            # Optional simple status
            if rain_data["rainfall_last_hour_mm"] > 0:
                print("Status           : 🌧 RAIN DETECTED")
            else:
                print("Status           : ☀️ NO RAIN")

            time.sleep(2)

    except KeyboardInterrupt:

        print("\n")
        print_separator()
        print("Weather test stopped by user.")
        print_separator()


if __name__ == "__main__":
    main()