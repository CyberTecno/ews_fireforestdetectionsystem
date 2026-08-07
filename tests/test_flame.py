"""
TEST — IR Flame Sensor (AO analog via MCP3008, TIDAK pakai GPIO/DO)
Usage: python3 tests/test_flame.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.flame import FlameSensor

print("=" * 60)
print("  TEST IR Flame Sensor (AO analog via MCP3008)")
print("=" * 60)

try:
    sensor = FlameSensor()
    print(f"[OK] Flame sensor diinisialisasi (CH{sensor.channel}, "
          f"threshold={sensor.threshold_v}V, trigger_below={sensor.trigger_below}).\n")
except Exception as e:
    print(f"[FAIL] Gagal inisialisasi: {e}")
    sys.exit(1)

print("BELUM DIKALIBRASI -- catat nilai AO di kondisi normal DULU, baru")
print("dekatkan api kecil yang aman dan catat lagi, lalu set")
print("EFWS_FLAME_AO_THRESHOLD_V di antara keduanya (lihat sensors/flame.py).")
print("Membaca tiap 0.5 detik selama 20 detik (Ctrl+C untuk stop)...\n")

try:
    for i in range(40):
        d = sensor.read()
        flag = "🔥 API TERDETEKSI!" if d["flame_detected"] else "   normal"
        print(f"AO={d['analog_voltage']:.3f}V | flame_detected={d['flame_detected']!s:5}  {flag}")
        time.sleep(0.5)
except KeyboardInterrupt:
    pass

print("\n[CATATAN] Kalau flame_detected SELALU True walau tidak ada api, kemungkinan:")
print("  - Arah threshold salah -> coba FlameSensor(trigger_below=False)")
print("  - FLAME_AO_THRESHOLD_V belum dikalibrasi ke unit fisik Anda")
