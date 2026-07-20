"""
Early Fire Warning System (EFWS) - Main Orchestrator

ARSITEKTUR BARU (lihat penjelasan lengkap di chat sebelum file ini dibuat):
  - Siklus baca sensor (default 3 menit) HANYA mengevaluasi threshold.
    Tidak ada penyimpanan ke SQLite dan tidak ada pengiriman kalau semua
    nilai di bawah threshold ("nothing happens").
  - Kalau ADA nilai yang melewati threshold -> "emergency upload": kirim
    Location + Telemetry + Heartbeat sekaligus (endpoint 1,2,3).
  - Endpoint 4 (/sensors/commands/ack) HANYA jalan kalau response
    Heartbeat membawa 'commands' -- event-driven, di luar scheduler.
  - Threshold aktif = remote config (dari response Telemetry) di-merge
    per-field dengan hardcoded lokal (config/threshold_resolver.py).
  - Retry offline queue (tiap 2 menit) berjalan di thread terpisah,
    independen dari siklus baca sensor (3 menit).
"""
import json
import time
import logging
import threading
import subprocess
import traceback
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import settings
from config.threshold_resolver import resolve_active_thresholds
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


# ─── smokeLevel calculator ────────────────────────────────────────
def _calc_smoke_level(mq2_ppm: float, mq135_ppm: float) -> float:
    """
    Gabungkan MQ-2 dan MQ-135 menjadi satu persentase 0-100%.
    Formula: (mq2/MQ2_CRIT * W_MQ2 + mq135/MQ135_CRIT * W_MQ135) * 100
    """
    n2   = min(mq2_ppm   / settings.SMOKE_MQ2_CRIT_PPM,   1.5)
    n135 = min(mq135_ppm / settings.SMOKE_MQ135_CRIT_PPM, 1.5)
    raw  = (n2 * settings.SMOKE_WEIGHT_MQ2 + n135 * settings.SMOKE_WEIGHT_MQ135) * 100
    return round(min(raw, 100.0), 2)


# ─── SIM factory (auto-detect A7670E atau SIM7600) ───────────────
def _load_sim():
    from communication.sim_detector import detect_sim
    try:
        sim = detect_sim()
        logger.info("SIM modul: %s @ %s", sim.module.upper(), sim.port)
        return sim
    except Exception as e:
        logger.warning("SIM tidak bisa diinisialisasi: %s — GPS dinonaktifkan.", e)
        return None


# ─── Sensor + alarm factory ──────────────────────────────────────
def _load_sensors_and_alarm():
    if settings.RUN_MODE == "mock":
        logger.info("Mode: MOCK — sensor disimulasi, tidak ada akses GPIO/I2C")
        from sensors.mock_sensors import (
            MockMQ2, MockMQ135, MockBME280, MockPressureWater,
            MockSoilMoisture, MockAnemometer, MockBattery,
            MockAlarmController,
        )
        return {
            "mq2":      MockMQ2(),
            "mq135":    MockMQ135(),
            "bme280":   MockBME280(),
            "pressure": MockPressureWater(),
            "soil":     MockSoilMoisture(),
            "wind":     MockAnemometer(),
            "battery":  MockBattery(),
        }, MockAlarmController()
    else:
        logger.info("Mode: HARDWARE — mengakses GPIO/SPI/I2C nyata")
        from sensors.mq2        import MQ2Sensor
        from sensors.mq135      import MQ135Sensor
        from sensors.bme280     import BME280Sensor
        from sensors.pressure   import PressureWaterSensor
        from sensors.soil       import SoilMoistureSensor
        from sensors.anemometer import AnemometerSensor
        from sensors.battery    import BatterySensor
        from alarm.siren        import AlarmController
        return {
            "mq2":      MQ2Sensor(),
            "mq135":    MQ135Sensor(),
            "bme280":   BME280Sensor(),
            "pressure": PressureWaterSensor(),
            "soil":     SoilMoistureSensor(),
            "wind":     AnemometerSensor(),
            "battery":  BatterySensor(),
        }, AlarmController()


# ─── Threshold helpers ───────────────────────────────────────────
def _load_hardcoded_thresholds() -> dict:
    with open(settings.THRESHOLDS_PATH) as f:
        return json.load(f)


def _exceeds(value, danger, lower_is_worse) -> bool:
    """True kalau value melewati danger threshold. None value -> selalu False (unknown, bukan alarm)."""
    if value is None or danger is None:
        return False
    return (value <= danger) if lower_is_worse else (value >= danger)


# ─── Main class ──────────────────────────────────────────────────
class EFWS:
    def __init__(self):
        self.hardcoded_thresholds = _load_hardcoded_thresholds()
        self.sensors, self.alarm  = _load_sensors_and_alarm()
        self.api                  = APIPublisher()
        self.db                   = DBManager()
        self.sim                  = _load_sim()   # auto-detect A7670E atau SIM7600

        self._critical_streak = 0
        self._stop_flag = threading.Event()

        self._location = {
            "lat":    settings.DEVICE_LOCATION["lat"],
            "lon":    settings.DEVICE_LOCATION["lon"],
            "source": "config",
            "fix":    False,
        }

        logger.info("EFWS initialised. Device: %s | Mode: %s | SIM: %s",
                    settings.DEVICE_ID, settings.RUN_MODE,
                    self.sim.module.upper() if self.sim else "none")

        # Thread terpisah khusus retry offline queue tiap
        # EFWS_CONNECTIVITY_CHECK_SEC (2 menit) -- SENGAJA independen dari
        # siklus baca sensor (3 menit), supaya requirement "retry every
        # 2 minutes" tetap terpenuhi persis walau siklus baca lebih lambat.
        self._flush_thread = threading.Thread(target=self._flush_queue_loop, daemon=True)
        self._flush_thread.start()

    # ─── Background: retry offline queue, independen dari siklus baca ──
    def _flush_queue_loop(self):
        interval = settings.EFWS_CONNECTIVITY_CHECK_SEC
        while not self._stop_flag.is_set():
            try:
                self.api.flush_queue(self.db)
            except Exception:
                logger.error("Flush queue thread error:\n%s", traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── GPS refresh ─────────────────────────────────────────────
    def _update_gps(self):
        if self.sim is None:
            return
        logger.info("📡 Meminta data GPS dari %s...",
                    self.sim.module.upper() if hasattr(self.sim, "module") else "SIM")
        try:
            result = self.sim.get_gps(timeout=settings._int("EFWS_GPS_TIMEOUT", 90))
        except Exception as e:
            logger.warning("GPS error: %s", e)
            return

        if result.get("fix"):
            self._location = {
                "lat":        result["lat"],
                "lon":        result["lon"],
                "altitude_m": result.get("altitude_m"),
                "source":     "gps",
                "fix":        True,
            }
            logger.info("📍 GPS fix: lat=%.6f, lon=%.6f", result["lat"], result["lon"])
        else:
            logger.warning("📍 GPS tidak fix: %s", result.get("reason"))
            self._location["fix"]    = False
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

    # ─── Evaluate (single-tier: exceeded / not, sesuai kontrak API) ──
    def _evaluate(self, data: dict):
        """
        Threshold aktif = merge remote config (dari response telemetry
        terakhir) dengan hardcoded lokal, per-field (lihat threshold_resolver).
        Return: (any_triggered: bool, triggered: list[str], smoke_pct: float)
        """
        t = resolve_active_thresholds(self.hardcoded_thresholds, self.api.remote_config)

        smoke_pct = _calc_smoke_level(
            data["mq2"].get("ppm", 0),
            data["mq135"].get("ppm", 0),
        )

        surface = data["soil"].get("surface", {}).get("moisture_percent")
        deep    = data["soil"].get("deep", {}).get("moisture_percent")

        checks = {
            "smoke":       _exceeds(smoke_pct, t["smokeDangerThreshold"], lower_is_worse=False),
            "temperature": _exceeds(data["bme280"].get("temperature_c"), t["temperatureDangerThreshold"], lower_is_worse=False),
            "humidity":    _exceeds(data["bme280"].get("humidity_percent"), t["humidityDangerThreshold"], lower_is_worse=True),
            "water":       _exceeds(data["pressure"].get("depth_m"), t["waterDangerThreshold"], lower_is_worse=True),
            "soil_surface": _exceeds(surface, t["soilMoistureDangerThreshold"]["surface"], lower_is_worse=True),
            "soil_deep":    _exceeds(deep,    t["soilMoistureDangerThreshold"]["deep"],    lower_is_worse=True),
            "wind":        _exceeds(data["wind"].get("speed_ms"), t["windDangerThreshold"], lower_is_worse=False),
        }

        triggered = [k for k, v in checks.items() if v]
        return (len(triggered) > 0), triggered, smoke_pct

    # ─── Payload builders (kontrak backend, endpoint 1/2/3/4) ────
    def _build_location_payload(self) -> dict:
        return {
            "deviceId":    settings.DEVICE_ID,
            "deviceToken": settings.DEVICE_TOKEN,
            "latitude":    self._location["lat"],
            "longitude":   self._location["lon"],
        }

    def _build_telemetry_payload(self, data, smoke_pct) -> dict:
        soil     = data.get("soil", {})
        bme      = data.get("bme280", {})
        wind     = data.get("wind", {})
        pressure = data.get("pressure", {})
        battery  = data.get("battery", {})

        timestamp = (
            datetime.now(ZoneInfo("Asia/Jakarta"))
            .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z"
        )

        return {
            "deviceId": settings.DEVICE_ID,
            "deviceToken": settings.DEVICE_TOKEN,
            "telemetry": [
                {
                    "timestamp": timestamp,
                    "waterLevel": pressure.get("depth_m"),
                    "smokeLevel": smoke_pct,
                    "temp": bme.get("temperature_c"),
                    "humidity": bme.get("humidity_percent"),
                    "soilMoisture": {
                        "surface": soil.get("surface", {}).get("moisture_percent"),
                        "deep":    soil.get("deep", {}).get("moisture_percent"),
                    },
                    "windSpeed": wind.get("speed_ms"),
                    "batteryLevel": battery.get("percent"),
                    "flameDetected": False,
                }
            ],
        }

    def _build_heartbeat_payload(self, data) -> dict:
        return {
            "deviceId":     settings.DEVICE_ID,
            "deviceToken":  settings.DEVICE_TOKEN,
            "batteryLevel": data.get("battery", {}).get("percent"),
        }

    def _build_ack_payload(self, command_id: str, status: str, error: str = "") -> dict:
        return {
            "deviceId":    settings.DEVICE_ID,
            "deviceToken": settings.DEVICE_TOKEN,
            "commandId":   command_id,
            "status":      status,
            "error":       error,
        }

    # ─── Alarm handler LOKAL (sirine real-time, independen dari backend) ──
    def _handle_alarm(self, any_triggered: bool, triggered: list):
        cfg      = self.hardcoded_thresholds.get("alarm", {})
        required = cfg.get("consecutive_readings_required", 3)

        self._critical_streak = (self._critical_streak + 1) if any_triggered else 0
        self.alarm.set_level("critical" if any_triggered else "normal")

        if any_triggered and self._critical_streak >= required:
            logger.warning("🔴 ALARM (lokal, sirine menyala) — %d bacaan berturut: %s",
                           self._critical_streak, triggered)

    # ─── Endpoint 4: eksekusi command dari heartbeat, lalu ACK ───
    def _process_commands(self, commands: list):
        for cmd in commands:
            command_id = cmd.get("id", "")
            command_name = cmd.get("command", "")
            logger.warning("📥 Command diterima dari backend: id=%s command=%s", command_id, command_name)

            handler = self._COMMAND_HANDLERS.get(command_name)
            if handler is None:
                logger.error("Command '%s' tidak dikenal.", command_name)
                ack = self._build_ack_payload(command_id, "FAILED", f"Unknown command: {command_name}")
                self.api.send_command_ack(ack, db=self.db)
                continue

            try:
                handler(self)
                ack = self._build_ack_payload(command_id, "SUCCESS")
            except Exception as e:
                logger.error("Command '%s' gagal: %s", command_name, e)
                ack = self._build_ack_payload(command_id, "FAILED", str(e))

            self.api.send_command_ack(ack, db=self.db)

    def _cmd_reboot(self):
        """
        CATATAN ARSITEKTUR PENTING:
        Spec minta "execute -> wait until complete -> baru kirim ACK". Untuk
        command Reboot ini SECARA TEKNIS TIDAK MUNGKIN dipenuhi literal:
        begitu `systemctl restart efws.service` dieksekusi, proses Python
        yang sedang jalan (proses ini sendiri) akan dibunuh SEBELUM sempat
        mengirim ACK "setelah selesai".

        Solusi yang dipakai: dispatch restart lewat proses child yang
        DETACHED dengan delay singkat (EFWS_REBOOT_DELAY_SEC, default 5s),
        lalu anggap "berhasil" begitu restart itu terjadwal (bukan setelah
        restart benar-benar selesai) -- ACK SUCCESS dikirim oleh caller
        (_process_commands) SEGERA setelah fungsi ini return, memberi waktu
        ACK terkirim ke backend sebelum proses ini benar-benar mati.
        """
        delay = settings.COMMAND_REBOOT_DELAY_SEC
        logger.warning("🔄 Reboot dijadwalkan %ds lagi (setelah ACK dikirim)...", delay)
        subprocess.Popen(
            ["setsid", "bash", "-c", f"sleep {delay} && sudo -n systemctl restart efws.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    _COMMAND_HANDLERS = {
        "Reboot": _cmd_reboot,
    }

    # ─── Main loop ───────────────────────────────────────────────
    def run(self):
        logger.info(
            "EFWS loop started. Cek threshold tiap: %ds | Retry queue tiap: %ds (thread terpisah)",
            settings.SENSOR_READ_INTERVAL_SEC,
            settings.EFWS_CONNECTIVITY_CHECK_SEC,
        )
        try:
            while True:
                # 1) Baca semua sensor + GPS tiap siklus (sesuai scheduler baru).
                data = self._read_all()
                self._update_gps()

                # 2) Evaluasi threshold aktif (remote-first, fallback lokal per-field).
                any_triggered, triggered, smoke_pct = self._evaluate(data)

                # 3) Sirine lokal selalu dievaluasi real-time, independen dari
                #    berhasil-tidaknya (atau terjadi-tidaknya) pengiriman ke backend.
                self._handle_alarm(any_triggered, triggered)

                if not any_triggered:
                    logger.info(
                        "READ | semua nilai NORMAL (di bawah threshold) — tidak ada emergency upload. "
                        "smoke=%.1f%% temp=%.1f°C hum=%.1f%%",
                        smoke_pct,
                        data["bme280"].get("temperature_c", 0) or 0,
                        data["bme280"].get("humidity_percent", 0) or 0,
                    )
                else:
                    logger.warning("🚨 EMERGENCY UPLOAD -- threshold terlewati: %s", triggered)

                    location_payload  = self._build_location_payload()
                    telemetry_payload = self._build_telemetry_payload(data, smoke_pct)
                    heartbeat_payload = self._build_heartbeat_payload(data)

                    # Endpoint 1, 2, 3 dikirim bersamaan (tiap-tiap masuk
                    # offline queue sendiri kalau gagal karena jaringan/5xx).
                    self.api.send_location(location_payload, db=self.db)
                    self.api.send_telemetry(telemetry_payload, db=self.db)
                    delivered_hb, commands = self.api.send_heartbeat(heartbeat_payload, db=self.db)

                    # Endpoint 4: HANYA jalan kalau heartbeat sukses DAN
                    # membawa command -- event-driven, bukan scheduled.
                    if delivered_hb and commands:
                        self._process_commands(commands)

                    pending = self.db.count_pending_queue()
                    if pending:
                        logger.info("📦 %d item masih di offline queue (akan di-retry thread terpisah).", pending)

                time.sleep(settings.SENSOR_READ_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("EFWS dihentikan oleh user (Ctrl+C).")
        except Exception:
            logger.critical("EFWS crash!\n%s", traceback.format_exc())
        finally:
            self._stop_flag.set()
            self.alarm.silence()
            self.api.close()
            if self.sim:
                self.sim.close()
            self.db.close()
            logger.info("EFWS shutdown selesai.")


if __name__ == "__main__":
    efws = EFWS()
    efws.run()
