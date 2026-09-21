"""
BME280 — Temperature / Humidity / Pressure ambient sensor (I2C).
Used for detection of ambient conditions (high temperature + low humidity =
increased risk of fire). NOT via MCP3008/LLC — this module is native I2C.

Requires: pip install smbus2 RPi.bme280
"""
import time
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
            raise RuntimeError("smbus2/RPi.bme280 not installed - pip install smbus2 RPi.bme280")

        self.bus_num  = bus     if bus     is not None else settings.I2C_BUS
        self.address  = address if address is not None else settings.BME280_ADDRESS
        self.bus       = smbus2.SMBus(self.bus_num)
        
        # ─── MODIFICATION 1: MANUALLY WAKE UP THE SENSOR (ANTI SLEEP/ERRNO 5) ───
        self._initialize_sensor_hardware()
        
        # Take calibration data after the sensor is confirmed to be awake and stable
        try:
            self.calib = _bme280_lib.load_calibration_params(self.bus, self.address)
        except OSError as e:
            # If there is still an error, we will allow a pause and try again
            time.sleep(0.2)
            self.calib = _bme280_lib.load_calibration_params(self.bus, self.address)

    def _initialize_sensor_hardware(self):
        """
Forces the sensor to enter Normal Mode by reading/writing one byte at a time.
It is crucial to overcome the 1.5m long cable and voltage drop.
        """
        try:
            # Provoke connection by reading Chip ID (Single Byte)
            chip_id = self.bus.read_byte_data(self.address, 0xD0)
            
            if chip_id == 0x60:
                # Register the configuration to the control registers (0xF2 and 0xF4) in stages
                # Atur Humidity Oversampling 1x (Reg 0xF2)
                self.bus.write_byte_data(self.address, 0xF2, 0x01)
                time.sleep(0.05)
                
                # Force enter Normal Mode (Reg 0xF4) -> Temp x1, Press x1, Normal Mode
                self.bus.write_byte_data(self.address, 0xF4, 0x27)
                time.sleep(0.1) # Give the sensor's internal circuitry time to charge
        except Exception:
            # Let it escape if it fails, so as not to immediately crash the main application
            pass

    def read(self) -> dict:
        try:
            data = _bme280_lib.sample(self.bus, self.address, self.calib)
            
            # Validate whether the data obtained is constant 0x800000 (invalid / asleep)
            # In the RPi.bme280 library, if it fails, the temperature value is usually an extreme value or None
            if data.temperature == 0.0 and data.humidity == 0.0:
                 raise ValueError("Sensor data is empty/invalid")

            return {
                "temperature_c":    round(data.temperature, 2),
                "humidity_percent": round(data.humidity, 2),
                "pressure_hpa":     round(data.pressure, 2),
            }
        except Exception as e:
            # If an error occurs during operation, try waking up the hardware again
            self._initialize_sensor_hardware()
            return {"temperature_c": None, "humidity_percent": None,
                    "pressure_hpa": None, "error": str(e)}

    def close(self):
        self.bus.close()


if __name__ == "__main__":
    sensor = BME280Sensor()
    try:
        while True:
            print(sensor.read())
            time.sleep(2)
    except KeyboardInterrupt:
        sensor.close()
        print("\nTest stopped.")
