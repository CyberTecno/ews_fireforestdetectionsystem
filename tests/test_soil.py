"""
TEST — Soil Moisture Probe (dua probe: surface + deep)

SURFACE probe (CH2): depth 0-30cm — ground surface conditions
DEEP probe (CH3): depth 30-60cm — moisture in the soil

The evaluation on EFWS takes the LOWEST (worst) value of the two.

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
    print("[OK] Soil sensor initialized (CH2=surface, CH3=deep).\n")
except Exception as e:
    print(f"[FAIL] {e}"); sys.exit(1)

print("CALIBRATION STEPS per probe:")
print("1. Probe in DRY AIR → note 'raw' → that's dry_raw")
print("2. The probe is submerged in water → note 'raw' → that's wet_raw")
print("Update value in sensors/soil.py SoilMoistureSensor.__init__\n")

print("Reading every 1 second (Ctrl+C to stop)...\n")
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
