import minimalmodbus
import serial
import time

from config import settings


class AnemometerSensor:
    # Mengubah default paramater ke nilai yang SUDAH TERBUKTI BERHASIL
    # (Port USB0, Slave ID 2, Baudrate 9600).
    # Jika di file config/settings.py Anda parameternya berbeda, kita amankan di sini.
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
        # MENGGUNAKAN PENGATURAN REGISTER YANG BERHASIL: 
        return self.instrument.read_register(
            settings.ANEMOMETER_REGISTER,
            number_of_decimals=settings.ANEMOMETER_DECIMALS,
            functioncode=settings.ANEMOMETER_FUNCTION_CODE
        )

    def read(self):

        last_error = None
        for _ in range(3):
            try:
                speed = self.read_wind_speed()
                return {
                    "speed_ms": speed
                }
            except minimalmodbus.NoResponseError as e:
                last_error = e
                time.sleep(0.2)

        return {
            "speed_ms": None,
            "error": str(last_error)
    }
      
# Blok untuk pengetesan langsung di dalam folder sensors
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
