"""
TEST — Soil Moisture Probe (dua probe: surface + deep)

Probe SURFACE (CH2): kedalaman 0-30cm — kondisi permukaan tanah
Probe DEEP    (CH3): kedalaman 30-60cm — kelembaban dalam tanah

Evaluasi di EFWS mengambil nilai TERENDAH (terburuk) dari keduanya.

Usage: python3 tests/test_soil.py
"""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.soil import SoilMoistureSensor

print("=" * 60)
print("  TEST Soil Moisture (dual probe: surface + deep)")
print("=" * 60)

try:
    sensor = SoilMoistureSensor()
    print("[OK] Soil sensor diinisialisasi (CH2=surface, CH3=deep).\n")
except Exception as e:
    print(f"[FAIL] {e}"); sys.exit(1)

print("LANGKAH KALIBRASI per probe:")
print("  1. Probe di UDARA KERING → catat 'raw' → itu dry_raw")
print("  2. Probe TERENDAM AIR    → catat 'raw' → itu wet_raw")
print("  Update nilai di sensors/soil.py SoilMoistureSensor.__init__\n")

print("Membaca tiap 1 detik (Ctrl+C untuk stop)...\n")
try:
    for _ in range(20):
        d = sensor.read()
        s = d["surface"]
        dp = d["deep"]
        worst = min(s["moisture_percent"], dp["moisture_percent"])
        status = "🔴 CRITICAL" if worst < 10 else "🟡 WARNING" if worst < 20 else "🟢 OK"
        print(f"  Surface: raw={s['raw']:4d}  {s['moisture_percent']:5.1f}%  |  "
              f"Deep: raw={dp['raw']:4d}  {dp['moisture_percent']:5.1f}%  |  "
              f"Worst={worst:.1f}%  {status}")
        time.sleep(1)
except KeyboardInterrupt:
    pass
