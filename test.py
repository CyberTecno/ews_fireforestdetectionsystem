# from gpiozero import Buzzer
# from time import sleep

# BUZZER_PIN = 16

# buzzer = Buzzer(BUZZER_PIN)

# try:
#     while True:
#         print("Buzzer ON")
#         buzzer.on()
#         sleep(1)

#         print("Buzzer OFF")
#         buzzer.off()
#         sleep(1)

# except KeyboardInterrupt:
#     buzzer.off()
#     print("Program dihentikan")


from gpiozero import DigitalInputDevice
from time import sleep

MQ135_PIN = 17

sensor = DigitalInputDevice(MQ135_PIN)

print("Menunggu sensor pemanasan...")

sleep(30)

try:
    while True:
        if sensor.value == 0:
            print("⚠️ Gas/asap terdeteksi!")
        else:
            print("Udara normal")

        sleep(1)

except KeyboardInterrupt:
    print("Program dihentikan")