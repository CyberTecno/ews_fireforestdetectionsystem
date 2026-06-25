"""
MQ-135 Air Quality Sensor driver (NH3, NOx, alcohol, benzene, CO2, smoke).
Same ADS1115 analog read pattern as MQ-2, different channel & curve.
Calibrate against known clean-air baseline for production accuracy.
"""
import time

try:
    import Adafruit_ADS1x15
except ImportError:
    Adafruit_ADS1x15 = None

from config import settings


class MQ135Sensor:
    def __init__(self, channel=settings.ADC_CHANNEL_MQ135, address=settings.ADS1115_ADDRESS):
        self.channel = channel
        self.gain = 1
        if Adafruit_ADS1x15:
            self.adc = Adafruit_ADS1x15.ADS1115(address=address, busnum=settings.I2C_BUS)
        else:
            self.adc = None

    def read_raw(self):
        if self.adc is None:
            raise RuntimeError("Adafruit_ADS1x15 not installed - pip install Adafruit-ADS1x15")
        return self.adc.read_adc(self.channel, gain=self.gain)

    def read_voltage(self):
        raw = self.read_raw()
        return raw * 0.125 / 1000.0

    def read_ppm(self):
        voltage = self.read_voltage()
        if voltage <= 0:
            return 0.0
        # CALIBRATE: placeholder linear approximation
        ppm = max(0.0, (voltage - 0.3) * 900)
        return round(ppm, 2)

    def read(self):
        voltage = self.read_voltage()
        return {"voltage": round(voltage, 3), "ppm": self.read_ppm()}


if __name__ == "__main__":
    sensor = MQ135Sensor()
    while True:
        print(sensor.read())
        time.sleep(2)
