"""
TEST 1 — MCP3008 (ADC SPI)
Run BEFORE testing any analog sensor (MQ-2/MQ-135/soil), because
all sensors depend on this chip.

Usage: python3 tests/test_mcp3008.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.mcp3008 import MCP3008

print("=" * 60)
print("  TEST MCP3008 (SPI ADC)")
print("=" * 60)
print("Make sure SPI is enabled: sudo raspi-config -> Interface -> SPI -> Yes")
print("Then check the device: ls /dev/spidev* (should appear /dev/spidev0.0)\n")

try:
    adc = MCP3008()
    print(f"[OK] MCP3008 opens on SPI bus={adc.bus}, device={adc.device}, VREF={adc.vref}V\n")
except Exception as e:
    print(f"[FAIL] Cannot open MCP3008:{e}")
    print("\nPossible causes:")
    print("- SPI has not been activated (raspi-config)")
    print("- Spidev is not installed (pip install Spidev)")
    print("- Wiring CLK/DOUT/DIN/CS is wrong (check docs/Pinout.md)")
    sys.exit(1)

print("Reads all 8 channels for 10 seconds (Ctrl+C to stop early)...")
print("Channels that are NOT connected to the sensor will show a random value/noise - that's NORMAL.\n")

try:
    for i in range(10):
        readings = []
        for ch in range(8):
            raw = adc.read_raw(ch)
            volt = adc.read_voltage(ch)
            readings.append(f"CH{ch}={raw:4d}({volt:.2f}V)")
        print(" | ".join(readings))
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    adc.close()

print("\n[END] If the channel with the sensor (CH0-CH7) shows a value")
print("which CHANGES when you cover the sensor with your hand / touch the cable,")
print("means that the wiring of SPI MCP3008 is correct.")
