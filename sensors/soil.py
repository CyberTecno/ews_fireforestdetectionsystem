"""
Capacitive Soil Moisture Probe - analog output, read via ADS1115.
IMPORTANT: run a quick calibration before deployment:
  1. Read raw value with probe fully dry in open air  -> use as dry_raw
  2. Read raw value with probe fully submerged in water -> use as wet_raw
Capacitive probes typically read HIGHER raw values when dry, LOWER when wet.
"""
import time

try:
    import Adafruit_ADS1x15
except ImportError:
    Adafruit_ADS1x15 = None

from config import settings


class SoilMoistureSensor:
    def __init__(self, channel=settings.ADC_CHANNEL_SOIL, address=settings.ADS1115_ADDRESS,
                 dry_raw=26000, wet_raw=12000):
        self.channel = channel
        self.dry_raw = dry_raw
        self.wet_raw = wet_raw
        self.gain = 1
        if Adafruit_ADS1x15:
            self.adc = Adafruit_ADS1x15.ADS1115(address=address, busnum=settings.I2C_BUS)
        else:
            self.adc = None

    def read_raw(self):
        if self.adc is None:
            raise RuntimeError("Adafruit_ADS1x15 not installed - pip install Adafruit-ADS1x15")
        return self.adc.read_adc(self.channel, gain=self.gain)

    def read_moisture_percent(self):
        raw = self.read_raw()
        raw = max(min(raw, self.dry_raw), self.wet_raw)
        percent = (self.dry_raw - raw) / (self.dry_raw - self.wet_raw) * 100
        return round(max(0.0, min(100.0, percent)), 2)

    def read(self):
        raw = self.read_raw()
        return {"raw": raw, "moisture_percent": self.read_moisture_percent()}


if __name__ == "__main__":
    sensor = SoilMoistureSensor()
    while True:
        print(sensor.read())
        time.sleep(2)
