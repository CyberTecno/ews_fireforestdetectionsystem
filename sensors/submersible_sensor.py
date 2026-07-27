from gpiozero import MCP3008
import time

# Kita asumsikan kabel kuning/hitam masuk ke channel 0 (CH0) di MCP3008
# Jika Anda colok ke CH1, ganti angka 0 menjadi 1 di bawah ini
adc = MCP3008(channel=0)

# Masukkan nilai resistor yang Anda gunakan (misal 150 atau 100)
RESISTOR_OHM = 100
VREF = 3.3 # Tegangan referensi MCP3008 (standar Raspberry Pi)

print("=== TEST SENSOR AIR (4-20mA) ===")
print("Tekan Ctrl+C untuk berhenti\n")

while True:
    try:
        # adc.value memberikan persentase (0.0 sampai 1.0)
        # Kita ubah jadi tegangan nyata (Volt)
        tegangan = adc.value * VREF
        
        # Hitung arus listrik (Hukum Ohm: I = V / R) dalam satuan mA
        arus_mA = (tegangan / RESISTOR_OHM) * 1000
        
        # Hitung ketinggian air
        # Sensor ini: 4mA = 0 mm, 20mA = 4000 mm
        # Jarak range arus = 16mA (dari 20 - 4), Range air = 4000 mm
        
        if arus_mA < 3.8:
            status = "SENSOR TERPUTUS / KERING"
            level_air_mm = 0
        else:
            status = "OK"
            level_air_mm = ((arus_mA - 4.0) / 16.0) * 4000
            
            # Jangan biarkan angkanya minus jika arus sedikit di bawah 4mA
            if level_air_mm < 0: level_air_mm = 0
            # Maksimal 4000 mm
            if level_air_mm > 4000: level_air_mm = 4000

        print(f"Volt: {tegangan:.2f}V | Arus: {arus_mA:.2f} mA | Level Air: {level_air_mm:.1f} mm | Status: {status}")
        
    except Exception as e:
        print(f"Error: {e}")
        
    time.sleep(1)
