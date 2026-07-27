#!/usr/bin/env python3

"""
Dump seluruh register penting Rainfall Sensor.

Tidak menggunakan driver.
Langsung membaca register I2C.

CTRL+C untuk berhenti.
"""

import time
from smbus2 import SMBus

ADDR = 0x1D

REGISTERS = {
    0x00: ("PID", 4),
    0x0A: ("VERSION", 2),
    0x0C: ("TIME_RAINFALL", 4),
    0x10: ("TOTAL_RAINFALL", 4),
    0x14: ("RAW_DATA", 4),
    0x18: ("WORKING_TIME", 2),
}

bus = SMBus(1)

print("=" * 70)
print("Rainfall Register Monitor")
print("=" * 70)

try:

    while True:

        print()

        for reg, (name, size) in REGISTERS.items():

            try:

                data = bus.read_i2c_block_data(
                    ADDR,
                    reg,
                    size
                )

                little = int.from_bytes(
                    data,
                    "little"
                )

                print(
                    f"0x{reg:02X} {name:18s}"
                    f" Raw={data}"
                    f" Hex={[hex(x) for x in data]}"
                    f" Int={little}"
                )

            except Exception as e:

                print(
                    f"0x{reg:02X} {name:18s} ERROR : {e}"
                )

        time.sleep(2)

except KeyboardInterrupt:

    bus.close()

    print("\nStopped.")