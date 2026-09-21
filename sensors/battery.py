"""
DC Voltage Sensor Module (built-in fixed 1:5 voltage divider).
DIRECT to MCP3008 CH5 -- NOT via Logic Level Converter.

WHY NOT VIA LLC (different from MQ2/MQ135/soil/pressure):
According to the official wiring of this module (osoyoo.com/2024/09/08/lesson-13-voltage-
sensor-for-raspberry-pi/), the "+" pin of the module is supplied DIRECTLY from the 3.3V Pi
(not 5V) -- that's why the input safe limit is lowered from 3.3V (3.3 x 5 =
16.5V), not from 5V. The "S" signal is output so ALREADY is in range
0-3.3V, fits directly to MCP3008 (VREF 3.3V) without needing to step down again
via LLC. Skipping it via digital LLC (e.g. TXS0108E) is instead FALSE --
such digital level-shifter chips do not translate analog voltages
linearly, only detecting the HIGH/LOW. threshold

Complete wiring (5 connection points, DUA different sides):
Output side/logic (to Pi) : "+" -> 3.3V, "-" -> GND, "S" -> MCP3008 CH5
Input side (which is measured): anode -> Battery+, cathode -> Battery-

Kalkulasi:
  V_battery = (raw / 1023) x BATTERY_SENSOR_MAX_V
BATTERY_SENSOR_MAX_V = 16.5V (= VREF 3.3V x divider ratio 5), NOT 25V --
The 25V value only applies if the ADC is given VREF 5V, not the project case
This. See config/settings.py for derivation details.
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
