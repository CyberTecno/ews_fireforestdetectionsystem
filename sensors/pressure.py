"""
Submersible Pressure Sensor
Output : 4-20mA

Configuration:
- MCP3008
- Raspberry Pi
- WITHOUT Logic Level Converter
- Burden resistor = 56.9 Ohm
- ADC Reference = 3.3V

Voltage produced:

4mA
0.228V

20mA
1.138V

Safe for MCP3008.
"""

from config import settings
from sensors.mcp3008 import get_mcp3008


class PressureWaterSensor:

    def __init__(
        self,
        channel=None,
        burden_ohm=None,
        adc_ref_voltage=None,
        min_ma=None,
        max_ma=None,
        range_m=None,
    ):

        self.channel = (
            channel
            if channel is not None
            else settings.ADC_CHANNEL_PRESSURE
        )

        self.burden_ohm = (
            burden_ohm
            if burden_ohm is not None
            else settings.PRESSURE_BURDEN_OHM
        )

        self.adc_ref = (
            adc_ref_voltage
            if adc_ref_voltage is not None
            else settings.PRESSURE_ADC_REF_VOLTAGE
        )

        self.min_ma = (
            min_ma
            if min_ma is not None
            else settings.PRESSURE_MIN_MA
        )

        self.max_ma = (
            max_ma
            if max_ma is not None
            else settings.PRESSURE_MAX_MA
        )

        self.range_m = (
            range_m
            if range_m is not None
            else settings.PRESSURE_RANGE_M
        )

        self.adc = get_mcp3008()

    # ------------------------------------------------------

    def read_raw(self):

        return self.adc.read_raw(self.channel)

    # ------------------------------------------------------

    def read_voltage(self):

        raw = self.read_raw()

        voltage = raw / 1023.0 * self.adc_ref

        return round(voltage, 4)

    # ------------------------------------------------------

    def read_current_ma(self):

        voltage = self.read_voltage()

        current_ma = voltage / self.burden_ohm * 1000.0

        return round(current_ma, 3)

    # ------------------------------------------------------

    def read_depth_m(self):

        current = self.read_current_ma()

        percent = (
            current - self.min_ma
        ) / (
            self.max_ma - self.min_ma
        )

        percent = max(
            0.0,
            min(1.0, percent)
        )

        return round(
            percent * self.range_m,
            3
        )

    # ------------------------------------------------------

    def read_pressure_bar(self):

        depth = self.read_depth_m()

        pressure = depth * 0.0980665

        return round(
            pressure,
            4
        )

    # ------------------------------------------------------

    def read(self):

        raw = self.read_raw()

        voltage = self.read_voltage()

        current = self.read_current_ma()

        depth = self.read_depth_m()

        pressure = self.read_pressure_bar()

        fault = current < 3.8

        return {

            "adc_raw": raw,

            "voltage": voltage,

            "current_ma": current,

            "depth_m": depth,

            "pressure_bar": pressure,

            "fault_open_loop": fault

        }


if __name__ == "__main__":

    import time

    sensor = PressureWaterSensor()

    while True:

        print(sensor.read())

        time.sleep(2)