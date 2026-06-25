"""
RS485 Anemometer (Modbus RTU) wind speed sensor.
Connected via a USB-RS485 adapter (RPi4 has no native RS485 port).
Register address / scaling factor MUST be confirmed against your specific
anemometer's Modbus register map - this varies between manufacturers.
Requires: pip install minimalmodbus
"""
import minimalmodbus
import serial
from config import settings


class AnemometerSensor:
    def __init__(self, port=settings.ANEMOMETER_PORT, slave_id=settings.ANEMOMETER_SLAVE_ID,
                 baudrate=settings.ANEMOMETER_BAUDRATE):
        self.instrument = minimalmodbus.Instrument(port, slave_id)
        self.instrument.serial.baudrate = baudrate
        self.instrument.serial.bytesize = 8
        self.instrument.serial.parity = serial.PARITY_NONE
        self.instrument.serial.stopbits = 1
        self.instrument.serial.timeout = 1
        self.instrument.mode = minimalmodbus.MODE_RTU

    def read_wind_speed(self):
        # functioncode=4 (read input register) is common for these sensors; some use 3 (holding register)
        return self.instrument.read_register(settings.ANEMOMETER_REGISTER,
                                              number_of_decimals=1, functioncode=4)

    def read(self):
        try:
            return {"speed_ms": self.read_wind_speed()}
        except Exception as e:
            return {"speed_ms": None, "error": str(e)}


if __name__ == "__main__":
    import time
    sensor = AnemometerSensor()
    while True:
        print(sensor.read())
        time.sleep(2)
