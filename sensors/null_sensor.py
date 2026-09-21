"""
NullSensor — fallback if physical sensor FAILS is initialized
(not installed, driver missing, port/bus not found at startup).

Goal: so that the EFWS can still run even if one of the sensors (whatever it is)
nothing, without having to change the payload builder / threshold evaluator code
in main.py at all.

IMPORTANT data type question: all numeric fields under ALWAYS are Python values
`None` (not the string "None", not the error message). `None` -> JSON `null` and
SQLite `NULL` automatically, so column REAL/float never receives
text. Error message /alasan why the sensor is not read ONLY is stored in the key
separate `"error"` (string type), NEVER mixed into the number field.

SENSOR_SCHEMAS lists what fields should be in each
sensor (exactly the same as the original return sensor form when successful), let
NullSensor.read() always returns an identical shape --
complete with all keys, only the contents are null -- fine accessed via
`.get(...)` or directly `dict[...]`.
"""

SENSOR_SCHEMAS = {
    "mq2":      {"voltage": None, "ppm": None},
    "mq135":    {"voltage": None, "ppm": None},
    "bme280":   {"temperature_c": None, "humidity_percent": None, "pressure_hpa": None},
    "pressure": {"current_ma": None, "depth_m": None, "pressure_bar": None, "fault_open_loop": None},
    "soil": {
        "surface": {"raw": None, "moisture_percent": None},
        "deep":    {"raw": None, "moisture_percent": None},
    },
    "wind":    {"speed_ms": None},
    "wind_dir": {"direction_code": None, "direction_abbr": None, "direction_name": None},
    "flame":    {"analog_voltage": None, "flame_detected": None},
    "rainfall": {"rainfall_total_mm": None, "rainfall_last_hour_mm": None,
                 "tip_counter": None, "working_time_hours": None},
    "battery": {"voltage": None, "percent": None},
}


class NullSensor:
    def __init__(self, name: str, reason: str):
        self.name = name
        self.reason = reason
        self._fields = SENSOR_SCHEMAS.get(name, {})

    def read(self) -> dict:
        # A shallow copy is sufficient: all field contents are None (immutable) or
        # nested dict which also only contains None, so it's safe not to be mutated.
        result = dict(self._fields)
        result["error"] = (
            f"sensor '{self.name}' unread/not installed: {self.reason}"
        )
        return result


class NullAlarmController:
    """Fallback if relay/siren initialization fails — the local alarm becomes a no-op,
but the level status is still recorded, so the operator knows."""

    current_level = "none"

    def __init__(self, reason: str):
        self.reason = reason

    def set_level(self, level: str):
        self.current_level = level

    def silence(self):
        self.current_level = "none"
