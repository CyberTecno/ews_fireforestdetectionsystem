from smbus2 import SMBus
import time

ADDR = 0x1D
bus = SMBus(1)

while True:
    values = []

    for reg in range(0x00, 0x30):
        try:
            val = bus.read_byte_data(ADDR, reg)
            values.append(f"{val:02X}")
        except Exception:
            values.append("--")

    print(" ".join(values))
    time.sleep(1)