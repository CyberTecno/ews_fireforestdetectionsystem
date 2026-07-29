import time
import serial
import minimalmodbus

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"

instrument = minimalmodbus.Instrument(PORT, 1)

instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout = 1

instrument.mode = minimalmodbus.MODE_RTU

while True:

    try:

        raw = instrument.read_register(
            registeraddress=0,
            number_of_decimals=0,
            functioncode=3,
            signed=False,
        )

        wind_speed = raw * 0.1

        print(f"Raw = {raw}")
        print(f"Wind Speed = {wind_speed:.1f} m/s")
        print("-" * 40)

    except Exception as e:

        print(e)

    time.sleep(2)
