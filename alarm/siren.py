"""
AlarmController - mengendalikan relay yang men-switch sirine 12V/24V/220V
120dB dengan LED flasher bawaan.

Tidak ada buzzer terpisah di hardware (sesuai daftar komponen) - jadi
2 tingkat eskalasi dibuat HANYA dari satu relay yang sama:

  WARNING  -> sirine berdenyut pelan (nyala 0.4s / mati 1.6s) sebagai
              pre-alarm yang masih bisa "diabaikan" sebentar
  CRITICAL -> sirine menyala TERUS-MENERUS (siaga penuh)

Pulsing untuk level WARNING dijalankan di background thread supaya tidak
memblokir loop utama main.py (yang tetap perlu lanjut baca sensor & kirim
data tiap beberapa detik sementara alarm WARNING aktif).
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

        # Selalu hentikan dulu pola pulsing lama sebelum set state baru
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
    # Test cepat manual: python alarm/siren.py
    ctrl = AlarmController()
    try:
        print("WARNING selama 5 detik (denyut pelan)...")
        ctrl.set_level(AlarmController.LEVEL_WARNING)
        time.sleep(5)

        print("CRITICAL selama 5 detik (nyala terus)...")
        ctrl.set_level(AlarmController.LEVEL_CRITICAL)
        time.sleep(5)
    finally:
        ctrl.silence()
        print("Alarm dimatikan.")
