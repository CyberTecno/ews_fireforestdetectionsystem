"""
MQ-2 Gas/Smoke Sensor driver.
MQ-2 is analog-only, so it is read through an ADS1115 ADC (I2C).
NOTE: The voltage->ppm formula below is a simplified placeholder.
For accurate ppm you must calibrate R0 in clean air per the MQ-2 datasheet
curve (Rs/R0 vs ppm, log-log). Treat the "ppm" field as a relative
indicator until calibrated, and rely on the raw voltage trend as well.
"""
import time

try:
    import Adafruit_ADS1x15
except ImportError:
    Adafruit_ADS1x15 = None

from config import settings


class MQ2Sensor:
    def __init__(self, channel=settings.ADC_CHANNEL_MQ2, address=settings.ADS1115_ADDRESS):
        self.channel = channel
        self.gain = 1  # +/-4.096V range, ~0.125mV/bit
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
        # CALIBRATE: replace with your unit's Rs/R0 curve for real ppm accuracy
        ppm = max(0.0, (voltage - 0.4) * 1000)
        return round(ppm, 2)

    def read(self):
        voltage = self.read_voltage()
        return {"voltage": round(voltage, 3), "ppm": self.read_ppm()}


if __name__ == "__main__":
    sensor = MQ2Sensor()
    while True:
        print(sensor.read())
        time.sleep(2)
