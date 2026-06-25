"""
BME280 Temperature / Humidity / Pressure sensor via I2C.
Requires: pip install smbus2 RPi.bme280
"""
import smbus2
import bme280
from config import settings


class BME280Sensor:
    def __init__(self, address=settings.BME280_ADDRESS, bus_num=settings.I2C_BUS):
        self.bus = smbus2.SMBus(bus_num)
        self.address = address
        self.calibration_params = bme280.load_calibration_params(self.bus, self.address)

    def read(self):
        data = bme280.sample(self.bus, self.address, self.calibration_params)
        return {
            "temperature_c": round(data.temperature, 2),
            "humidity_percent": round(data.humidity, 2),
            "pressure_hpa": round(data.pressure, 2),
        }


if __name__ == "__main__":
    import time
    sensor = BME280Sensor()
    while True:
        print(sensor.read())
        time.sleep(2)
