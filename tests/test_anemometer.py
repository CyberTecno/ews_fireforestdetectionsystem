"""
TEST 6 — RS485 Anemometer (Modbus RTU, via USB-RS485 converter)
Usage: python3 tests/test_anemometer.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("  TEST RS485 Anemometer")
print("=" * 60)
print("Cek dulu USB-RS485 converter terdeteksi: ls /dev/ttyUSB*")
print("Cek juga register Modbus & function code sesuai datasheet unit Anda")
print("(beda merk anemometer biasanya beda register address - lihat config/settings.py)\n")

try:
    from sensors.anemometer import AnemometerSensor
    sensor = AnemometerSensor()
    print("[OK] Anemometer berhasil diinisialisasi.\n")
except Exception as e:
    print(f"[FAIL] Gagal inisialisasi: {e}")
    print("\nKemungkinan penyebab:")
    print("  - Port salah (cek EFWS_ANEM_PORT di .env, biasanya /dev/ttyUSB0)")
    print("  - Wiring A/B (D+/D-) RS485 terbalik")
    print("  - Slave ID Modbus salah (default 1, cek dip-switch/manual unit)")
    sys.exit(1)

print("Membaca tiap 2 detik selama 20 detik (Ctrl+C untuk stop). Tiup sensor untuk lihat perubahan.\n")
try:
    for i in range(10):
        d = sensor.read()
        if d.get("error"):
            print(f"[ERROR] {d['error']}")
        else:
            print(f"wind_speed={d['speed_ms']} m/s")
        time.sleep(2)
except KeyboardInterrupt:
    pass
