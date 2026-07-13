"""
Modul Sensor Tegangan DC 0-25V — monitoring baterai (voltage divider bawaan modul).
Lewat MCP3008 CH5 via Logic Level Converter yang sama dengan sensor analog lain.

Input : terhubung langsung ke terminal Battery+ dan Battery-
Output: pin S → 0-5V proporsional terhadap tegangan input (0-25V)

Kalkulasi:
  V_battery = (raw / 1023) × BATTERY_SENSOR_MAX_V
  Karena LLC scale linear (HV=5V↔LV=3.3V), faktor LLC saling meniadakan:
  raw/1023 = V_lv/3.3 = (V_s × 3.3/5) / 3.3 = V_s/5 = V_battery/25
  → V_battery = raw × 25 / 1023
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
