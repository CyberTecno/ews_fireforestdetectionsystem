"""
Modul Sensor Tegangan DC (voltage divider bawaan modul, rasio 1:5 TETAP).
LANGSUNG ke MCP3008 CH5 -- TIDAK lewat Logic Level Converter.

KENAPA TIDAK LEWAT LLC (beda dari MQ2/MQ135/soil/pressure):
Sesuai wiring resmi modul ini (osoyoo.com/2024/09/08/lesson-13-voltage-
sensor-for-raspberry-pi/), pin "+" modul disuplai LANGSUNG dari 3.3V Pi
(bukan 5V) -- makanya batas aman inputnya diturunkan dari 3.3V (3.3 x 5 =
16.5V), bukan dari 5V. Sinyal "S" keluarannya jadi SUDAH berada di rentang
0-3.3V, cocok langsung ke MCP3008 (VREF 3.3V) tanpa perlu diturunkan lagi
lewat LLC. Melewatkannya lewat LLC digital (mis. TXS0108E) justru SALAH --
chip level-shifter digital seperti itu tidak menerjemahkan tegangan analog
secara linear, cuma mendeteksi ambang HIGH/LOW.

Wiring lengkap (5 titik sambung, DUA sisi berbeda):
  Sisi output/logic (ke Pi) : "+" -> 3.3V, "-" -> GND, "S" -> MCP3008 CH5
  Sisi input (yang diukur)  : anode -> Battery+, cathode -> Battery-

Kalkulasi:
  V_battery = (raw / 1023) x BATTERY_SENSOR_MAX_V
  BATTERY_SENSOR_MAX_V = 16.5V (= VREF 3.3V x rasio divider 5), BUKAN 25V --
  nilai 25V cuma berlaku kalau ADC-nya diberi VREF 5V, bukan kasus project
  ini. Lihat config/settings.py untuk detail derivasinya.
"""
from config import settings
from sensors.mcp3008 import get_mcp3008


class BatterySensor:
    def __init__(self, channel=None, sensor_max_v=None, batt_max_v=None, batt_min_v=None):
        self.channel      = channel      if channel      is not None else settings.ADC_CHANNEL_BATTERY
        self.sensor_max_v = sensor_max_v if sensor_max_v is not None else settings.BATTERY_SENSOR_MAX_V
        self.batt_max_v   = batt_max_v   if batt_max_v   is not None else settings.BATTERY_MAX_V
        self.batt_min_v   = batt_min_v   if batt_min_v   is not None else settings.BATTERY_MIN_V
        self.adc          = get_mcp3008()

    def read_voltage(self) -> float:
        raw = self.adc.read_raw(self.channel)
        return round(raw / 1023.0 * self.sensor_max_v, 3)

    def read_percent(self) -> float:
        v    = self.read_voltage()
        span = self.batt_max_v - self.batt_min_v
        pct  = (v - self.batt_min_v) / span * 100
        return round(max(0.0, min(100.0, pct)), 1)

    def read(self) -> dict:
        v = self.read_voltage()
        return {"voltage": v, "percent": self.read_percent()}


if __name__ == "__main__":
    import time
    sensor = BatterySensor()
    while True:
        print(sensor.read())
        time.sleep(2)
