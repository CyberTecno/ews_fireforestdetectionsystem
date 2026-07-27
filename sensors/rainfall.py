"""
DFRobot Gravity Rainfall Sensor (SEN0575)
Native Raspberry Pi driver using smbus2.

Requires:
    pip install smbus2

Author:
    EFWS Native Driver
"""

from config import settings

try:
    import smbus2
except ImportError:
    smbus2 = None


class RainfallSensor:
    # I2C Address
    DEFAULT_ADDRESS = 0x1D

    # Registers
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
                "smbus2 not installed. Run:\n"
                "pip install smbus2"
            )

        self.bus_num = bus if bus is not None else settings.I2C_BUS
        self.address = address if address is not None else self.DEFAULT_ADDRESS

        self.bus = smbus2.SMBus(self.bus_num)

    ##########################################################
    # Low-level functions
    ##########################################################

    def _read(self, register, length):
        return self.bus.read_i2c_block_data(
            self.address,
            register,
            length
        )

    def _write(self, register, data):
        if isinstance(data, int):
            data = [data]

        self.bus.write_i2c_block_data(
            self.address,
            register,
            data
        )

    ##########################################################
    # Device Information
    ##########################################################

    def begin(self):
        """
        Verify PID/VID exactly like Arduino library.
        """

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
            and vid == self.EXPECTED_VID
        )

    def firmware_version(self):

        data = self._read(self.REG_VERSION, 2)

        version = data[0] | (data[1] << 8)

        return "{}.{}.{}.{}".format(
            version >> 12,
            (version >> 8) & 0x0F,
            (version >> 4) & 0x0F,
            version & 0x0F,
        )

    ##########################################################
    # Measurements
    ##########################################################

    def rainfall_total(self):

        data = self._read(self.REG_CUMULATIVE_RAINFALL, 4)

        value = int.from_bytes(data, byteorder="little")

        return round(value / 10000.0, 4)

    def rainfall(self, hours=1):

        if hours < 1 or hours > 24:
            raise ValueError("hours must be 1-24")

        self._write(self.REG_RAIN_HOUR, hours)

        data = self._read(self.REG_TIME_RAINFALL, 4)

        value = int.from_bytes(data, byteorder="little")

        return round(value / 10000.0, 4)

    def raw_tip_count(self):

        data = self._read(self.REG_RAW_DATA, 4)

        return int.from_bytes(data, byteorder="little")

    def working_time_hours(self):

        data = self._read(self.REG_SYS_TIME, 2)

        minutes = int.from_bytes(data, byteorder="little")

        return round(minutes / 60.0, 2)

    ##########################################################
    # Configuration
    ##########################################################

    def set_accumulated_value(self, value):

        raw = int(value * 10000)

        data = [
            raw & 0xFF,
            (raw >> 8) & 0xFF
        ]

        self._write(self.REG_BASE_RAINFALL, data)

    ##########################################################

    def read(self):

        return {
            "rainfall_total_mm": self.rainfall_total(),
            "rainfall_last_hour_mm": self.rainfall(1),
            "tip_counter": self.raw_tip_count(),
            "working_time_hours": self.working_time_hours(),
        }