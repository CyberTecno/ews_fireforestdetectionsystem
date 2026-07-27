import minimalmodbus
import serial
import time
from config import settings

class AnemometerSensor:
    # Mengubah default paramater ke nilai yang SUDAH TERBUKTI BERHASIL
    # (Port USB0, Slave ID 2, Baudrate 9600).
    # Jika di file config/settings.py Anda parameternya berbeda, kita amankan di sini.
    def __init__(self, port='/dev/ttyUSB0', slave_id=2, baudrate=9600):
        
        # Inisialisasi Modbus
        self.instrument = minimalmodbus.Instrument(port, slave_id)
        self.instrument.serial.baudrate = baudrate
        self.instrument.serial.bytesize = 8
        self.instrument.serial.parity = serial.PARITY_NONE
        self.instrument.serial.stopbits = 1
        self.instrument.serial.timeout = 1.0
        self.instrument.mode = minimalmodbus.MODE_RTU

    def read_wind_speed(self):
        # MENGGUNAKAN PENGATURAN YANG BERHASIL: 
        # Register 0, 1 desimal, dan functioncode 3 (sebelumnya di kode lama functioncode=4)
        return self.instrument.read_register(0, number_of_decimals=1, functioncode=3)

    def read(self):
        try:
            # Mengambil data dari sensor
            speed = self.read_wind_speed()
            return {"speed_ms": speed}
            
        except minimalmodbus.NoResponseError:
            # Penanganan khusus jika sensor mati / kabel terputus
            return {"speed_ms": None, "error": "No response: Cek kabel A/B dan power supply"}
        except Exception as e:
            # Penanganan error lainnya
            return {"speed_ms": None, "error": str(e)}

# Blok untuk pengetesan langsung di dalam folder sensors
if __name__ == "__main__":
    sensor = AnemometerSensor()
    print("=== MENGUJI CLASS ANEMOMETER ===")
    print("Membaca sensor... (Tekan Ctrl+C untuk berhenti)\n")
    
    while True:
        data = sensor.read()
        
        # Cek apakah pembacaan sukses
        if data.get("speed_ms") is not None:
            print(f"Kecepatan Angin: {data['speed_ms']} m/s")
        else:
            print(f"Error: {data['error']}")
            
        time.sleep(1)
