import serial
import time

class WindDirectionSensor:
    def __init__(self, port='/dev/serial0', baudrate=9600):
        try:
            # /dev/serial0 adalah alias standar untuk pin GPIO 14 & 15 di Raspberry Pi
            self.ser = serial.Serial(port, baudrate, timeout=1)
            # Bersihkan sisa data lama yang mungkin nyangkut
            self.ser.flushInput() 
        except Exception as e:
            print(f"Error membuka port serial: {e}")
            self.ser = None

    def get_direction_name(self, code):
        # Kamus terjemahan arah angin (Bisa Anda sesuaikan jika arahnya terbalik)
        directions = {
            1: "Utara (N)",
            2: "Timur Laut (NE)",
            3: "Timur (E)",
            4: "Tenggara (SE)",
            5: "Selatan (S)",
            6: "Barat Daya (SW)",
            7: "Barat (W)",
            8: "Barat Laut (NW)"
        }
        return directions.get(code, f"Tidak diketahui ({code})")

    def read(self):
        if self.ser is None:
            return {"direction_code": None, "direction_name": None, "error": "Serial port tidak terbuka"}

        try:
            # Baca data baris per baris
            if self.ser.in_waiting > 0:
                data = self.ser.readline().decode('utf-8').strip()
                
                # Pastikan formatnya benar: contoh *5#
                if data.startswith('*') and data.endswith('#'):
                    # Ambil karakter di tengah (membuang bintang dan pagar)
                    angka_str = data[1:-1]
                    
                    if angka_str.isdigit():
                        kode = int(angka_str)
                        nama = self.get_direction_name(kode)
                        return {"direction_code": kode, "direction_name": nama}
                        
        except UnicodeDecodeError:
            # Abaikan jika ada data sampah/noise saat kabel baru dicolok
            pass
        except Exception as e:
            return {"direction_code": None, "direction_name": None, "error": str(e)}

        return None # Jika sedang tidak ada data yang masuk

# Blok ini HANYA berjalan jika file ini dieksekusi langsung (untuk testing)
if __name__ == "__main__":
    sensor = WindDirectionSensor()
    print("=== TEST SENSOR ARAH ANGIN ZHAFIRA (RASPBERRY PI) ===")
    print("Putar baling-baling sensor... (Tekan Ctrl+C untuk berhenti)\n")
    
    while True:
        hasil = sensor.read()
        if hasil:
            if "error" in hasil:
                print(f"Error: {hasil['error']}")
            else:
                print(f"Data Masuk -> Kode: {hasil['direction_code']} | Arah: {hasil['direction_name']}")
        
        time.sleep(0.1) # Jeda super singkat agar tidak ketinggalan data
