"""
MCP3008 driver (8-channel, 10-bit ADC over SPI) — replaces the ADS1115.

MCP3008 is used because the Pi 4 doesn't have an analog pin. All analog sensors
(MQ-2, MQ-135, soil moisture x2, pressure sensor, battery voltage sensor)
connected to the same MCP3008 chip, read via SPI hardware (SPI0, CE0).

IMPORTANT about voltage:
- MCP3008 VDD/VREF must be 3.3V (NOT 5V) because it is connected directly to
Pi without level shifter on side SPI.
- But MQ-2/MQ-135/soil probe/battery sensor output is 0-5V → EACH
analog channel MCP3008 which receives signals from the 5V sensor MANDATORY
passes through the logic level converter (HV side=5V to sensor, LV side=3.3V to
MCP3008), otherwise the reading will clip/jenuh at ~3.3V and can
damage the chip in the long term.

Default channel mapping (see docs/Pinout.md for wiring details):
CH0 → MQ-2 (via LLC)
CH1 → MQ-135 (via LLC)
CH2 → Soil moisture — surface (via LLC)
CH3 → Soil moisture — deep (via LLC)
CH4 → Submersible pressure sensor, via burden resistor (via LLC)
CH5 → Battery voltage sensor module (via LLC)
CH6-CH7 → backup/ekspansi

Requires: pip install spidev
"""
import logging
from config import settings

logger = logging.getLogger("efws.mcp3008")

try:
    import spidev
except ImportError:
    spidev = None


class MCP3008:
    """One instance represents one physical MCP3008 chip in SPI0/CE0."""

    def __init__(self, bus=None, device=None, max_speed_hz=None, vref=None):
        if spidev is None:
            raise RuntimeError("spidev not installed - pip install spidev")

        self.bus = bus if bus is not None else settings.SPI_BUS
        self.device = device if device is not None else settings.SPI_DEVICE
        self.vref = vref if vref is not None else settings.MCP3008_VREF

        self.spi = spidev.SpiDev()
        self.spi.open(self.bus, self.device)
        self.spi.max_speed_hz = max_speed_hz or settings.SPI_MAX_SPEED_HZ
        self.spi.mode = 0b00

    def read_raw(self, channel: int) -> int:
        """Read channels 0-7, return raw value 0-1023 (10-bit)."""
        if not 0 <= channel <= 7:
            raise ValueError("MCP3008 channel should be 0-7")
        cmd = [1, (8 + channel) << 4, 0]
        resp = self.spi.xfer2(cmd)
        value = ((resp[1] & 3) << 8) + resp[2]
        return value

    def read_voltage(self, channel: int) -> float:
        raw = self.read_raw(channel)
        return round(raw / 1023.0 * self.vref, 4)

    def close(self):
        self.spi.close()


# ─── Singleton helper ──────────────────────────────────────────────
# All analog sensors share the same physical SATU chip MCP3008, so
# all sensors should use the same instance of SPI, not each
# each open connection SPI individually.
_instance = None


def get_mcp3008() -> "MCP3008":
    global _instance
    if _instance is None:
        _instance = MCP3008()
    return _instance


if __name__ == "__main__":
    import time
    adc = MCP3008()
    print(f"MCP3008 opens at SPI bus={adc.bus} device={adc.device}, VREF={adc.vref}V")
    print("Reads all 8 channels every 1 second (Ctrl+C to stop)...\n")
    try:
        while True:
            readings = [f"CH{c}={adc.read_voltage(c):.3f}V" for c in range(8)]
            print(" | ".join(readings))
            time.sleep(1)
    except KeyboardInterrupt:
        adc.close()
