"""
BME280 — Temperature / Humidity / Pressure ambient sensor (I2C).
Dipakai untuk deteksi kondisi ambient (suhu tinggi + kelembaban rendah =
risiko kebakaran meningkat). TIDAK lewat MCP3008/LLC — modul ini I2C native.

Requires: pip install smbus2 RPi.bme280
"""
import time
from config import settings

try:
    import smbus2
    import bme280 as _bme280_lib
except ImportError:
    smbus2 = None
    _bme280_lib = None


class BME280Sensor:
    def __init__(self, bus=None, address=None):
        if smbus2 is None or _bme280_lib is None:
            raise RuntimeError("smbus2/RPi.bme280 tidak terinstall - pip install smbus2 RPi.bme280")

        self.bus_num  = bus     if bus     is not None else settings.I2C_BUS
        self.address  = address if address is not None else settings.BME280_ADDRESS
        self.bus       = smbus2.SMBus(self.bus_num)
        
        # ─── MODIFIKASI 1: BANGUNKAN SENSOR SECARA MANUAL (ANTI SLEEP/ERRNO 5) ───
        self._initialize_sensor_hardware()
        
        # Ambil data kalibrasi setelah sensor dipastikan terbangun dan stabil
        try:
            self.calib = _bme280_lib.load_calibration_params(self.bus, self.address)
        except OSError as e:
            # Jika masih error, kita beri toleransi jeda dan coba sekali lagi
            time.sleep(0.2)
            self.calib = _bme280_lib.load_calibration_params(self.bus, self.address)

    def _initialize_sensor_hardware(self):
        """
        Memaksa sensor masuk ke Normal Mode dengan membaca/menulis per-byte.
        Sangat krusial untuk mengatasi kabel panjang 1.5m dan drop tegangan.
        """
        try:
            # Pancing koneksi dengan membaca Chip ID (Byte tunggal)
            chip_id = self.bus.read_byte_data(self.address, 0xD0)
            
            if chip_id == 0x60:
                # Daftarkan konfigurasi ke register kontrol (0xF2 dan 0xF4) secara bertahap
                # Atur Humidity Oversampling 1x (Reg 0xF2)
                self.bus.write_byte_data(self.address, 0xF2, 0x01)
                time.sleep(0.05)
                
                # Paksa masuk Normal Mode (Reg 0xF4) -> Temp x1, Press x1, Mode Normal
                self.bus.write_byte_data(self.address, 0xF4, 0x27)
                time.sleep(0.1) # Beri waktu sirkuit internal sensor mengisi daya
        except Exception:
            # Biarkan lolos jika gagal, agar tidak langsung membuat crash aplikasi utama
            pass

    def read(self) -> dict:
        try:
            data = _bme280_lib.sample(self.bus, self.address, self.calib)
            
            # Validasi apakah data yang didapat konstan 0x800000 (tidak valid / tertidur)
            # Pada library RPi.bme280, jika ia gagal, nilai temperatur biasanya bernilai ekstrem atau None
            if data.temperature == 0.0 and data.humidity == 0.0:
                 raise ValueError("Data sensor kosong / tidak valid")

            return {
                "temperature_c":    round(data.temperature, 2),
                "humidity_percent": round(data.humidity, 2),
                "pressure_hpa":     round(data.pressure, 2),
            }
        except Exception as e:
            # Jika terjadi error saat operasional, coba bangunkan kembali hardware-nya
            self._initialize_sensor_hardware()
            return {"temperature_c": None, "humidity_percent": None,
                    "pressure_hpa": None, "error": str(e)}

    def close(self):
        self.bus.close()


if __name__ == "__main__":
    sensor = BME280Sensor()
    try:
        while True:
            print(sensor.read())
            time.sleep(2)
    except KeyboardInterrupt:
        sensor.close()
        print("\nPengujian dihentikan.")
