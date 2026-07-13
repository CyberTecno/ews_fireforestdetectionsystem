"""
BME280 — Temperature / Humidity / Pressure ambient sensor (I2C).
Dipakai untuk deteksi kondisi ambient (suhu tinggi + kelembaban rendah =
risiko kebakaran meningkat). TIDAK lewat MCP3008/LLC — modul ini I2C native.

Requires: pip install smbus2 RPi.bme280
"""
from config import settings

try:
    import smbus2
    import bme280 as _bme280_lib
except ImportError:
    smbus2 = None
    _bme280_lib = None


class BME280Sensor:
    def __init__(self, bus=None, address=None):
        if smbus2 is None or _bme280_lib is None:
            raise RuntimeError("smbus2/RPi.bme280 tidak terinstall - pip install smbus2 RPi.bme280")

        self.bus_num  = bus     if bus     is not None else settings.I2C_BUS
        self.address  = address if address is not None else settings.BME280_ADDRESS
        self.bus       = smbus2.SMBus(self.bus_num)
        self.calib     = _bme280_lib.load_calibration_params(self.bus, self.address)

    def read(self) -> dict:
        try:
            data = _bme280_lib.sample(self.bus, self.address, self.calib)
            return {
                "temperature_c":    round(data.temperature, 2),
                "humidity_percent": round(data.humidity, 2),
                "pressure_hpa":     round(data.pressure, 2),
            }
        except Exception as e:
            return {"temperature_c": None, "humidity_percent": None,
                    "pressure_hpa": None, "error": str(e)}


if __name__ == "__main__":
    import time
    sensor = BME280Sensor()
    while True:
        print(sensor.read())
        time.sleep(2)
