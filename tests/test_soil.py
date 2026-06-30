"""
TEST 5 — Soil Moisture Probe (waterproof, analog via MCP3008)
Usage: python3 tests/test_soil.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.soil import SoilMoistureSensor

print("=" * 60)
print("  TEST Soil Moisture Probe")
print("=" * 60)

try:
    sensor = SoilMoistureSensor()
    print("[OK] Soil sensor diinisialisasi.\n")
except Exception as e:
    print(f"[FAIL] Gagal inisialisasi: {e}")
    sys.exit(1)

print("LANGKAH KALIBRASI (lakukan ini sebelum pasang permanen):")
print("  1. Biarkan probe di UDARA KERING beberapa detik, catat 'raw' di bawah -> jadi dry_raw")
print("  2. Celupkan probe ke AIR, catat 'raw' lagi -> jadi wet_raw")
print("  3. Update nilai dry_raw/wet_raw di sensors/soil.py SoilMoistureSensor.__init__\n")

print("Membaca tiap 1 detik selama 20 detik (Ctrl+C untuk stop)...\n")
try:
    for i in range(20):
        d = sensor.read()
        print(f"raw={d['raw']:4d} | moisture={d['moisture_percent']:.1f}%")
        time.sleep(1)
except KeyboardInterrupt:
    pass
