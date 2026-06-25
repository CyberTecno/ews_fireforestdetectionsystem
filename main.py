"""
Early Fire Warning System (EFWS) - Main Orchestrator (Refactored)
=================================================================
Perubahan dari versi sebelumnya:
  • Komunikasi  : MQTT + Telegram → HTTP REST API (JSON POST)
  • Mode testing: RUN_MODE=mock → semua sensor di-simulasi, tidak butuh hardware
  • Database    : kolom per-sensor + offline API queue
  • Logging     : Python logging ke file + console (bukan print campur aduk)
  • Systemd     : siap dijadikan service (lihat docs/DEPLOYMENT.md)
"""
import json
import time
import logging
import traceback
from datetime import datetime, timezone

from config import settings
from database.db_manager import DBManager
from communication.api_publisher import APIPublisher

# ─── Logger setup ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(),                           # stdout → ditangkap systemd/journald
        logging.FileHandler("logs/efws.log", mode="a"),   # file log lokal
    ],
)
logger = logging.getLogger("efws.main")


# ─── Sensor + alarm factory ───────────────────────────────────────
def _load_sensors_and_alarm():
    """Return dict sensor & alarm controller sesuai RUN_MODE."""
    if settings.RUN_MODE == "mock":
        logger.info("Mode: MOCK — sensor disimulasi, tidak ada akses GPIO/I2C")
        from sensors.mock_sensors import (
            MockMQ2, MockMQ135, MockFlameSensor,
            MockBME280, MockSoilMoisture, MockAnemometer,
            MockAlarmController,
        )
        return {
            "mq2":       MockMQ2(),
            "mq135":     MockMQ135(),
            "flame":     MockFlameSensor(),
            "bme280":    MockBME280(),
            "soil":      MockSoilMoisture(),
            "wind":      MockAnemometer(),
        }, MockAlarmController()
    else:
        logger.info("Mode: HARDWARE — mengakses GPIO/I2C nyata")
        from sensors.mq2         import MQ2Sensor
        from sensors.mq135       import MQ135Sensor
        from sensors.flame       import FlameSensor
        from sensors.bme280      import BME280Sensor
        from sensors.soil        import SoilMoistureSensor
        from sensors.anemometer  import AnemometerSensor
        from alarm.siren         import AlarmController
        return {
            "mq2":   MQ2Sensor(),
            "mq135": MQ135Sensor(),
            "flame": FlameSensor(),
            "bme280": BME280Sensor(),
            "soil":  SoilMoistureSensor(),
            "wind":  AnemometerSensor(),
        }, AlarmController()


# ─── Threshold helper ─────────────────────────────────────────────
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


# ─── Main class ───────────────────────────────────────────────────
class EFWS:
    def __init__(self):
        import os
        os.makedirs("logs", exist_ok=True)

        self.thresholds  = _load_thresholds()
        self.sensors, self.alarm = _load_sensors_and_alarm()
        self.api = APIPublisher()
        self.db  = DBManager()

        self._critical_streak  = 0
        self._last_alarm_time  = 0
        self._last_publish     = 0

        logger.info("EFWS initialised. Device: %s | Mode: %s", settings.DEVICE_ID, settings.RUN_MODE)

    # ─── Sensor reads ─────────────────────────────────────────────
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
        t = self.thresholds
        st = {}
        st["mq2"]         = _evaluate_status(data["mq2"].get("ppm"),
                                               t["mq2"]["warning_ppm"], t["mq2"]["critical_ppm"])
        st["mq135"]       = _evaluate_status(data["mq135"].get("ppm"),
                                               t["mq135"]["warning_ppm"], t["mq135"]["critical_ppm"])
        st["flame"]       = "critical" if data["flame"].get("flame_detected") else "normal"
        st["temperature"] = _evaluate_status(data["bme280"].get("temperature_c"),
                                               t["bme280"]["temp_warning_c"], t["bme280"]["temp_critical_c"])
        st["humidity_low"]= _evaluate_status(data["bme280"].get("humidity_percent"),
                                               t["bme280"]["humidity_low_percent"],
                                               t["bme280"]["humidity_low_percent"] * 0.5,
                                               higher_is_worse=False)
        st["soil_dry"]    = _evaluate_status(data["soil"].get("moisture_percent"),
                                               t["soil"]["dry_percent"],
                                               t["soil"]["dry_percent"] * 0.5,
                                               higher_is_worse=False)
        st["wind"]        = _evaluate_status(data["wind"].get("speed_ms"),
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
            "location":   settings.DEVICE_LOCATION,
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
        cfg     = self.thresholds.get("alarm", {})
        required = cfg.get("consecutive_readings_required", 3)
        cooldown = cfg.get("cooldown_seconds", 300)

        self._critical_streak = (self._critical_streak + 1) if level == "critical" else 0

        self.alarm.set_level(level if level != "none" else "none")

        now = time.time()
        if level in ("critical", "warning"):
            if level == "critical" and self._critical_streak < required:
                logger.info("Critical streak %d/%d — menunggu konfirmasi...",
                            self._critical_streak, required)
                return

            if now - self._last_alarm_time < cooldown:
                return   # masih dalam cooldown

            self._last_alarm_time = now
            self.db.log_alarm(level, triggered, payload, reading_id)

            success = self.api.send_alarm(payload, db=self.db)

            logger.warning("ALARM [%s] triggered_by=%s", level.upper(), triggered)

    # ─── Main loop ───────────────────────────────────────────────
    def run(self):
        logger.info("EFWS loop started. Interval baca: %ds | Interval API: %ds",
                    settings.SENSOR_READ_INTERVAL_SEC, settings.API_PUBLISH_INTERVAL_SEC)
        try:
            while True:
                # 1. Baca sensor (selalu, ada/tidak ada sinyal)
                data = self._read_all()

                # 2. Evaluasi status
                level, triggered, statuses = self._evaluate(data)

                # 3. Bangun payload
                payload = self._build_payload(data, statuses, level, triggered)

                # 4. Simpan ke DB lokal (SELALU — tidak peduli ada sinyal atau tidak)
                reading_id = self.db.log_reading(payload)

                # 5. Handle alarm (kirim ke API; jika gagal → masuk queue otomatis)
                self._handle_alarm(level, triggered, payload, reading_id)

                # 6. Kirim ke API sesuai interval
                now = time.time()
                if now - self._last_publish >= settings.API_PUBLISH_INTERVAL_SEC:
                    self._last_publish = now

                    # send_data otomatis masukkan ke queue jika gagal (db diteruskan)
                    self.api.send_data(payload, db=self.db)

                    # Setelah tiap kirim (berhasil/gagal), coba flush queue lama.
                    # flush_queue() akan skip sendiri jika masih offline.
                    self.api.flush_queue(self.db)

                # 7. Log ringkas ke console
                pending = self.db.count_pending_queue()
                offline_tag = f" | 📦 queue={pending}" if pending > 0 else ""
                net_tag = "🔴 OFFLINE" if not self.api.online else "🟢 online "

                logger.info(
                    "READ #%d | %s | alarm=%-8s | mq2=%.0f ppm | mq135=%.0f ppm | "
                    "flame=%s | temp=%.1f°C | hum=%.1f%% | soil=%.1f%% | wind=%.1f m/s%s",
                    reading_id,
                    net_tag,
                    level,
                    data["mq2"].get("ppm", 0),
                    data["mq135"].get("ppm", 0),
                    data["flame"].get("flame_detected", "?"),
                    data["bme280"].get("temperature_c", 0),
                    data["bme280"].get("humidity_percent", 0),
                    data["soil"].get("moisture_percent", 0),
                    data["wind"].get("speed_ms", 0),
                    offline_tag,
                )

                time.sleep(settings.SENSOR_READ_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("EFWS dihentikan oleh user (Ctrl+C).")
        except Exception:
            logger.critical("EFWS crash!\n%s", traceback.format_exc())
        finally:
            self.alarm.silence()
            self.api.close()
            self.db.close()
            logger.info("EFWS shutdown selesai.")


# ─── Entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    efws = EFWS()
    efws.run()
