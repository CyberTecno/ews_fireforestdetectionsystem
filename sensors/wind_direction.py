import serial, time

from config import settings



class WindDirectionSensor:
    """
    Sensor arah angin 4-kabel, UART:
      VCC (merah) -> 3.3V
      GND (hitam) -> GND
      TX  (kuning) -> GPIO14 / pin 8  (RXD Raspberry Pi)
      RX  (hijau)  -> GPIO15 / pin 10 (TXD Raspberry Pi)

    Protokol: baris teks "*<kode>#", kode 1-8 = N/NE/E/SE/S/SW/W/NW.

    CATATAN PENTING (Raspberry Pi 4 + UART GPIO14/15):
    Secara default, /dev/serial0 di RPi4 nyambung ke mini-UART, yang
    clock-nya ikut naik-turun mengikuti frekuensi VPU core -- baudrate bisa
    ngaco/drift kalau tidak di-lock (core_freq=250 di /boot/config.txt), atau
    port ini masih dipakai Bluetooth (default RPi4). Kalau sensor ini sering
    kosong/datanya acak, itu gejala khasnya. Perlu dikonfirmasi: apakah
    /boot/config.txt Anda sudah pakai dtoverlay=disable-bt (supaya PL011 full
    UART pindah ke GPIO14/15) dan console serial (login shell lewat UART)
    sudah dimatikan lewat raspi-config? Kalau belum, sensor ini berisiko
    kirim data sampah/putus-putus walau wiring & kode-nya benar.
    """

    def __init__(self):
        self.ser = serial.Serial(
            settings.WIND_DIR_PORT,
            settings.WIND_DIR_BAUDRATE,
            timeout=settings.WIND_DIR_TIMEOUT,
        )
        # Bersihkan sisa data lama yang mungkin nyangkut di buffer OS.
        self.ser.reset_input_buffer()
        # Cache bacaan valid TERAKHIR -- dipakai kalau siklus sampling ini
        # kebetulan belum ada baris baru masuk (sensor kirim terus tiap
        # beberapa ratus ms, jauh lebih cepat dari siklus baca kita).
        self._last = None

    _COMPASS = {
        1: ("N",  "Utara"),
        2: ("NE", "Timur Laut"),
        3: ("E",  "Timur"),
        4: ("SE", "Tenggara"),
        5: ("S",  "Selatan"),
        6: ("SW", "Barat Daya"),
        7: ("W",  "Barat"),
        8: ("NW", "Barat Laut"),
    }

    def _decode(self, code: int):
        abbr, name_id = self._COMPASS.get(code, (None, None))
        name = f"{name_id} ({abbr})" if abbr else f"Tidak diketahui ({code})"
        return abbr, name

    def read(self) -> dict:
        """
        SELALU return dict berisi ketiga field ini (schema tetap, sama
        seperti sensor lain di project ini -- lihat null_sensor.py), TIDAK
        PERNAH return None, supaya caller (main.py) tidak perlu penanganan
        khusus untuk sensor ini.
        """
        try:
            # Kuras SEMUA baris yang menumpuk di buffer, ambil yang PALING
            # BARU -- kalau cuma baca baris pertama, di siklus baca yang
            # jarang (default tiap beberapa menit) datanya akan basi/telat.
            latest_code = None
            while self.ser.in_waiting > 0:
                raw = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if raw.startswith("*") and raw.endswith("#"):
                    angka_str = raw[1:-1]
                    if angka_str.isdigit():
                        latest_code = int(angka_str)

            if latest_code is not None:
                abbr, name = self._decode(latest_code)
                self._last = {
                    "direction_code": latest_code,
                    "direction_abbr": abbr,
                    "direction_name": name,
                }

            if self._last is not None:
                return dict(self._last)

            return {
                "direction_code": None,
                "direction_abbr": None,
                "direction_name": None,
                "error": "belum ada data masuk dari sensor sejak EFWS start",
            }

        except Exception as e:
            return {
                "direction_code": None,
                "direction_abbr": None,
                "direction_name": None,
                "error": str(e),
            }


# Blok untuk pengetesan langsung (hardware check manual, BUKAN pytest --
# lihat tests/hardware_checks/ untuk konvensi penamaan check_*.py project ini)
if __name__ == "__main__":

    sensor = WindDirectionSensor()
    print("=== EFWS Wind Direction Test ===")
    print("Putar baling-baling sensor... (Ctrl+C untuk berhenti)\n")
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
