"""
5V Relay Module driver - this relay switches the 12V siren circuit.
Most cheap relay modules are active-LOW on the IN pin (LOW = energized/closed).
Set active_low=False if yours is active-HIGH.
"""
import RPi.GPIO as GPIO
from config import settings


class Relay:
    def __init__(self, pin=settings.GPIO_RELAY_SIREN, active_low=True):
        self.pin = pin
        self.active_low = active_low
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self.off()

    def on(self):
        GPIO.output(self.pin, GPIO.LOW if self.active_low else GPIO.HIGH)

    def off(self):
        GPIO.output(self.pin, GPIO.HIGH if self.active_low else GPIO.LOW)

    def is_on(self):
        state = GPIO.input(self.pin)
        return (state == GPIO.LOW) if self.active_low else (state == GPIO.HIGH)
