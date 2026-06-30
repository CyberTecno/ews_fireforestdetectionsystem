"""
Driver Relay 5V - relay ini menyambungkan sirine 12V/24V/220V 120dB
(dengan LED flasher bawaan) ke sumber daya 12V.
Kebanyakan modul relay murah aktif-LOW di pin IN (LOW = energized/closed).
Set active_low=False jika modul Anda aktif-HIGH.

Kebanyakan modul relay (dengan optocoupler) sudah kompatibel logic 3.3V,
jadi BIASANYA tidak perlu logic level converter untuk jalur kontrolnya -
tapi cek datasheet modul relay Anda untuk pastikan (lihat docs/Pinout.md).
"""
from config import settings

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class Relay:
    def __init__(self, pin=None, active_low=True):
        self.pin = pin if pin is not None else settings.GPIO_RELAY_SIREN
        self.active_low = active_low
        if GPIO is None:
            raise RuntimeError("RPi.GPIO tidak tersedia - jalankan ini di Raspberry Pi")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self.off()

    def on(self):
        GPIO.output(self.pin, GPIO.LOW if self.active_low else GPIO.HIGH)

    def off(self):
        GPIO.output(self.pin, GPIO.HIGH if self.active_low else GPIO.LOW)

    def is_on(self) -> bool:
        state = GPIO.input(self.pin)
        return (state == GPIO.LOW) if self.active_low else (state == GPIO.HIGH)
