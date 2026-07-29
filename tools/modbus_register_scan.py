import serial
import minimalmodbus
import time

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
SLAVE = 1

instrument = minimalmodbus.Instrument(PORT, SLAVE)
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout = 0.3
instrument.mode = minimalmodbus.MODE_RTU

print("Scanning register 0-100...\n")

while True:

    print("=" * 60)

    for reg in range(0, 101):

        try:
            value = instrument.read_register(
                reg,
                number_of_decimals=0,
                functioncode=3,
                signed=False
            )

            print(f"Reg {reg:03d} : {value}")

        except:
            pass

    print("\nPutar baling-baling selama scan...\n")

    time.sleep(2)
