"""
IR Flame Sensor -- read via AO (analog) on ​​MCP3008 CH6.

User decision: this sensor is wired ONLY via AO to MCP3008, NOT via
GPIO digital DO -- so no need for an additional RPi.GPIO/level converter for
This sensor simply goes through the same analog route as the MCP3008 sensor
others (get_mcp3008()).

============================================================
CALIBRATION IS MANDATORY BEFORE INSTALLING IN THE FIELD
============================================================
FLAME_AO_THRESHOLD_V in new config/settings.py INITIAL ESTIMATE (half
VREF, 1.65V), YET is measured from your physical unit. How to calibrate:
1. Run this file directly (`python sensors/flame.py`) in condition
normal (no flame) -- note the printed "AO" value.
2. Bring a safe source of small fire (matches/candles, reasonable distance,
DO NOT damage the sensor) -- note the printed "AO" value.
3. Set EFWS_FLAME_AO_THRESHOLD_V in .env to a value between the two.
4. If AO TURUN when there is a fire (common for many IR comparator modules),
let trigger_below=True (default). If it's AO, it's actually NAIK when it's there
fire on your module, call FlameSensor(trigger_below=False).
"""
from config import settings
from sensors.mcp3008 import get_mcp3008


class FlameSensor:
    def __init__(self, channel=None, threshold_v=None, trigger_below=True):
        self.channel     = channel     if channel     is not None else settings.ADC_CHANNEL_FLAME_AO
        self.threshold_v = threshold_v if threshold_v is not None else settings.FLAME_AO_THRESHOLD_V
        self.trigger_below = trigger_below
        self.adc = get_mcp3008()

    def read(self) -> dict:
        voltage = self.adc.read_voltage(self.channel)
        detected = (voltage < self.threshold_v) if self.trigger_below else (voltage > self.threshold_v)
        return {"analog_voltage": voltage, "flame_detected": bool(detected)}


if __name__ == "__main__":
    import time
    sensor = FlameSensor()
    print(f"=== EFWS Flame Sensor Test (CH{sensor.channel}, threshold={sensor.threshold_v}V) ===")
    print("Not yet calibrated -- use the AO numbers below to determine the correct threshold.\n")
    while True:
        r = sensor.read()
        print(f"AO={r['analog_voltage']:.3f}V | flame_detected={r['flame_detected']}")
        time.sleep(1)
