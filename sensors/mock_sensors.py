"""
Mock sensor layer untuk testing TANPA hardware.
Menghasilkan data realistis dengan variasi acak dan skenario bahaya terjadwal,
sehingga alarm logic, database, dan API publisher bisa diuji penuh di desktop/Pi.

Aktif saat EFWS_RUN_MODE=mock (default).
"""
import math
import random
import time


# ─── Helper ──────────────────────────────────────────────────────
def _jitter(value: float, pct: float = 0.05) -> float:
    """Tambah noise acak ±pct% ke nilai."""
    return round(value * (1 + random.uniform(-pct, pct)), 3)


# ─── Base mock ────────────────────────────────────────────────────
class _MockBase:
    """Semua mock sensor turunan dari sini; _scenario() bisa override."""

    def _scenario(self) -> str:
        """Pilih skenario berdasarkan waktu (siklus 2 menit untuk demo)."""
        t = time.time() % 120          # siklus 120 detik
        if t < 80:
            return "normal"
        elif t < 100:
            return "warning"
        else:
            return "critical"


# ─── MQ-2 (smoke / LPG) ──────────────────────────────────────────
class MockMQ2(_MockBase):
    BASELINES = {"normal": 80, "warning": 450, "critical": 1200}

    def read(self) -> dict:
        sc  = self._scenario()
        ppm = _jitter(self.BASELINES[sc], 0.08)
        v   = round(0.4 + ppm / 1000 * 3.6, 3)   # voltase perkiraan
        return {"voltage": v, "ppm": max(0.0, ppm), "_mock": True, "_scenario": sc}


# ─── MQ-135 (air quality) ────────────────────────────────────────
class MockMQ135(_MockBase):
    BASELINES = {"normal": 120, "warning": 500, "critical": 1100}

    def read(self) -> dict:
        sc  = self._scenario()
        ppm = _jitter(self.BASELINES[sc], 0.08)
        v   = round(0.3 + ppm / 1000 * 3.3, 3)
        return {"voltage": v, "ppm": max(0.0, ppm), "_mock": True, "_scenario": sc}


# ─── BME280 (temp / humidity / pressure ambient) ─────────────────
class MockBME280(_MockBase):
    TEMP_BASE = {"normal": 30.0, "warning": 47.0, "critical": 62.0}
    HUM_BASE  = {"normal": 65.0, "warning": 28.0, "critical": 12.0}

    def read(self) -> dict:
        sc = self._scenario()
        phase = math.sin(time.time() / 30) * 2   # variasi sinusoidal kecil
        return {
            "temperature_c":    round(_jitter(self.TEMP_BASE[sc]) + phase, 2),
            "humidity_percent": round(max(0, _jitter(self.HUM_BASE[sc]) - phase), 2),
            "pressure_hpa":     round(_jitter(1013.0, 0.002), 2),
            "_mock": True, "_scenario": sc,
        }


# ─── Submersible Pressure Sensor (water level, loop 4-20mA) ──────
class MockPressureWater(_MockBase):
    MA_BASE = {"normal": 14.0, "warning": 7.0, "critical": 4.5}  # makin rendah = makin dangkal/kosong
    RANGE_M = 5.0

    def read(self) -> dict:
        sc   = self._scenario()
        ma   = max(4.0, min(20.0, _jitter(self.MA_BASE[sc], 0.05)))
        pct  = max(0.0, min(1.0, (ma - 4.0) / 16.0))
        depth = round(pct * self.RANGE_M, 3)
        return {
            "current_ma":     round(ma, 3),
            "depth_m":        depth,
            "pressure_bar":   round(depth * 0.0980665, 4),
            "fault_open_loop": False,
            "_mock": True, "_scenario": sc,
        }


# ─── Soil moisture ───────────────────────────────────────────────
class MockSoilMoisture(_MockBase):
    SURFACE_BASE = {"normal": 55.0, "warning": 18.0, "critical":  8.0}
    DEEP_BASE    = {"normal": 65.0, "warning": 25.0, "critical": 12.0}

    def read(self) -> dict:
        sc          = self._scenario()
        surface_pct = max(0.0, _jitter(self.SURFACE_BASE[sc], 0.06))
        deep_pct    = max(0.0, _jitter(self.DEEP_BASE[sc],    0.06))
        return {
            "surface": {"raw": int(900 - surface_pct / 100 * 520), "moisture_percent": round(surface_pct, 2), "_mock": True},
            "deep":    {"raw": int(900 - deep_pct    / 100 * 520), "moisture_percent": round(deep_pct,    2), "_mock": True},
        }


# ─── Anemometer ──────────────────────────────────────────────────
class MockAnemometer(_MockBase):
    SPEED_BASE = {"normal": 2.5, "warning": 9.0, "critical": 17.0}

    def read(self) -> dict:
        sc    = self._scenario()
        speed = max(0.0, _jitter(self.SPEED_BASE[sc], 0.12))
        return {"speed_ms": round(speed, 2), "_mock": True, "_scenario": sc}


# ─── Wind Direction -- UART, muter searah jarum jam tiap ~10 detik ─
class MockWindDirection(_MockBase):
    _COMPASS = {
        1: ("N", "Utara"), 2: ("NE", "Timur Laut"), 3: ("E", "Timur"),
        4: ("SE", "Tenggara"), 5: ("S", "Selatan"), 6: ("SW", "Barat Daya"),
        7: ("W", "Barat"), 8: ("NW", "Barat Laut"),
    }

    def read(self) -> dict:
        code = int((time.time() // 10) % 8) + 1
        abbr, name_id = self._COMPASS[code]
        return {
            "direction_code": code,
            "direction_abbr": abbr,
            "direction_name": f"{name_id} ({abbr})",
            "_mock": True,
        }


# ─── Battery — Modul Sensor Tegangan DC 0-25V ────────────────────
class MockBattery(_MockBase):
    PCT_BASE = {"normal": 85.0, "warning": 42.0, "critical": 15.0}

    def read(self) -> dict:
        sc  = self._scenario()
        pct = max(0.0, min(100.0, _jitter(self.PCT_BASE[sc], 0.04)))
        v   = round(9.0 + pct / 100 * 3.6, 2)
        return {"voltage": v, "percent": round(pct, 1), "_mock": True, "_scenario": sc}


class MockFlame(_MockBase):
    def read(self) -> dict:
        sc = self._scenario()
        # "critical" scenario sesekali memicu deteksi api, supaya jalur flame
        # bisa ikut teruji tanpa perlu hardware.
        detected = sc == "critical" and random.random() < 0.3
        voltage = _jitter(0.8, 0.1) if detected else _jitter(2.8, 0.1)
        return {"analog_voltage": voltage, "flame_detected": detected, "_mock": True}


class MockRainfall(_MockBase):
    def __init__(self):
        self._cumulative = 0.0

    def read(self) -> dict:
        sc = self._scenario()
        rate = {"normal": 0.0, "warning": 0.4, "critical": 2.5}[sc]
        increment = max(0.0, _jitter(rate, 0.3)) if rate else 0.0
        self._cumulative += increment
        return {
            "rainfall_total_mm": round(self._cumulative, 4),
            "rainfall_last_hour_mm": round(increment, 4),
            "tip_counter": int(self._cumulative / 0.2794),  # 1 tip standar = 0.2794mm
            "working_time_hours": round(time.time() / 3600 % 1000, 2),
            "_mock": True,
        }

# ─── Mock Alarm (no GPIO) ────────────────────────────────────────
class MockAlarmController:
    """Cetak level alarm ke console; tidak sentuh GPIO."""

    LEVELS = {"none": "🟢", "warning": "🟡", "critical": "🔴"}
    current_level = "none"

    def set_level(self, level: str):
        if level == self.current_level:
            return
        self.current_level = level
        icon = self.LEVELS.get(level, "⚪")
        print(f"  [ALARM] {icon}  Level → {level.upper()}")

    def silence(self):
        self.set_level("none")

