import minimalmodbus
import serial
import time

from config import settings


class AnemometerSensor:
    # Changing the default parameters to the values ​​HAS BEEN PROVEN WORKING
    # (Port USB0, Slave ID 2, Baudrate 9600).
    # If in your config/settings.py file the parameters are different, we secure them here.
    def __init__(self):
        # Inisialisasi Modbus
        self.instrument = minimalmodbus.Instrument(
            settings.ANEMOMETER_PORT,
            settings.ANEMOMETER_SLAVE_ID
        )

        self.instrument.serial.baudrate = settings.ANEMOMETER_BAUDRATE
        self.instrument.serial.bytesize = settings.ANEMOMETER_BYTESIZE
        self.instrument.serial.parity = serial.PARITY_NONE
        self.instrument.serial.stopbits = settings.ANEMOMETER_STOPBITS
        self.instrument.serial.timeout = settings.ANEMOMETER_TIMEOUT

        self.instrument.mode = minimalmodbus.MODE_RTU

    def read_wind_speed(self):
        # USING SUCCESSFUL REGISTER SETTINGS:
        return self.instrument.read_register(
            settings.ANEMOMETER_REGISTER,
            number_of_decimals=settings.ANEMOMETER_DECIMALS,
            functioncode=settings.ANEMOMETER_FUNCTION_CODE
        )

    def read(self):

        try:
            # Retrieves data from sensors
            speed = self.read_wind_speed()
            return {
                "speed_ms": speed
            }

        except minimalmodbus.NoResponseError:
            # Special handling if the sensor dies / cable is disconnected
            return {
                "speed_ms": None,
                "error": "No response from sensor"
            }

        except Exception as e:
            print("Wind Error :",repr(e))
            return {
                "speed_ms":None,
                "error":str(e)
            }

# Blocks for testing directly in the sensors folder
if __name__ == "__main__":
    sensor = AnemometerSensor()

    print("=== EFWS Wind Speed Test ===")
    print()

    try:

        while True:

            data = sensor.read()

            if data["speed_ms"] is not None:

                print(
                    f"Wind Speed : {data['speed_ms']:.1f} m/s"
                )

            else:

                print(
                    f"Error : {data['error']}"
                )

            time.sleep(1)

    except KeyboardInterrupt:

        print("\nStopped.")