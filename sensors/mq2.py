"""
MQ-2 Gas/Smoke Sensor driver.
MQ-2 analog-only -> read via MCP3008 (SPI ADC), default channel CH0.
The signal AOUT MQ-2 (0-5V) MUST passes through the logic level converter before entering
to MCP3008 (see docs/Pinout.md).

NOTE: The voltage->ppm formula below is a simple linear approximation.
For accurate ppm, calibrate R0 in clean air according to the datasheet Rs/R0 curve
MQ-2 (log-log). Consider "ppm" as a relative indicator before calibrating.
"""
import time
from config import settings
from sensors.mcp3008 import get_mcp3008


class MQ2Sensor:
    def __init__(self, channel=None):
        self.channel = channel if channel is not None else settings.ADC_CHANNEL_MQ2
        self.adc = get_mcp3008()

    def read_voltage(self) -> float:
        return self.adc.read_voltage(self.channel)

    def read_ppm(self) -> float:
        voltage = self.read_voltage()
        if voltage <= 0:
            return 0.0
        # CALIBRATE: replace with your sensor's Rs/R0 curve for real accuracy
        ppm = max(0.0, (voltage - 0.4) * 1000)
        return round(ppm, 2)

    def read(self) -> dict:
        voltage = self.read_voltage()
        return {"voltage": round(voltage, 3), "ppm": self.read_ppm()}


if __name__ == "__main__":
    sensor = MQ2Sensor()
    while True:
        print(sensor.read())
        time.sleep(2)
