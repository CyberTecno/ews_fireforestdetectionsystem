"""
TEST 7 — Relay 5V + Siren 12V/24V/220V 120dB (with LED flasher)

⚠️ WARNING: This siren is 120dB - VERY LOUD. Make sure you are ready
before carrying out this test (cover your ears / keep your distance / give notice
people around). This test will actually turn on the physical siren.

Usage: python3 tests/test_relay_siren.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alarm.siren import AlarmController

print("=" * 60)
print("TEST Relay + Siren 12V (120dB)")
print("=" * 60)
print("⚠️ The siren will SOUND LOUD on this test.")
confirm = input("Type 'yes' to continue, or Enter to cancel:").strip().lower()
if confirm != "ya":
    print("Cancelled.")
    sys.exit(0)

try:
    ctrl = AlarmController()
    print("\n[OK] Relay initialized.\n")
except Exception as e:
    print(f"[FAIL] Relay initialization failed:{e}")
    sys.exit(1)

try:
    print("Stage 1: Relay ON immediately 2 seconds (check relay 'click' sound + siren turns on)...")
    ctrl.relay.on()
    time.sleep(2)
    ctrl.relay.off()
    print("Stage 1 complete - relay OFF.\n")
    time.sleep(1)

    print("Stage 2: WARNING level for 5 seconds (siren pulses slowly 0.4s ON/1.6s OFF)...")
    ctrl.set_level(AlarmController.LEVEL_WARNING)
    time.sleep(5)

    print("Stage 3: CRITICAL level for 3 seconds (siren ON CONTINUOUSLY)...")
    ctrl.set_level(AlarmController.LEVEL_CRITICAL)
    time.sleep(3)

finally:
    ctrl.silence()
    print("\n[COMPLETE] The alarm is turned off (relay OFF).")
    print("If the siren doesn't sound at all, check:")
    print("- Wiring relay COM/NO to 12V siren line (see docs/Pinout.md)")
    print("- active_low is false (try Relay(active_low=False) on alarm/relay.py)")
    print("- The 12 V source for the siren is not connected/active")
