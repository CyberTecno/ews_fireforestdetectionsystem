"""
TEST — Submersible Pressure Sensor (ketinggian air, loop 4-20mA via burden resistor)

Cek dulu sebelum run:
  ls /dev/spidev*  → harus ada /dev/spidev0.0
  R_BURDEN 250Ω terpasang di loop, tap-nya ke LLC HV-5 → LV-5 → MCP3008 CH4
  PSU loop 12-24V sudah menyala (sensor ini loop-powered, BUKAN dari Pi/buck 5V)

Yang dicek:
  1. Sensor bisa dibaca tanpa exception.
  2. current_ma ada di rentang wajar 4-20mA (di luar itu = sinyal aneh/loop bermasalah).
  3. fault_open_loop tidak menyala terus-menerus (kalau iya → loop kemungkinan putus).
  4. depth_m masuk akal (0 sampai PRESSURE_RANGE_M).

Usage: python3 tests/test_pressure.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from sensors.pressure import PressureWaterSensor

print("=" * 60)
print("  TEST — Submersible Pressure Sensor (MCP3008 CH4)")
print("=" * 60)
print(f"R_BURDEN    : {settings.PRESSURE_BURDEN_OHM}Ω")
print(f"Rentang mA  : {settings.PRESSURE_MIN_MA}-{settings.PRESSURE_MAX_MA}mA")
print(f"Range depth : 0-{settings.PRESSURE_RANGE_M}m  (sesuaikan EFWS_PRESSURE_RANGE_M kalau beda datasheet)\n")

try:
    sensor = PressureWaterSensor()
except Exception as e:
    print(f"❌ Gagal inisialisasi: {e}")
    print("Cek: ls /dev/spidev* harus menunjukkan /dev/spidev0.0")
    sys.exit(1)

N = 5
fault_count = 0
readings = []

print(f"Membaca {N}x, tiap 2 detik (Ctrl+C untuk stop lebih awal)...\n")
try:
    for i in range(N):
        r = sensor.read()
        readings.append(r)
        if r["fault_open_loop"]:
            fault_count += 1
        flag = "  ⚠️ fault_open_loop!" if r["fault_open_loop"] else ""
        print(f"  [{i+1}] current={r['current_ma']}mA  depth={r['depth_m']}m  "
              f"pressure={r['pressure_bar']}bar{flag}")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nDihentikan oleh user.")
    sys.exit(0)

print("\n" + "=" * 60)
print("  RINGKASAN")
print("=" * 60)

problems = []

ma_values = [r["current_ma"] for r in readings]
out_of_range = [ma for ma in ma_values if ma < 3.5 or ma > 21.0]
if out_of_range:
    problems.append(f"Ada pembacaan current_ma di luar rentang wajar 4-20mA: {out_of_range}")
else:
    print(f"  ✅ current_ma semua di rentang wajar ({min(ma_values)}-{max(ma_values)}mA)")

if fault_count == N:
    problems.append("fault_open_loop menyala di SEMUA pembacaan — loop kemungkinan putus/belum tersambung")
elif fault_count > 0:
    print(f"  ⚠️  fault_open_loop menyala {fault_count}/{N}x — cek sambungan loop kalau ini tidak diharapkan")
else:
    print("  ✅ Tidak ada fault_open_loop selama test")

depth_values = [r["depth_m"] for r in readings]
if any(d < 0 or d > settings.PRESSURE_RANGE_M for d in depth_values):
    problems.append(f"Ada depth_m di luar rentang 0-{settings.PRESSURE_RANGE_M}m")
else:
    print(f"  ✅ depth_m semua di rentang 0-{settings.PRESSURE_RANGE_M}m ({min(depth_values)}-{max(depth_values)}m)")

print()
if problems:
    print("❌ Ada yang perlu dicek:")
    for p in problems:
        print(f"   - {p}")
    print("\nLihat docs/Pinout.md bagian 'Submersible Pressure Sensor' untuk detail wiring.")
    sys.exit(1)
else:
    print("✅ Submersible pressure sensor terbaca dengan baik.")
