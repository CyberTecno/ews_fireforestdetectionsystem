"""
TEST 3 — IR Flame Sensor (4-wire)
Usage: python3 tests/test_flame.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.flame import FlameSensor

print("=" * 60)
print("  TEST IR Flame Sensor (4-wire: VCC, GND, DO, AO)")
print("=" * 60)

try:
    sensor = FlameSensor(read_analog=True)
    print("[OK] Flame sensor diinisialisasi (DO via GPIO + AO via MCP3008).\n")
except Exception as e:
    print(f"[FAIL] Gagal inisialisasi: {e}")
    print("Kalau AO tidak Anda kabel, edit test ini: FlameSensor(read_analog=False)")
    sys.exit(1)

print("Nyalakan korek api / lighter ~30cm di depan sensor untuk lihat flame_detected=True.")
print("Membaca tiap 0.5 detik selama 20 detik (Ctrl+C untuk stop)...\n")

try:
    for i in range(40):
        d = sensor.read()
        flag = "🔥 API TERDETEKSI!" if d["flame_detected"] else "   normal"
        extra = f" | AO={d.get('analog_voltage', 'N/A')}V" if "analog_voltage" in d else ""
        print(f"raw={d['raw']} | flame_detected={d['flame_detected']!s:5}{extra}  {flag}")
        time.sleep(0.5)
except KeyboardInterrupt:
    pass

print("\n[CATATAN] Kalau flame_detected SELALU True walau tidak ada api, kemungkinan:")
print("  - active_low salah (coba FlameSensor(active_low=False))")
print("  - Wiring DO tidak lewat logic level converter dengan benar")
