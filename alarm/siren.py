"""
AlarmController - combines the 12V relay-driven siren and the small buzzer
into a two-tier escalation: WARNING (buzzer beeps) -> CRITICAL (siren on
continuously + buzzer pattern).
"""
from alarm.relay import Relay
from alarm.buzzer import Buzzer


class AlarmController:
    LEVEL_NONE = "none"
    LEVEL_WARNING = "warning"
    LEVEL_CRITICAL = "critical"

    def __init__(self):
        self.relay = Relay()
        self.buzzer = Buzzer()
        self.current_level = self.LEVEL_NONE

    def set_level(self, level):
        if level == self.current_level:
            return
        self.current_level = level
        if level == self.LEVEL_NONE:
            self.relay.off()
            self.buzzer.off()
        elif level == self.LEVEL_WARNING:
            self.relay.off()
            self.buzzer.beep(duration=0.1, pause=0.4, times=3)
        elif level == self.LEVEL_CRITICAL:
            self.relay.on()
            self.buzzer.beep(duration=0.3, pause=0.1, times=5)

    def silence(self):
        self.set_level(self.LEVEL_NONE)
