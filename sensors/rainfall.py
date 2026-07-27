"""
DFRobot Gravity Rainfall Sensor (SEN0575)
Native Raspberry Pi Driver

Requires:
    pip install smbus2
"""

import time

from config import settings

try:
    import smbus2
except ImportError:
    smbus2 = None


class RainfallSensor:

    DEFAULT_ADDRESS = 0x1D

    REG_PID = 0x00
    REG_VERSION = 0x0A
    REG_TIME_RAINFALL = 0x0C
    REG_CUMULATIVE_RAINFALL = 0x10
    REG_RAW_DATA = 0x14
    REG_SYS_TIME = 0x18
    REG_RAIN_HOUR = 0x26
    REG_BASE_RAINFALL = 0x28

    EXPECTED_PID = 0x100C0
    EXPECTED_VID = 0x3343

    def __init__(self, bus=None, address=None):

        if smbus2 is None:
            raise RuntimeError(
                "Please install smbus2\n"
                "pip install smbus2"
            )

        self.bus_num = bus if bus is not None else settings.I2C_BUS
        self.address = address if address is not None else self.DEFAULT_ADDRESS

        self.bus = smbus2.SMBus(self.bus_num)

    ############################################################
    # LOW LEVEL
    ############################################################

    def _read(self, register, length):

        for attempt in range(3):

            try:
                write = smbus2.i2c_msg.write(
                    self.address,
                    [register]
                )

                read = smbus2.i2c_msg.read(
                    self.address,
                    length
                )

                self.bus.i2c_rdwr(write)
                self.bus.i2c_rdwr(read)

                return list(read)

            except OSError:

                time.sleep(0.05)

        raise

    def _write(self, register, data):
        if isinstance(data, int):
            data = [data]

        for attempt in range(3):
            try:
                msg = smbus2.i2c_msg.write(
                    self.address,
                    [register] + list(data)
                )

                self.bus.i2c_rdwr(msg)
                time.sleep(0.10)
                return

            except OSError:
                time.sleep(0.05)

        raise

    ############################################################
    # DEVICE
    ############################################################

    def begin(self):

        data = self._read(self.REG_PID, 4)

        pid = (
            data[0]
            | (data[1] << 8)
            | ((data[3] & 0xC0) << 10)
        )

        vid = (
            data[2]
            | ((data[3] & 0x3F) << 8)
        )

        return (
            pid == self.EXPECTED_PID
            and
            vid == self.EXPECTED_VID
        )

    def firmware_version(self):

        data = self._read(
            self.REG_VERSION,
            2
        )

        version = data[0] | (data[1] << 8)

        return "{}.{}.{}.{}".format(
            version >> 12,
            (version >> 8) & 0x0F,
            (version >> 4) & 0x0F,
            version & 0x0F
        )

    ############################################################
    # DATA
    ############################################################

    def rainfall_total(self):

        data = self._read(
            self.REG_CUMULATIVE_RAINFALL,
            4
        )

        return int.from_bytes(
            data,
            "little"
        ) / 10000.0

    def set_rainfall_window(self, hours=1):
        """
        Configure rainfall accumulation window.

        Call ONCE after begin().
        """

        if not (1 <= hours <= 24):
            raise ValueError("hours must be between 1 and 24")

        self._write(
            self.REG_RAIN_HOUR,
            [hours]
        )

        # sama seperti library Arduino
        time.sleep(0.10)

    def window_rainfall(self):
        """
        Read rainfall for previously configured window.

        Does NOT write register 0x26.
        """

        data = self._read(
            self.REG_TIME_RAINFALL,
            4
        )

        return round(
            int.from_bytes(
                data,
                "little"
            ) / 10000,
            4
        )

    def raw_tip_count(self):

        data = self._read(
            self.REG_RAW_DATA,
            4
        )

        return int.from_bytes(
            data,
            "little"
        )

    def working_time_hours(self):

        data = self._read(
            self.REG_SYS_TIME,
            2
        )

        minutes = int.from_bytes(
            data,
            "little"
        )

        return minutes / 60.0

    ############################################################
    # CONFIGURATION
    ############################################################

    def set_accumulated_value(self, value):

        raw = int(value * 10000)

        self._write(
            self.REG_BASE_RAINFALL,
            [
                raw & 0xFF,
                (raw >> 8) & 0xFF
            ]
        )

    ############################################################

    def read(self):

        return {

            "rainfall_total_mm": round(
                self.rainfall_total(),
                4
            ),

            "rainfall_last_hour_mm": round(
                self.window_rainfall(),
                4
            ),

            "tip_counter": self.raw_tip_count(),

            "working_time_hours": round(
                self.working_time_hours(),
                2
            )

        }

    def close(self):
        self.bus.close()