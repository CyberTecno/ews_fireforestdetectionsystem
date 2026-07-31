"""
Submersible Water Level Pressure Sensor (4-20mA)
Sensor loop-powered 2-kabel: 4mA=kosong, 20mA=penuh (PRESSURE_RANGE_M).
Arus diubah tegangan lewat burden resistor, dibaca MCP3008 CH4 (lewat LLC).

Jadi sekarang pakai get_mcp3008() yang
sama seperti mq2.py/mq135.py/battery.py/soil.py.
"""
from config import settings
from sensors.mcp3008 import get_mcp3008


class PressureWaterSensor:

    def __init__(
        self,
        channel=None,
        burden_ohm=None,
        min_ma=None,
        max_ma=None,
        range_m=None,
    ):
        self.channel    = channel    if channel    is not None else settings.ADC_CHANNEL_PRESSURE
        self.burden_ohm = burden_ohm if burden_ohm is not None else settings.PRESSURE_BURDEN_OHM
        self.min_ma     = min_ma     if min_ma     is not None else settings.PRESSURE_MIN_MA
        self.max_ma     = max_ma     if max_ma     is not None else settings.PRESSURE_MAX_MA
        self.range_m    = range_m    if range_m    is not None else settings.PRESSURE_RANGE_M
        self.adc = get_mcp3008()

    # ------------------------------------------------------

    def read(self):
        voltage = self.adc.read_voltage(self.channel)

        current_ma = (voltage / self.burden_ohm) * 1000.0

        fault = current_ma < 3.8

        if fault:
            depth_m = 0.0
        else:
            depth_mm = ((current_ma - self.min_ma) / (self.max_ma - self.min_ma)) * (self.range_m * 1000)
            depth_mm = max(0.0, min(self.range_m * 1000, depth_mm))
            depth_m = depth_mm / 1000.0

        # Konversi hidrostatik standar: 1 meter kolom air ≈ 0.0980665 bar
        # (rho_air=1000 kg/m3, g=9.80665 m/s2) -- rumus fisika baku, bukan
        # kalibrasi khusus hardware ini.
        pressure_bar = depth_m * 0.0980665

        return {
            "voltage":         round(voltage, 4),
            "current_ma":      round(current_ma, 4),
            "depth_m":         round(depth_m, 4),
            "pressure_bar":    round(pressure_bar, 4),
            "fault_open_loop": fault,
        }


if __name__ == "__main__":
    import time
    sensor = PressureWaterSensor()
    while True:
        print(sensor.read())
        time.sleep(2)
