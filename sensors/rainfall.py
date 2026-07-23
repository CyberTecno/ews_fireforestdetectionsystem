"""
Gravity Rainfall Sensor (DFRobot SEN0575)
Interface : I2C

Output:
- rainfall_total_mm
- rainfall_1h_mm
- rainfall_delta_mm
- rain_rate_mmh
- raw_tip_count
- working_time_hours
- is_raining

Author:
Adapted for EFWS Raspberry Pi
"""

import time

from config import settings

try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None


class RainfallSensor:

    REG_PID = 0x00
    REG_VERSION = 0x0A

    REG_TIME_RAIN = 0x0C
    REG_TOTAL_RAIN = 0x10
    REG_RAW = 0x14
    REG_RUNTIME = 0x18

    REG_SET_HOUR = 0x26

    def __init__(self, bus=None, address=None):

        if SMBus is None:
            raise RuntimeError(
                "Install dulu:\n"
                "pip install smbus2"
            )

        self.bus_num = bus if bus is not None else settings.I2C_BUS
        self.address = (
            address
            if address is not None
            else settings.RAINFALL_I2C_ADDRESS
        )

        self.bus = SMBus(self.bus_num)

        self._last_total = None
        self._last_time = None

    ########################################################

    def _read_u16(self, reg):

        data = self.bus.read_i2c_block_data(
            self.address,
            reg,
            2
        )

        return data[0] | (data[1] << 8)

    ########################################################

    def _read_u32(self, reg):

        data = self.bus.read_i2c_block_data(
            self.address,
            reg,
            4
        )

        return (
            data[0]
            | (data[1] << 8)
            | (data[2] << 16)
            | (data[3] << 24)
        )

    ########################################################

    def get_runtime_hours(self):

        minute = self._read_u16(self.REG_RUNTIME)

        return round(minute / 60.0, 2)

    ########################################################

    def get_total_rainfall(self):

        raw = self._read_u32(self.REG_TOTAL_RAIN)

        return round(raw / 10000.0, 4)

    ########################################################

    def get_raw_tip_count(self):

        return self._read_u32(self.REG_RAW)

    ########################################################

    def get_rainfall_last_hours(self, hour=1):

        if hour < 1:
            hour = 1

        if hour > 24:
            hour = 24

        self.bus.write_i2c_block_data(
            self.address,
            self.REG_SET_HOUR,
            [hour]
        )

        time.sleep(0.05)

        raw = self._read_u32(self.REG_TIME_RAIN)

        return round(raw / 10000.0, 4)

    ########################################################

    def read(self):

        now = time.time()

        total = self.get_total_rainfall()

        raw_tip = self.get_raw_tip_count()

        runtime = self.get_runtime_hours()

        rain_1h = self.get_rainfall_last_hours(1)

        if self._last_total is None:

            delta = 0

            rate = 0

        else:

            if total >= self._last_total:

                delta = total - self._last_total

            else:
                # sensor restart
                delta = total

            elapsed = now - self._last_time

            if elapsed > 0:

                rate = delta * 3600 / elapsed

            else:

                rate = 0

        self._last_total = total
        self._last_time = now

        return {

            "rainfall_total_mm": round(total, 4),

            "rainfall_1h_mm": round(rain_1h, 4),

            "rainfall_delta_mm": round(delta, 4),

            "rain_rate_mmh": round(rate, 2),

            "raw_tip_count": raw_tip,

            "working_time_hours": runtime,

            "is_raining": delta > 0

        }


if __name__ == "__main__":

    sensor = RainfallSensor()

    while True:

        print(sensor.read())

        time.sleep(2)