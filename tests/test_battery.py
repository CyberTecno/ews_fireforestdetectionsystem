"""
TEST — Modul Sensor Tegangan DC (baterai, LANGSUNG ke MCP3008 CH5, TANPA LLC)

Cek dulu sebelum run:
  ls /dev/spidev*  → harus ada /dev/spidev0.0
  Pin S modul tersambung LANGSUNG ke MCP3008 CH5 (BUKAN lewat LLC -- sinyal
  modul ini sudah native 3.3V, lihat sensors/battery.py)
  Pin "+"/"−" modul (logic side, BEDA dari IN+/IN− yang diukur) ke 3.3V/GND Pi

Usage: python3 tests/test_battery.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.battery import BatterySensor

print("=" * 60)
print("  TEST — Battery Voltage Sensor (MCP3008 CH5)")
print("=" * 60)

sensor = BatterySensor()
print("Membaca 5x, tiap 2 detik (Ctrl+C untuk stop lebih awal)...\n")
try:
    for i in range(5):
        reading = sensor.read()
        print(f"  [{i+1}] voltage={reading['voltage']}V  percent={reading['percent']}%")
        time.sleep(2)
    print("\n✅ Battery sensor terbaca dengan baik.")
except KeyboardInterrupt:
    print("\nDihentikan oleh user.")
