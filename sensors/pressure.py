"""
Submersible Water Level Sensor
Output : 4-20mA

Uses:
- gpiozero MCP3008 (same logic as the validated test)
- Configuration from settings.py
"""

from gpiozero import MCP3008

from config import settings


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

        self.adc = MCP3008(channel=self.channel)

    # ------------------------------------------------------

    def read(self):

        adc_value = self.adc.value

        voltage = adc_value * self.adc_ref

        current_ma = (
            voltage /
            self.burden_ohm
        ) * 1000.0

        fault = current_ma < 3.8

        if fault:
            depth_m = 0.0
        else:

            depth_mm = (
                (
                    current_ma - self.min_ma
                )
                /
                (
                    self.max_ma - self.min_ma
                )
            ) * (
                self.range_m * 1000
            )

            depth_mm = max(
                0.0,
                min(
                    self.range_m * 1000,
                    depth_mm
                )
            )

            depth_m = depth_mm / 1000.0

        pressure_bar = depth_m * 0.0980665

        return {

            "voltage": round(voltage, 4),

            "current_ma": round(current_ma, 4),

            "depth_m": round(depth_m, 4),

            "pressure_bar": round(pressure_bar, 4),

            "fault_open_loop": fault,

        }


if __name__ == "__main__":

    import time

    sensor = PressureWaterSensor()

    while True:

        print(sensor.read())

        time.sleep(2)