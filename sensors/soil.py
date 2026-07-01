"""
Capacitive Soil Moisture Probe (waterproof) - analog only, dibaca lewat
MCP3008 (SPI ADC), channel default CH2. Sinyal AOUT probe (0-5V) WAJIB
lewat logic level converter sebelum masuk ke MCP3008.

PENTING - kalibrasi sebelum dipasang permanen:
  1. Baca raw value dengan probe benar-benar kering di udara terbuka -> dry_raw
  2. Baca raw value dengan probe benar-benar terendam air -> wet_raw
Probe kapasitif biasanya: raw TINGGI saat kering, raw RENDAH saat basah.
Nilai default di bawah ini adalah perkiraan untuk MCP3008 10-bit (0-1023)
pada VREF 3.3V - WAJIB dikalibrasi ulang untuk probe fisik Anda.
"""
import time
from config import settings
from sensors.mcp3008 import get_mcp3008


class SoilMoistureSensor:
    def __init__(self, channel=None, dry_raw=770, wet_raw=440):
        self.channel = channel if channel is not None else settings.ADC_CHANNEL_SOIL
        self.adc = get_mcp3008()
        self.dry_raw = dry_raw
        self.wet_raw = wet_raw

    def read_raw(self) -> int:
        return self.adc.read_raw(self.channel)

    def read_moisture_percent(self, raw: int = None) -> float:
        raw = self.read_raw() if raw is None else raw
        raw = max(min(raw, self.dry_raw), self.wet_raw)
        percent = (self.dry_raw - raw) / (self.dry_raw - self.wet_raw) * 100
        return round(max(0.0, min(100.0, percent)), 2)

    def read(self) -> dict:
        raw = self.read_raw()
        return {"raw": raw, "moisture_percent": self.read_moisture_percent(raw)}


if __name__ == "__main__":
    sensor = SoilMoistureSensor()
    while True:
        print(sensor.read())
        time.sleep(2)
