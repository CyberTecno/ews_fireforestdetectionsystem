import serial, time

from config import settings



class WindDirectionSensor:
    """
4-wire wind direction sensor, UART:
      VCC (merah) -> 3.3V
      GND (hitam) -> GND
      TX  (kuning) -> GPIO14 / pin 8  (RXD Raspberry Pi)
      RX  (hijau)  -> GPIO15 / pin 10 (TXD Raspberry Pi)

Protocol: text line "*<code>#", code 1-8 = N/NE/E/SE/S/SW/W/NW.

IMPORTANT NOTE (Raspberry Pi 4 + UART GPIO14/15):
By default, /dev/serial0 on the RPi4 connects to mini-UART, which
The clock also goes up and down according to the VPU core frequency -- baudrate is possible
ngaco/drift if not locked (core_freq=250 on /boot/config.txt), or
This port is still used by Bluetooth (RPi4 default). If this sensor occurs frequently
empty/datanya random, that's a typical symptom. Need to confirm: whether
/boot/config.txt You have used dtoverlay=disable-bt (so that PL011 is full
UART moved to GPIO14/15) and console serial (login shell via UART)
Has it been turned off via raspi-config? If not, this sensor is risky
sends garbage/intermittent data even when the wiring and code are correct.
    """

    def __init__(self):
        self.ser = serial.Serial(
            settings.WIND_DIR_PORT,
            settings.WIND_DIR_BAUDRATE,
            timeout=settings.WIND_DIR_TIMEOUT,
        )
        # Clean remaining old data that may be stuck in the OS buffer.
        self.ser.reset_input_buffer()
        # LAST valid read cache -- used during this sampling cycle
        # Coincidentally there haven't been any new lines coming in (the sensor keeps sending every time
        # several hundred ms, much faster than our read cycle).
        self._last = None

    _COMPASS = {
        1: ("N",  "Utara"),
        2: ("NE", "Timur Laut"),
        3: ("E",  "Timur"),
        4: ("SE", "Tenggara"),
        5: ("S",  "Selatan"),
        6: ("SW", "Southwest"),
        7: ("W",  "Barat"),
        8: ("NW", "Barat Laut"),
    }

    def _decode(self, code: int):
        abbr, name_id = self._COMPASS.get(code, (None, None))
        name = f"{name_id} ({abbr})" if abbr else f"Unknown ({code})"
        return abbr, name

    def read(self) -> dict:
        """
Read the latest wind direction from UART.

If there is no data in the buffer when the function is called,
wait until WIND_DIR_TIMEOUT to get the minimum
one row of data.

The last valid read cache remains in use if on
the next cycle there is no new data.
        """
        try:
            latest_code = None

            # ---------------------------------------------------------
            # 1. Wait for the first data if the buffer is still empty
            # ---------------------------------------------------------
            if self.ser.in_waiting == 0:
                raw = self.ser.readline().decode(
                    "utf-8",
                    errors="ignore"
                ).strip()

                if raw.startswith("*") and raw.endswith("#"):
                    angka_str = raw[1:-1]

                    if angka_str.isdigit():
                        latest_code = int(angka_str)

            # ---------------------------------------------------------
            # 2. Drain all remaining data in the buffer
            #    so that we take the MOST NEW data
            # ---------------------------------------------------------
            while self.ser.in_waiting > 0:
                raw = self.ser.readline().decode(
                    "utf-8",
                    errors="ignore"
                ).strip()

                if raw.startswith("*") and raw.endswith("#"):
                    angka_str = raw[1:-1]

                    if angka_str.isdigit():
                        latest_code = int(angka_str)

            # ---------------------------------------------------------
            # 3. If you get a valid code, update the cache
            # ---------------------------------------------------------
            if latest_code is not None:
                abbr, name = self._decode(latest_code)

                self._last = {
                    "direction_code": latest_code,
                    "direction_abbr": abbr,
                    "direction_name": name,
                }

            # ---------------------------------------------------------
            # 4. If you have cache, use the last reading
            # ---------------------------------------------------------
            if self._last is not None:
                return dict(self._last)

            # ---------------------------------------------------------
            # 5. Really never get the data
            # ---------------------------------------------------------
            return {
                "direction_code": None,
                "direction_abbr": None,
                "direction_name": None,
                "error": "there has been no incoming data from the sensor since EFWS started",
            }

        except Exception as e:
            return {
                "direction_code": None,
                "direction_abbr": None,
                "direction_name": None,
                "error": str(e),
            }
# Block for direct testing (manual hardware check, NOT pytest --
# see tests/hardware_checks/ for the naming convention of this check_*.py project)
if __name__ == "__main__":

    sensor = WindDirectionSensor()
    print("=== EFWS Wind Direction Test ===")
    print("Rotate the sensor propeller... (Ctrl+C to stop)\n")
    try:
        while True:
            data = sensor.read()
            if data.get("error"):
                print(f"Error: {data['error']}")
            else:
                print(f"Kode: {data['direction_code']} | {data['direction_abbr']} | {data['direction_name']}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
