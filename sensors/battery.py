from gpiozero import MCP3008
import time

# 1. Inisialisasi MCP3008
# Menggunakan channel 0 (karena sensor dicolok ke CH0 / Pin 1)
adc = MCP3008(channel=0)

# 2. Konstanta Perhitungan
# Tegangan referensi MCP3008 (kita hubungkan ke 3.3V Pi)
VREF = 3.3 

# Rasio dari sensor pembagi tegangan (30k dan 7.5k = rasio 5)
RASIO_SENSOR = 5.0 

print("Membaca tegangan 14.4V via MCP3008...")
print("Tekan Ctrl+C untuk berhenti.\n")

try:
    while True:
        # adc.value mengembalikan nilai rasio dari 0.0 hingga 1.0
        # (0.0 = 0V, 1.0 = sama dengan VREF atau 3.3V)
        nilai_mentah = adc.value
        
        # Hitung tegangan yang masuk ke pin CH0
        tegangan_pin = nilai_mentah * VREF
        
        # Hitung tegangan asli power supply (dikalikan rasio modul sensor)
        tegangan_asli = tegangan_pin * RASIO_SENSOR
        
        # Print hasil
        print(f"Tegangan Terbaca: {tegangan_asli:.2f} V (Tegangan Pin: {tegangan_pin:.2f} V)")
        
        # Jeda setengah detik
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nProgram dihentikan.")