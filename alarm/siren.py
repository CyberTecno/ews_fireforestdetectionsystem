"""
AlarmController - controls the relay that switches the siren 12V/24V/220V
120dB with built-in LED flasher.

There is no separate buzzer in the hardware (according to the components list) - so
2 escalation levels are created ONLY from the same relay:

WARNING -> siren pulses slowly (on 0.4s / off 1.6s) as
pre-alarm that can still be "ignored" for a while
CRITICAL -> siren on CONTINUOUSLY (full alert)

Pulsing for level WARNING is run in the background thread so it doesn't
blocks the main loop main.py (which still needs to continue reading sensors & sending
data every few seconds while alarm WARNING is active).
"""
import threading
import time
from alarm.relay import Relay


class AlarmController:
    LEVEL_NONE = "none"
    LEVEL_WARNING = "warning"
    LEVEL_CRITICAL = "critical"

    def __init__(self):
        self.relay = Relay()
        self.current_level = self.LEVEL_NONE
        self._stop_event = threading.Event()
        self._pulse_thread = None

    def _start_pulse(self, on_sec=0.4, off_sec=1.6):
        self._stop_event.clear()

        def _loop():
            while not self._stop_event.is_set():
                self.relay.on()
                if self._stop_event.wait(on_sec):
                    break
                self.relay.off()
                if self._stop_event.wait(off_sec):
                    break
            self.relay.off()

        self._pulse_thread = threading.Thread(target=_loop, daemon=True)
        self._pulse_thread.start()

    def _stop_pulse(self):
        if self._pulse_thread and self._pulse_thread.is_alive():
            self._stop_event.set()
            self._pulse_thread.join(timeout=2)
        self._pulse_thread = None

    def set_level(self, level: str):
        if level == self.current_level:
            return
        self.current_level = level

        # Always stop the old pulsing pattern before setting a new state
        self._stop_pulse()

        if level == self.LEVEL_NONE:
            self.relay.off()
        elif level == self.LEVEL_WARNING:
            self._start_pulse(on_sec=0.4, off_sec=1.6)
        elif level == self.LEVEL_CRITICAL:
            self.relay.on()

    def silence(self):
        self.set_level(self.LEVEL_NONE)


if __name__ == "__main__":
    # Quick manual test: python alarm/siren.py
    ctrl = AlarmController()
    try:
        print("WARNING for 5 seconds (slow pulse)...")
        ctrl.set_level(AlarmController.LEVEL_WARNING)
        time.sleep(5)

        print("CRITICAL for 5 seconds (on continuously)...")
        ctrl.set_level(AlarmController.LEVEL_CRITICAL)
        time.sleep(5)
    finally:
        ctrl.silence()
        print("Alarm is turned off.")
