"""
IR Flame Sensor 4-wire (VCC, GND, DO, AO).
  - DO (digital out): aktif-LOW pada kebanyakan modul ini (LOW = api terdeteksi).
    Sinyal DO 5V WAJIB lewat logic level converter sebelum masuk GPIO Pi (3.3V).
  - AO (analog out, opsional): bisa dibaca lewat MCP3008 channel terpisah
    untuk mengetahui INTENSITAS api, bukan cuma deteksi ya/tidak.
    Sinyal AO 5V juga WAJIB lewat logic level converter sebelum ke MCP3008.

Set read_analog=False jika AO tidak Anda kabel (cukup pakai DO saja).
"""
from config import settings

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class FlameSensor:
    def __init__(self, pin=None, active_low=True, read_analog=False, analog_channel=None):
        self.pin = pin if pin is not None else settings.GPIO_FLAME_SENSOR
        self.active_low = active_low
        self.read_analog = read_analog

        if GPIO is None:
            raise RuntimeError("RPi.GPIO tidak tersedia - jalankan ini di Raspberry Pi")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP if active_low else GPIO.PUD_DOWN)

        self.adc = None
        if self.read_analog:
            from sensors.mcp3008 import get_mcp3008
            self.adc = get_mcp3008()
            self.analog_channel = analog_channel if analog_channel is not None else settings.ADC_CHANNEL_FLAME_AO

    def read(self) -> dict:
        raw = GPIO.input(self.pin)
        detected = (raw == GPIO.LOW) if self.active_low else (raw == GPIO.HIGH)
        result = {"raw": raw, "flame_detected": bool(detected)}
        if self.read_analog and self.adc:
            result["analog_voltage"] = self.adc.read_voltage(self.analog_channel)
        return result


if __name__ == "__main__":
    import time
    sensor = FlameSensor(read_analog=True)
    while True:
        print(sensor.read())
        time.sleep(1)
