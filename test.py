from gpiozero import Buzzer
from time import sleep

BUZZER_PIN = 16

buzzer = Buzzer(BUZZER_PIN)

try:
    while True:
        print("Buzzer ON")
        buzzer.on()
        sleep(1)

        print("Buzzer OFF")
        buzzer.off()
        sleep(1)

except KeyboardInterrupt:
    buzzer.off()
    print("Program dihentikan")