"""
TEST 7 — Relay 5V + Sirine 12V/24V/220V 120dB (dengan LED flasher)

⚠️  PERINGATAN: Sirine ini 120dB - SANGAT KERAS. Pastikan Anda siap
    sebelum menjalankan test ini (tutup telinga / jaga jarak / beri tahu
    orang sekitar). Test ini akan benar-benar menyalakan sirine fisik.

Usage: python3 tests/test_relay_siren.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alarm.siren import AlarmController

print("=" * 60)
print("  TEST Relay + Sirine 12V (120dB)")
print("=" * 60)
print("⚠️  Sirine akan BERBUNYI KERAS pada test ini.")
confirm = input("Ketik 'ya' untuk lanjut, atau Enter untuk batal: ").strip().lower()
if confirm != "ya":
    print("Dibatalkan.")
    sys.exit(0)

try:
    ctrl = AlarmController()
    print("\n[OK] Relay diinisialisasi.\n")
except Exception as e:
    print(f"[FAIL] Gagal inisialisasi relay: {e}")
    sys.exit(1)

try:
    print("Tahap 1: Relay ON langsung 2 detik (cek bunyi 'klik' relay + sirine menyala)...")
    ctrl.relay.on()
    time.sleep(2)
    ctrl.relay.off()
    print("Tahap 1 selesai - relay OFF.\n")
    time.sleep(1)

    print("Tahap 2: Level WARNING selama 5 detik (sirine berdenyut pelan 0.4s ON/1.6s OFF)...")
    ctrl.set_level(AlarmController.LEVEL_WARNING)
    time.sleep(5)

    print("Tahap 3: Level CRITICAL selama 3 detik (sirine menyala TERUS)...")
    ctrl.set_level(AlarmController.LEVEL_CRITICAL)
    time.sleep(3)

finally:
    ctrl.silence()
    print("\n[SELESAI] Alarm dimatikan (relay OFF).")
    print("Kalau sirine tidak bunyi sama sekali, cek:")
    print("  - Wiring relay COM/NO ke jalur 12V sirine (lihat docs/Pinout.md)")
    print("  - active_low salah (coba Relay(active_low=False) di alarm/relay.py)")
    print("  - Sumber 12V untuk sirine belum tersambung/aktif")
