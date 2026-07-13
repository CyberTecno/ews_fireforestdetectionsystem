"""
Submersible Pressure Sensor (water level / reservoir) — output loop 4-20mA.
Dibaca lewat MCP3008 CH4, lewat burden resistor + logic level converter yang sama
dengan sensor analog lainnya (lihat docs/Pinout.md).

WIRING RINGKAS (loop 2-kabel, powered dari PSU eksternal 12-24V):
  PSU+  ──► Sensor V+ (loop+)
  Sensor loop out (4-20mA) ──► turun lewat R_BURDEN (250Ω presisi) ──► GND
  Titik sambung Sensor-out/R_BURDEN ──► LLC HV (5V sisi) ──► LV (3.3V) ──► MCP3008 CH4

Kenapa 250Ω persis?
  I = 4mA  → V = 4mA  × 250Ω = 1.0V  (level "kosong"/0m)
  I = 20mA → V = 20mA × 250Ω = 5.0V  (level penuh / PRESSURE_RANGE_M)
  Ini pas mengisi rentang 0-5V yang sama dengan sensor analog lain di LLC,
  jadi tidak perlu LLC/channel terpisah dari desain yang sudah ada.

Karena LLC scale linear (HV=5V ↔ LV=3.3V), faktor LLC saling meniadakan
(lihat catatan yang sama di config/settings.py untuk battery sensor lama):
  raw/1023 = V_lv/3.3 = (I × R_BURDEN × 3.3/5) / 3.3 = I × R_BURDEN / 5
  → I(mA) = raw/1023 × 5000 / R_BURDEN(ohm)   (dengan R_BURDEN=250 → I = raw/1023 × 20)
"""
from config import settings
from sensors.mcp3008 import get_mcp3008


class PressureWaterSensor:
    def __init__(self, channel=None,
                 burden_ohm=None, min_ma=None, max_ma=None, range_m=None):
        self.channel    = channel    if channel    is not None else settings.ADC_CHANNEL_PRESSURE
        self.burden_ohm = burden_ohm if burden_ohm is not None else settings.PRESSURE_BURDEN_OHM
        self.min_ma     = min_ma     if min_ma     is not None else settings.PRESSURE_MIN_MA
        self.max_ma     = max_ma     if max_ma     is not None else settings.PRESSURE_MAX_MA
        self.range_m    = range_m    if range_m    is not None else settings.PRESSURE_RANGE_M
        self.adc        = get_mcp3008()

    def read_current_ma(self) -> float:
        raw = self.adc.read_raw(self.channel)
        ma  = raw / 1023.0 * (5000.0 / self.burden_ohm)
        return round(ma, 3)

    def read_depth_m(self) -> float:
        ma   = self.read_current_ma()
        span = self.max_ma - self.min_ma
        pct  = (ma - self.min_ma) / span
        pct  = max(0.0, min(1.0, pct))
        return round(pct * self.range_m, 3)

    def read(self) -> dict:
        ma    = self.read_current_ma()
        depth = self.read_depth_m()
        # Cek putus kabel/loop: <3.8mA biasanya berarti sensor/loop terputus
        fault = ma < (self.min_ma - 0.2)
        return {
            "current_ma": ma,
            "depth_m":     depth,
            "pressure_bar": round(depth * 0.0980665, 4),
            "fault_open_loop": fault,
        }


if __name__ == "__main__":
    import time
    sensor = PressureWaterSensor()
    while True:
        print(sensor.read())
        time.sleep(2)
