"""
MQ-2 Gas/Smoke Sensor driver.
MQ-2 analog-only -> dibaca lewat MCP3008 (SPI ADC), channel default CH0.
Sinyal AOUT MQ-2 (0-5V) WAJIB lewat logic level converter sebelum masuk
ke MCP3008 (lihat docs/Pinout.md).

NOTE: formula voltase->ppm di bawah adalah pendekatan linear sederhana.
Untuk ppm akurat, kalibrasi R0 di udara bersih sesuai kurva Rs/R0 datasheet
MQ-2 (log-log). Anggap "ppm" sebagai indikator relatif sebelum dikalibrasi.
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
        # CALIBRATE: ganti dengan kurva Rs/R0 sensor Anda untuk akurasi nyata
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
