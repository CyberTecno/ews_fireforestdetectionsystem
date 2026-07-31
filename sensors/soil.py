"""
Capacitive Soil Moisture Probe (waterproof) — dua probe: surface dan deep.

  - soilMoistureSurface: probe di kedalaman 0–30 cm
  - soilMoistureDeep:    probe di kedalaman 30–60 cm

Masing-masing probe memiliki nilai kalibrasi dry/wet sendiri.
"""

from config import settings
from sensors.mcp3008 import get_mcp3008


class SoilMoistureSensor:
    def __init__(
        self,
        channel_surface=None,
        channel_deep=None,

        # Kalibrasi Surface
        dry_raw_surface=900,
        wet_raw_surface=380,

        # Kalibrasi Deep
        dry_raw_deep=920,
        wet_raw_deep=410,
    ):

        self.ch_surface = (
            channel_surface
            if channel_surface is not None
            else settings.ADC_CHANNEL_SOIL_SURFACE
        )

        self.ch_deep = (
            channel_deep
            if channel_deep is not None
            else settings.ADC_CHANNEL_SOIL_DEEP
        )

        self.adc = get_mcp3008()

        # Surface calibration
        self.dry_raw_surface = dry_raw_surface
        self.wet_raw_surface = wet_raw_surface

        # Deep calibration
        self.dry_raw_deep = dry_raw_deep
        self.wet_raw_deep = wet_raw_deep

    def _raw_to_pct(self, raw: int, dry_raw: int, wet_raw: int) -> float:
        """
        Mengubah nilai ADC menjadi persentase kelembapan.
        Probe kapasitif:
            raw tinggi = kering
            raw rendah = basah
        """

        raw = max(min(raw, dry_raw), wet_raw)

        pct = (dry_raw - raw) / (dry_raw - wet_raw) * 100.0

        return round(max(0.0, min(100.0, pct)), 2)

    def read_surface(self) -> dict:
        raw = self.adc.read_raw(self.ch_surface)

        return {
            "raw": raw,
            "moisture_percent": self._raw_to_pct(
                raw,
                self.dry_raw_surface,
                self.wet_raw_surface,
            ),
        }

    def read_deep(self) -> dict:
        raw = self.adc.read_raw(self.ch_deep)

        return {
            "raw": raw,
            "moisture_percent": self._raw_to_pct(
                raw,
                self.dry_raw_deep,
                self.wet_raw_deep,
            ),
        }

    def read(self):
        surface = self.read_surface()
        deep = self.read_deep()

        return {
            "surface": surface,
            "deep": deep,
        }


if __name__ == "__main__":
    import time

    sensor = SoilMoistureSensor()

    while True:
        print(sensor.read())
        time.sleep(2)