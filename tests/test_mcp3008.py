"""
TEST 1 — MCP3008 (ADC SPI)
Jalankan SEBELUM testing sensor analog apapun (MQ-2/MQ-135/soil), karena
semua sensor itu bergantung ke chip ini.

Usage: python3 tests/test_mcp3008.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.mcp3008 import MCP3008

print("=" * 60)
print("  TEST MCP3008 (SPI ADC)")
print("=" * 60)
print("Pastikan SPI sudah diaktifkan: sudo raspi-config -> Interface -> SPI -> Yes")
print("Lalu cek device: ls /dev/spidev* (harus muncul /dev/spidev0.0)\n")

try:
    adc = MCP3008()
    print(f"[OK] MCP3008 terbuka di SPI bus={adc.bus}, device={adc.device}, VREF={adc.vref}V\n")
except Exception as e:
    print(f"[FAIL] Tidak bisa buka MCP3008: {e}")
    print("\nKemungkinan penyebab:")
    print("  - SPI belum diaktifkan (raspi-config)")
    print("  - spidev belum terinstall (pip install spidev)")
    print("  - Wiring CLK/DOUT/DIN/CS salah (cek docs/Pinout.md)")
    sys.exit(1)

print("Membaca semua 8 channel selama 10 detik (Ctrl+C untuk stop lebih awal)...")
print("Channel yang TIDAK terhubung sensor akan menunjukkan nilai acak/noise - itu NORMAL.\n")

try:
    for i in range(10):
        readings = []
        for ch in range(8):
            raw = adc.read_raw(ch)
            volt = adc.read_voltage(ch)
            readings.append(f"CH{ch}={raw:4d}({volt:.2f}V)")
        print(" | ".join(readings))
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    adc.close()

print("\n[SELESAI] Kalau channel yang ada sensornya (CH0-CH3) menunjukkan nilai")
print("yang BERUBAH saat Anda tutup sensor dengan tangan / kabel disentuh,")
print("berarti wiring SPI MCP3008 sudah benar.")
