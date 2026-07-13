"""
Capacitive Soil Moisture Probe (waterproof) — dua probe: surface dan deep.

  - soilMoistureSurface: probe di kedalaman 0-30cm (kondisi permukaan tanah)
  - soilMoistureDeep:    probe di kedalaman 30-60cm (kelembaban dalam tanah)

Keduanya dibaca lewat MCP3008 di channel yang berbeda.
Sinyal AOUT probe (0-5V) WAJIB lewat logic level converter sebelum ke MCP3008.

KALIBRASI (wajib sebelum pasang permanen, lakukan per probe):
  1. Probe di udara kering beberapa detik → catat raw → dry_raw
  2. Probe terendam air → catat raw → wet_raw
  Probe kapasitif: raw TINGGI saat kering, RENDAH saat basah.
  Nilai default adalah perkiraan untuk MCP3008 10-bit, VREF 3.3V.
"""
from config import settings
from sensors.mcp3008 import get_mcp3008


class SoilMoistureSensor:
    def __init__(self,
                 channel_surface=None, channel_deep=None,
                 dry_raw=900, wet_raw=380):
        self.ch_surface = channel_surface if channel_surface is not None else settings.ADC_CHANNEL_SOIL_SURFACE
        self.ch_deep    = channel_deep    if channel_deep    is not None else settings.ADC_CHANNEL_SOIL_DEEP
        self.adc        = get_mcp3008()
        self.dry_raw    = dry_raw
        self.wet_raw    = wet_raw

    def _raw_to_pct(self, raw: int) -> float:
        raw = max(min(raw, self.dry_raw), self.wet_raw)
        pct = (self.dry_raw - raw) / (self.dry_raw - self.wet_raw) * 100.0
        return round(max(0.0, min(100.0, pct)), 2)

    def read_surface(self) -> dict:
        raw = self.adc.read_raw(self.ch_surface)
        return {"raw": raw, "moisture_percent": self._raw_to_pct(raw)}

    def read_deep(self) -> dict:
        raw = self.adc.read_raw(self.ch_deep)
        return {"raw": raw, "moisture_percent": self._raw_to_pct(raw)}

    def read(self) -> dict:
        surface = self.read_surface()
        deep    = self.read_deep()
        return {
            "surface": surface,
            "deep":    deep,
        }


if __name__ == "__main__":
    import time
    sensor = SoilMoistureSensor()
    while True:
        print(sensor.read())
        time.sleep(2)
