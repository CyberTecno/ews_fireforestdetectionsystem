"""
Driver MCP3008 (ADC 8-channel, 10-bit, via SPI) — menggantikan ADS1115.

MCP3008 dipakai karena Pi 4 tidak punya pin analog. Semua sensor analog
(MQ-2, MQ-135, soil moisture, dan opsional AO dari flame sensor) terhubung
ke satu chip MCP3008 yang sama, dibaca lewat SPI hardware (SPI0, CE0).

PENTING soal tegangan:
  - MCP3008 VDD/VREF harus 3.3V (BUKAN 5V) karena terhubung langsung ke
    Pi tanpa level shifter di sisi SPI.
  - Tapi MQ-2/MQ-135/soil probe outputnya 0-5V → SETIAP channel analog
    MCP3008 yang menerima sinyal dari sensor 5V WAJIB melewati logic
    level converter (sisi HV=5V ke sensor, sisi LV=3.3V ke MCP3008),
    kalau tidak pembacaan akan clipping/jenuh di ~3.3V dan bisa merusak
    chip dalam jangka panjang.

Pemetaan channel default (lihat docs/Pinout.md untuk detail wiring):
  CH0 → MQ-2 (lewat logic level converter)
  CH1 → MQ-135 (lewat logic level converter)
  CH2 → Soil moisture probe (lewat logic level converter)
  CH3 → Flame sensor AO (opsional, lewat logic level converter)
  CH4-CH7 → cadangan/ekspansi

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
    """Satu instance merepresentasikan satu chip MCP3008 fisik di SPI0/CE0."""

    def __init__(self, bus=None, device=None, max_speed_hz=None, vref=None):
        if spidev is None:
            raise RuntimeError("spidev tidak terinstall - pip install spidev")

        self.bus = bus if bus is not None else settings.SPI_BUS
        self.device = device if device is not None else settings.SPI_DEVICE
        self.vref = vref if vref is not None else settings.MCP3008_VREF

        self.spi = spidev.SpiDev()
        self.spi.open(self.bus, self.device)
        self.spi.max_speed_hz = max_speed_hz or settings.SPI_MAX_SPEED_HZ
        self.spi.mode = 0b00

    def read_raw(self, channel: int) -> int:
        """Baca channel 0-7, return nilai mentah 0-1023 (10-bit)."""
        if not 0 <= channel <= 7:
            raise ValueError("MCP3008 channel harus 0-7")
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
# Semua sensor analog berbagi SATU chip MCP3008 fisik yang sama, jadi
# semua sensor sebaiknya pakai instance SPI yang sama, bukan masing-
# masing buka koneksi SPI sendiri-sendiri.
_instance = None


def get_mcp3008() -> "MCP3008":
    global _instance
    if _instance is None:
        _instance = MCP3008()
    return _instance


if __name__ == "__main__":
    import time
    adc = MCP3008()
    print(f"MCP3008 dibuka di SPI bus={adc.bus} device={adc.device}, VREF={adc.vref}V")
    print("Membaca semua 8 channel tiap 1 detik (Ctrl+C untuk stop)...\n")
    try:
        while True:
            readings = [f"CH{c}={adc.read_voltage(c):.3f}V" for c in range(8)]
            print(" | ".join(readings))
            time.sleep(1)
    except KeyboardInterrupt:
        adc.close()
