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


# ─── Flame sensor ────────────────────────────────────────────────
class MockFlameSensor(_MockBase):
    def read(self) -> dict:
        sc       = self._scenario()
        detected = (sc == "critical")
        raw      = 0 if detected else 1   # active-LOW logic
        return {"raw": raw, "flame_detected": detected, "_mock": True, "_scenario": sc}


# ─── BME280 (temp / humidity / pressure) ─────────────────────────
class MockBME280(_MockBase):
    TEMP_BASE = {"normal": 30.0, "warning": 47.0, "critical": 62.0}
    HUM_BASE  = {"normal": 65.0, "warning": 28.0, "critical": 12.0}

    def read(self) -> dict:
        sc = self._scenario()
        # Tambah variasi sinusoidal kecil agar grafik lebih natural
        phase = math.sin(time.time() / 30) * 2
        return {
            "temperature_c":   round(_jitter(self.TEMP_BASE[sc]) + phase, 2),
            "humidity_percent": round(max(0, _jitter(self.HUM_BASE[sc]) - phase), 2),
            "pressure_hpa":    round(_jitter(1013.0, 0.002), 2),
            "_mock": True, "_scenario": sc,
        }


# ─── Soil moisture ───────────────────────────────────────────────
class MockSoilMoisture(_MockBase):
    MOIST_BASE = {"normal": 55.0, "warning": 18.0, "critical": 8.0}

    def read(self) -> dict:
        sc  = self._scenario()
        pct = max(0.0, _jitter(self.MOIST_BASE[sc], 0.06))
        raw = int(26000 - pct / 100 * 14000)
        return {"raw": raw, "moisture_percent": round(pct, 2), "_mock": True, "_scenario": sc}


# ─── Anemometer ──────────────────────────────────────────────────
class MockAnemometer(_MockBase):
    SPEED_BASE = {"normal": 2.5, "warning": 9.0, "critical": 17.0}

    def read(self) -> dict:
        sc    = self._scenario()
        speed = max(0.0, _jitter(self.SPEED_BASE[sc], 0.12))
        return {"speed_ms": round(speed, 2), "_mock": True, "_scenario": sc}


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
