"""
MQ-135 Air Quality Sensor driver (NH3, NOx, alkohol, benzena, CO2, asap).
Analog-only -> dibaca lewat MCP3008 (SPI ADC), channel default CH1.
Sinyal AOUT MQ-135 (0-5V) WAJIB lewat logic level converter sebelum masuk
ke MCP3008 (lihat docs/Pinout.md).

Kalibrasi terhadap baseline udara bersih diperlukan untuk akurasi produksi.
"""
import time
from config import settings
from sensors.mcp3008 import get_mcp3008


class MQ135Sensor:
    def __init__(self, channel=None):
        self.channel = channel if channel is not None else settings.ADC_CHANNEL_MQ135
        self.adc = get_mcp3008()

    def read_voltage(self) -> float:
        return self.adc.read_voltage(self.channel)

    def read_ppm(self) -> float:
        voltage = self.read_voltage()
        if voltage <= 0:
            return 0.0
        # CALIBRATE: pendekatan linear placeholder
        ppm = max(0.0, (voltage - 0.3) * 900)
        return round(ppm, 2)

    def read(self) -> dict:
        voltage = self.read_voltage()
        return {"voltage": round(voltage, 3), "ppm": self.read_ppm()}


if __name__ == "__main__":
    sensor = MQ135Sensor()
    while True:
        print(sensor.read())
        time.sleep(2)
