"""
Early Fire Warning System (EFWS) - Main Orchestrator
=====================================================
Perubahan terbaru:
  • GPS: koordinat diambil dari SIM7600E secara real-time (bukan hardcode di .env)
  • GPS di-refresh tiap GPS_UPDATE_INTERVAL_SEC (default 5 menit)
  • Fallback ke koordinat .env jika GPS tidak dapat fix
"""
import json
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime, timezone

from config import settings
from database.db_manager import DBManager
from communication.api_publisher import APIPublisher

# ─── Buat folder yang dibutuhkan sebelum logger ──────────────────
Path(settings.LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)

# ─── Logger setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.LOG_PATH, mode="a"),
    ],
)
logger = logging.getLogger("efws.main")


# ─── SIM7600 factory ─────────────────────────────────────────────
def _load_sim7600():
    if settings.RUN_MODE == "mock":
        from communication.sim7600 import MockSIM7600
        return MockSIM7600()
    else:
        from communication.sim7600 import SIM7600
        try:
            return SIM7600()
        except Exception as e:
            logger.warning("SIM7600 tidak bisa diinisialisasi: %s — GPS dinonaktifkan.", e)
            return None


# ─── Sensor + alarm factory ──────────────────────────────────────
def _load_sensors_and_alarm():
    if settings.RUN_MODE == "mock":
        logger.info("Mode: MOCK — sensor disimulasi, tidak ada akses GPIO/I2C")
        from sensors.mock_sensors import (
            MockMQ2, MockMQ135, MockFlameSensor,
            MockBME280, MockSoilMoisture, MockAnemometer,
            MockAlarmController,
        )
        return {
            "mq2":    MockMQ2(),
            "mq135":  MockMQ135(),
            "flame":  MockFlameSensor(),
            "bme280": MockBME280(),
            "soil":   MockSoilMoisture(),
            "wind":   MockAnemometer(),
        }, MockAlarmController()
    else:
        logger.info("Mode: HARDWARE — mengakses GPIO/I2C nyata")
        from sensors.mq2        import MQ2Sensor
        from sensors.mq135      import MQ135Sensor
        from sensors.flame      import FlameSensor
        from sensors.bme280     import BME280Sensor
        from sensors.soil       import SoilMoistureSensor
        from sensors.anemometer import AnemometerSensor
        from alarm.siren        import AlarmController
        return {
            "mq2":    MQ2Sensor(),
            "mq135":  MQ135Sensor(),
            "flame":  FlameSensor(),
            "bme280": BME280Sensor(),
            "soil":   SoilMoistureSensor(),
            "wind":   AnemometerSensor(),
        }, AlarmController()


# ─── Threshold helpers ───────────────────────────────────────────
def _load_thresholds() -> dict:
    with open(settings.THRESHOLDS_PATH) as f:
        return json.load(f)


def _evaluate_status(value, warning, critical, higher_is_worse=True) -> str:
    if value is None:
        return "unknown"
    if higher_is_worse:
        if value >= critical: return "critical"
        if value >= warning:  return "warning"
        return "normal"
    else:
        if value <= critical: return "critical"
        if value <= warning:  return "warning"
        return "normal"


# ─── Main class ──────────────────────────────────────────────────
class EFWS:
    # Interval refresh koordinat GPS (detik)
    GPS_UPDATE_INTERVAL = int(settings._opt("EFWS_GPS_INTERVAL", "300"))  # default 5 menit

    def __init__(self):
        self.thresholds           = _load_thresholds()
        self.sensors, self.alarm  = _load_sensors_and_alarm()
        self.api                  = APIPublisher()
        self.db                   = DBManager()
        self.sim                  = _load_sim7600()

        self._critical_streak  = 0
        self._last_alarm_time  = 0.0
        self._last_publish     = 0.0
        self._last_gps_update  = 0.0

        # Lokasi: mulai dari .env sebagai fallback
        self._location = {
            "lat":    settings.DEVICE_LOCATION["lat"],
            "lon":    settings.DEVICE_LOCATION["lon"],
            "source": "config",         # akan berubah ke "gps" setelah fix
            "fix":    False,
        }

        logger.info("EFWS initialised. Device: %s | Mode: %s", settings.DEVICE_ID, settings.RUN_MODE)
        # Ambil GPS langsung saat startup
        self._update_gps()

    # ─── GPS refresh ─────────────────────────────────────────────
    def _update_gps(self):
        """Ambil koordinat real dari SIM7600E GPS. Non-blocking jika gagal."""
        if self.sim is None:
            return

        logger.info("📡 Meminta data GPS dari SIM7600E...")
        try:
            result = self.sim.get_gps(timeout=settings._int("EFWS_GPS_TIMEOUT", 90))
        except Exception as e:
            logger.warning("GPS error: %s", e)
            return

        self._last_gps_update = time.time()

        if result.get("fix"):
            self._location = {
                "lat":         result["lat"],
                "lon":         result["lon"],
                "altitude_m":  result.get("altitude_m"),
                "speed_kmh":   result.get("speed_kmh"),
                "time_utc":    result.get("time_utc"),
                "date_utc":    result.get("date_utc"),
                "source":      "gps",
                "fix":         True,
            }
            logger.info(
                "📍 GPS fix: lat=%.6f, lon=%.6f, alt=%.1fm",
                result["lat"], result["lon"], result.get("altitude_m") or 0,
            )
        else:
            logger.warning("📍 GPS tidak fix: %s — pakai koordinat terakhir.", result.get("reason"))
            self._location["fix"] = False
            self._location["source"] = "fallback"

    # ─── Sensor reads ────────────────────────────────────────────
    def _read_all(self) -> dict:
        data = {}
        for key, sensor in self.sensors.items():
            try:
                data[key] = sensor.read()
            except Exception as e:
                logger.error("Sensor '%s' read error: %s", key, e)
                data[key] = {"error": str(e)}
        return data

    # ─── Evaluate ────────────────────────────────────────────────
    def _evaluate(self, data: dict):
        t  = self.thresholds
        st = {}
        st["mq2"]          = _evaluate_status(data["mq2"].get("ppm"),
                                               t["mq2"]["warning_ppm"], t["mq2"]["critical_ppm"])
        st["mq135"]        = _evaluate_status(data["mq135"].get("ppm"),
                                               t["mq135"]["warning_ppm"], t["mq135"]["critical_ppm"])
        st["flame"]        = "critical" if data["flame"].get("flame_detected") else "normal"
        st["temperature"]  = _evaluate_status(data["bme280"].get("temperature_c"),
                                               t["bme280"]["temp_warning_c"], t["bme280"]["temp_critical_c"])
        st["humidity_low"] = _evaluate_status(data["bme280"].get("humidity_percent"),
                                               t["bme280"]["humidity_low_percent"],
                                               t["bme280"]["humidity_low_percent"] * 0.5,
                                               higher_is_worse=False)
        st["soil_dry"]     = _evaluate_status(data["soil"].get("moisture_percent"),
                                               t["soil"]["dry_percent"],
                                               t["soil"]["dry_percent"] * 0.5,
                                               higher_is_worse=False)
        st["wind"]         = _evaluate_status(data["wind"].get("speed_ms"),
                                               t["wind"]["high_speed_ms"], t["wind"]["extreme_speed_ms"])

        level, triggered = "none", []
        for k, s in st.items():
            if s == "critical":
                level = "critical"; triggered.append(k)
            elif s == "warning" and level != "critical":
                level = "warning"; triggered.append(k)

        return level, triggered, st

    # ─── Payload builder ─────────────────────────────────────────
    def _build_payload(self, data, statuses, level, triggered) -> dict:
        return {
            "device_id":  settings.DEVICE_ID,
            "location":   self._location,       # ← koordinat real GPS, bukan hardcode
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "mode":       settings.RUN_MODE,
            "sensors":    data,
            "statuses":   statuses,
            "alarm": {
                "active":       level != "none",
                "level":        level,
                "triggered_by": triggered,
            },
        }

    # ─── Alarm handler ───────────────────────────────────────────
    def _handle_alarm(self, level, triggered, payload, reading_id):
        cfg      = self.thresholds.get("alarm", {})
        required = cfg.get("consecutive_readings_required", 3)
        cooldown = cfg.get("cooldown_seconds", 300)

        self._critical_streak = (self._critical_streak + 1) if level == "critical" else 0
        self.alarm.set_level(level)

        now = time.time()
        if level in ("critical", "warning"):
            if level == "critical" and self._critical_streak < required:
                logger.info("Critical streak %d/%d — menunggu konfirmasi...",
                            self._critical_streak, required)
                return
            if now - self._last_alarm_time < cooldown:
                return

            self._last_alarm_time = now
            self.db.log_alarm(level, triggered, payload, reading_id)
            self.api.send_alarm(payload, db=self.db)
            logger.warning("ALARM [%s] triggered_by=%s", level.upper(), triggered)

    # ─── Main loop ───────────────────────────────────────────────
    def run(self):
        logger.info("EFWS loop started. Baca: %ds | Publish: %ds | GPS refresh: %ds",
                    settings.SENSOR_READ_INTERVAL_SEC,
                    settings.API_PUBLISH_INTERVAL_SEC,
                    self.GPS_UPDATE_INTERVAL)
        try:
            while True:
                now = time.time()

                # 0. Refresh GPS secara berkala
                if now - self._last_gps_update >= self.GPS_UPDATE_INTERVAL:
                    self._update_gps()

                # 1. Baca sensor
                data = self._read_all()

                # 2. Evaluasi
                level, triggered, statuses = self._evaluate(data)

                # 3. Build payload
                payload = self._build_payload(data, statuses, level, triggered)

                # 4. Simpan ke DB (selalu, meskipun offline)
                reading_id = self.db.log_reading(payload)

                # 5. Handle alarm
                self._handle_alarm(level, triggered, payload, reading_id)

                # 6. Publish ke API sesuai interval
                if now - self._last_publish >= settings.API_PUBLISH_INTERVAL_SEC:
                    self._last_publish = now
                    self.api.send_data(payload, db=self.db)
                    self.api.flush_queue(self.db)

                # 7. Log ringkas
                pending   = self.db.count_pending_queue()
                queue_tag = f" | 📦 queue={pending}" if pending > 0 else ""
                net_tag   = "🔴 OFFLINE" if not self.api.online else "🟢 online "
                gps_tag   = f"📍{self._location['lat']:.4f},{self._location['lon']:.4f}" \
                            f"({'GPS' if self._location.get('fix') else 'fallback'})"

                logger.info(
                    "READ #%d | %s | %s | alarm=%-8s | "
                    "mq2=%.0fppm mq135=%.0fppm flame=%s | "
                    "temp=%.1f°C hum=%.1f%% soil=%.1f%% wind=%.1fm/s%s",
                    reading_id, net_tag, gps_tag, level,
                    data["mq2"].get("ppm", 0),
                    data["mq135"].get("ppm", 0),
                    data["flame"].get("flame_detected", "?"),
                    data["bme280"].get("temperature_c", 0),
                    data["bme280"].get("humidity_percent", 0),
                    data["soil"].get("moisture_percent", 0),
                    data["wind"].get("speed_ms", 0),
                    queue_tag,
                )

                time.sleep(settings.SENSOR_READ_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("EFWS dihentikan oleh user (Ctrl+C).")
        except Exception:
            logger.critical("EFWS crash!\n%s", traceback.format_exc())
        finally:
            self.alarm.silence()
            self.api.close()
            if self.sim:
                self.sim.close()
            self.db.close()
            logger.info("EFWS shutdown selesai.")


if __name__ == "__main__":
    efws = EFWS()
    efws.run()
