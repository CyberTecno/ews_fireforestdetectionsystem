"""
TEST — SIM Auto-Detector (A7670E vs SIM7600)

Script ini mensimulasikan proses yang terjadi saat EFWS startup di mode hardware:
  1. Scan semua port /dev/ttyUSBx
  2. Kirim AT + ATI ke tiap port
  3. Kenali modul dari fingerprint di respons ATI
  4. Simpan hasil ke .sim_cache untuk boot berikutnya

Usage:
  python3 tests/test_sim_detector.py
  python3 tests/test_sim_detector.py --force   # paksa scan ulang, abaikan cache
"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true", help="Paksa scan ulang, abaikan cache")
args = parser.parse_args()

print("=" * 60)
print("  TEST SIM Auto-Detector")
print("=" * 60)

if settings.RUN_MODE == "mock":
    print("Mode MOCK — tidak ada scan hardware nyata.")
    print("Dalam production (RUN_MODE=hardware), detector akan:")
    print("  1. Scan /dev/ttyUSB* satu per satu")
    print("  2. Kirim AT + ATI ke tiap port")
    print("  3. A7670E/SIM7670E → fingerprint 'A7670E' di ATI → pakai AT+CGNSSPWR untuk GPS")
    print("  4. SIM7600          → fingerprint 'SIM7600' di ATI → pakai AT+CGPS untuk GPS")
    print("  5. Cache port ke .sim_cache untuk boot berikutnya")
    print()
    print("Perintah berguna untuk troubleshoot di Pi:")
    print("  ls /dev/ttyUSB*")
    print("  dmesg | grep ttyUSB")
    print("  python3 -c \"import serial.tools.list_ports; print(list(serial.tools.list_ports.comports()))\"")
    sys.exit(0)

from communication.sim_detector import detect_sim, scan_ports, CACHE_FILE

# Cek cache dulu
if CACHE_FILE.exists() and not args.force:
    print(f"Cache ditemukan: {CACHE_FILE}")
    try:
        cached = json.loads(CACHE_FILE.read_text())
        print(f"  module : {cached.get('module','?').upper()}")
        print(f"  port   : {cached.get('port','?')}")
        print()
        print("Gunakan --force untuk scan ulang (berguna setelah ganti hardware).")
    except Exception as e:
        print(f"  Cache rusak: {e}")
    print()

print("Memulai scan port...")
result = scan_ports()

if result:
    print(f"\n✅ Modul ditemukan: {result['module'].upper()} @ {result['port']}")
    if result["module"] == "a7670e":
        print("   GPS command: AT+CGNSSPWR=1 (A7670E/SIM7670E command set)")
    else:
        print("   GPS command: AT+CGPS=1 (SIM7600 command set)")
    print()
    print("Test GPS dari modul yang terdeteksi...")
    try:
        sim = detect_sim(force_scan=args.force)
        gps = sim.get_gps(timeout=30)
        if gps.get("fix"):
            print(f"✅ GPS fix: lat={gps['lat']}, lon={gps['lon']}")
        else:
            print(f"⚠️  GPS belum fix: {gps.get('reason')} (normal kalau baru power-on / indoor)")
        sim.close()
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("\n❌ Tidak ada modul SIM terdeteksi.")
    print("\nCek:")
    print("  1. ls /dev/ttyUSB* (pastikan adapter USB terdeteksi)")
    print("  2. Modul sudah dinyalakan dan SIM card terpasang")
    print("  3. User pi masuk grup dialout: sudo usermod -aG dialout pi")
    print("  4. Coba port lain: python3 tests/test_a7670e.py --port /dev/ttyUSB1")
