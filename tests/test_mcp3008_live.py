import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.mcp3008 import MCP3008

adc = MCP3008()

print("=" * 70)
print("LIVE MCP3008 MONITOR")
print("Ctrl+C untuk keluar")
print("=" * 70)

try:
    while True:
        os.system("clear")

        print("=" * 70)
        print("LIVE MCP3008 MONITOR")
        print("=" * 70)

        for ch in range(8):

            raw = adc.read_raw(ch)
            volt = adc.read_voltage(ch)

            percent = raw / 1023 * 100

            bar = "█" * int(percent / 2)

            print(
                f"CH{ch}: "
                f"{raw:4d}/1023   "
                f"{volt:5.2f} V   "
                f"{percent:6.1f}%   "
                f"{bar}"
            )

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStop monitoring.")

finally:
    adc.close()