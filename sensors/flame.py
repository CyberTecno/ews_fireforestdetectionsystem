"""
IR Flame Sensor (LM393 comparator module).
Most LM393 flame modules are active-LOW (output goes LOW when flame detected).
Verify against your specific module - flip active_low=False if yours is active-HIGH.
"""
import RPi.GPIO as GPIO
from config import settings


class FlameSensor:
    def __init__(self, pin=settings.GPIO_FLAME_SENSOR, active_low=True):
        self.pin = pin
        self.active_low = active_low
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP if active_low else GPIO.PUD_DOWN)

    def read(self):
        raw = GPIO.input(self.pin)
        detected = (raw == GPIO.LOW) if self.active_low else (raw == GPIO.HIGH)
        return {"raw": raw, "flame_detected": bool(detected)}


if __name__ == "__main__":
    import time
    sensor = FlameSensor()
    while True:
        print(sensor.read())
        time.sleep(1)
