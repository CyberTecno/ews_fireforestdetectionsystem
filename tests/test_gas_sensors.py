"""
TEST 2 — MQ-2 (asap/gas) & MQ-135 (kualitas udara)
Jalankan SETELAH test_mcp3008.py berhasil.

PENTING: MQ-2 dan MQ-135 butuh waktu PEMANASAN (preheat) heater internal
sekitar 24-48 jam sebelum pembacaan stabil & akurat. Untuk testing wiring
saja (bukan akurasi), tunggu minimal 2-3 menit setelah power-on.

Usage: python3 tests/test_gas_sensors.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.mq2 import MQ2Sensor
from sensors.mq135 import MQ135Sensor

print("=" * 60)
print("  TEST MQ-2 & MQ-135 (lewat MCP3008)")
print("=" * 60)

try:
    mq2 = MQ2Sensor()
    mq135 = MQ135Sensor()
    print("[OK] Kedua sensor berhasil diinisialisasi.\n")
except Exception as e:
    print(f"[FAIL] Gagal inisialisasi: {e}")
    sys.exit(1)

print("Membaca tiap 2 detik selama 20 detik (Ctrl+C untuk stop)...")
print("Coba dekatkan korek api yang baru dipadamkan (asap) ke MQ-2 untuk lihat ppm naik.\n")

try:
    for i in range(10):
        d2 = mq2.read()
        d135 = mq135.read()
        print(f"MQ-2:   voltage={d2['voltage']:.3f}V  ppm={d2['ppm']:.1f}   |   "
              f"MQ-135: voltage={d135['voltage']:.3f}V  ppm={d135['ppm']:.1f}")
        time.sleep(2)
except KeyboardInterrupt:
    pass

print("\n[CATATAN] Nilai ppm di atas BELUM dikalibrasi - hanya pendekatan linear.")
print("Untuk produksi, kalibrasi R0 di udara bersih sesuai datasheet MQ-2/MQ-135.")
