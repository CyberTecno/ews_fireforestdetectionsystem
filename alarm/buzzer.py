"""
Active buzzer driver - direct GPIO control for short audible warnings
(separate from the 12V siren, used for the lower "warning" tier).
"""
import time
import RPi.GPIO as GPIO
from config import settings


class Buzzer:
    def __init__(self, pin=settings.GPIO_BUZZER):
        self.pin = pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, GPIO.LOW)

    def on(self):
        GPIO.output(self.pin, GPIO.HIGH)

    def off(self):
        GPIO.output(self.pin, GPIO.LOW)

    def beep(self, duration=0.2, pause=0.2, times=1):
        for _ in range(times):
            self.on()
            time.sleep(duration)
            self.off()
            time.sleep(pause)
