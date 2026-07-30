"""
Submersible Water Level Pressure Sensor (4–20 mA)

Sensor menghasilkan arus 4–20 mA.
Arus diubah menjadi tegangan menggunakan burden resistor,
kemudian dibaca MCP3008.

Pipeline pembacaan:

Sensor
   │
   ▼
read_raw()
   │
   ▼
_raw_to_voltage()
   │
   ▼
_voltage_to_current()
   │
   ▼
_current_to_level()
   │
   ▼
_status_from_current()
   │
   ▼
read()
"""

from config import settings
from sensors.mcp3008 import get_mcp3008


class PressureWaterSensor:

    def __init__(
        self,
        channel=None,
        burden_resistor=None,
        min_current_ma=None,
        max_current_ma=None,
        max_level_mm=None,
    ):

        self.channel = (
            channel
            if channel is not None
            else settings.ADC_CHANNEL_PRESSURE
        )

        self.burden_resistor = (
            burden_resistor
            if burden_resistor is not None
            else settings.PRESSURE_BURDEN_OHM
        )

        self.min_current = (
            min_current_ma
            if min_current_ma is not None
            else settings.PRESSURE_MIN_MA
        )

        self.max_current = (
            max_current_ma
            if max_current_ma is not None
            else settings.PRESSURE_MAX_MA
        )

        self.max_level = (
            max_level_mm
            if max_level_mm is not None
            else settings.PRESSURE_RANGE_M
        )

        self.adc = get_mcp3008()

    # ============================================================
    # Hardware
    # ============================================================

    def read_raw(self) -> int:
        """
        Membaca nilai ADC mentah (0-1023).
        """
        return self.adc.read_raw(self.channel)

    # ============================================================
    # Conversion Helpers (Pure Functions)
    # ============================================================

    def _raw_to_voltage(self, raw: int) -> float:
        """
        ADC Raw -> Volt
        """
        return raw / 1023.0 * settings.MCP3008_VREF

    def _voltage_to_current(self, voltage: float) -> float:
        """
        Volt -> mA
        """
        return (voltage / self.burden_resistor) * 1000

    def _current_to_level(self, current: float) -> float:
        """
        mA -> Water Level (mm)
        """

        if current <= self.min_current:
            return 0.0

        level = (
            (current - self.min_current)
            / (self.max_current - self.min_current)
        ) * self.max_level

        return max(0.0, min(self.max_level, level))

    def _status_from_current(self, current: float) -> str:

        if current < self.min_current - 0.2:
            return "SENSOR_DISCONNECTED"

        if current > self.max_current + 1:
            return "OVER_RANGE"

        return "OK"

    # ============================================================
    # Public API
    # ============================================================

    def read_voltage(self) -> float:

        raw = self.read_raw()

        return round(
            self._raw_to_voltage(raw),
            4,
        )

    def read_current(self) -> float:

        raw = self.read_raw()

        voltage = self._raw_to_voltage(raw)

        return round(
            self._voltage_to_current(voltage),
            2,
        )

    def read_level(self) -> float:

        raw = self.read_raw()

        voltage = self._raw_to_voltage(raw)

        current = self._voltage_to_current(voltage)

        return round(
            self._current_to_level(current),
            1,
        )

    def read(self):

        raw = self.read_raw()

        voltage = self._raw_to_voltage(raw)

        current = self._voltage_to_current(voltage)

        level = self._current_to_level(current)

        status = self._status_from_current(current)

        return {

            "raw": raw,

            "voltage": round(voltage, 4),

            "current_mA": round(current, 2),

            "water_level_mm": round(level, 1),

            "status": status,
        }


if __name__ == "__main__":

    import time

    sensor = PressureWaterSensor()

    while True:

        print(sensor.read())

        time.sleep(1)