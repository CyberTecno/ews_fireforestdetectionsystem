"""
Early Fire Warning System (EFWS) - Main Orchestrator
"""
import json
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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


# ─── smokeLevel calculator ────────────────────────────────────────
def _calc_smoke_level(mq2_ppm: float, mq135_ppm: float) -> float:
    """
    Gabungkan MQ-2 dan MQ-135 menjadi satu persentase 0-100%.
    Formula: (mq2/MQ2_CRIT * W_MQ2 + mq135/MQ135_CRIT * W_MQ135) * 100
    Batas: 60-70% = WARNING, ≥70% = CRITICAL.
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
    GPS_UPDATE_INTERVAL = int(settings._opt("EFWS_GPS_INTERVAL", "300"))

    def __init__(self):
        self.thresholds           = _load_thresholds()
        self.sensors, self.alarm  = _load_sensors_and_alarm()
        self.api                  = APIPublisher()
        self.db                   = DBManager()
        self.sim                  = _load_sim()   # auto-detect A7670E atau SIM7600

        self._critical_streak  = 0
        self._last_alarm_time  = 0.0
        self._last_gps_update  = 0.0

        self._location = {
            "lat":    settings.DEVICE_LOCATION["lat"],
            "lon":    settings.DEVICE_LOCATION["lon"],
            "source": "config",
            "fix":    False,
        }

        logger.info("EFWS initialised. Device: %s | Mode: %s | SIM: %s",
                    settings.DEVICE_ID, settings.RUN_MODE,
                    self.sim.module.upper() if self.sim else "none")
        self._update_gps()

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

        self._last_gps_update = time.time()
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

    # ─── Evaluate ────────────────────────────────────────────────
    def _evaluate(self, data: dict):
        t  = self.thresholds

        # smokeLevel: gabungan MQ-2 + MQ-135 → 0-100%
        smoke_pct = _calc_smoke_level(
            data["mq2"].get("ppm",   0),
            data["mq135"].get("ppm", 0),
        )
        st = {}
        st["smoke"]       = ("critical" if smoke_pct >= settings.SMOKE_CRITICAL_PCT
                             else "warning" if smoke_pct >= settings.SMOKE_WARNING_PCT
                             else "normal")
        st["temperature"]  = _evaluate_status(data["bme280"].get("temperature_c"),
                                              t["bme280"]["temp_warning_c"], t["bme280"]["temp_critical_c"])
        st["humidity_low"] = _evaluate_status(data["bme280"].get("humidity_percent"),
                                              t["bme280"]["humidity_low_percent"],
                                              t["bme280"]["humidity_low_percent"] * 0.5,
                                              higher_is_worse=False)
        st["water_low"]   = _evaluate_status(data["pressure"].get("depth_m"),
                                              t["pressure"]["low_warning_m"],
                                              t["pressure"]["low_critical_m"],
                                              higher_is_worse=False)
        soil_min = min(
            data["soil"].get("surface", {}).get("moisture_percent", 100),
            data["soil"].get("deep",    {}).get("moisture_percent", 100),
        )
        st["soil_dry"]    = _evaluate_status(soil_min,
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

        return level, triggered, st, smoke_pct

    # ─── Payload builder ─────────────────────────────────────────
    def _build_payload(self, data, statuses, level, triggered, smoke_pct) -> dict:
        """
        Bentuk body PERSIS sesuai kontrak backend:
          EFWS_API_URL/sensors/telemetry
          { deviceId, deviceToken, telemetry: [{ timestamp, waterLevel,
            waterLevelCurrentMa, smokeLevel, temp, humidity, soilMoisture,
            batteryLevel, flameDetected, windSpeed }] }

        Catatan desain:
          - waterLevel/waterLevelCurrentMa: dari submersible pressure sensor
            (depth_m + arus loop mA — mA berguna buat backend deteksi loop
            putus tanpa harus device sendiri yang mutusin threshold).
          - soilMoisture: rata-rata probe surface+deep (device punya 2 probe,
            backend cuma butuh satu angka ringkas).
          - flameDetected: SELALU false — flame sensor sudah tidak ada di
            hardware. Field dipertahankan cuma buat kompatibilitas skema.
          - Tidak ada _alarmLevel/_triggeredBy/threshold apa pun di payload —
            evaluasi alarm & threshold sekarang murni tanggung jawab backend.
            `statuses`/`level`/`triggered` di sini cuma dipakai device secara
            LOKAL untuk menyalakan sirine (lihat _handle_alarm), tidak dikirim.
        """
        soil     = data.get("soil", {})
        bme      = data.get("bme280", {})
        wind     = data.get("wind", {})
        pressure = data.get("pressure", {})
        battery  = data.get("battery", {})

        surface = soil.get("surface", {}).get("moisture_percent")
        deep    = soil.get("deep",    {}).get("moisture_percent")
        soil_values = [v for v in (surface, deep) if v is not None]
        soil_avg    = round(sum(soil_values) / len(soil_values), 2) if soil_values else None

        timestamp = (datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")


        return {
            "deviceId":    settings.DEVICE_ID,
            "deviceToken": settings.DEVICE_TOKEN,
            "telemetry": [{
                "timestamp":            timestamp,
                "waterLevel":           pressure.get("depth_m"),
                "waterLevelCurrentMa":  pressure.get("current_ma"),
                "smokeLevel":           smoke_pct,
                "temp":                 bme.get("temperature_c"),
                "humidity":             bme.get("humidity_percent"),
                "soilMoisture":         soil_avg,
                "batteryLevel":         battery.get("percent"),
                "flameDetected":        False,
                "windSpeed":            wind.get("speed_ms"),
            }],
        }

    # ─── Alarm handler (LOKAL saja — tidak disimpan ke DB) ────────
    def _handle_alarm(self, level, triggered):
        """
        Threshold & keputusan alarm sekarang murni tanggung jawab backend
        (device tidak menyimpan alarm_level/triggered_by/threshold apa pun
        ke database lokal — lihat db_manager.py).

        Evaluasi lokal (_evaluate) tetap dijalankan HANYA untuk menyalakan
        sirine secara real-time di lapangan, supaya alarm fisik tidak
        bergantung pada round-trip ke backend saat kondisi kritis.
        """
        cfg      = self.thresholds.get("alarm", {})
        required = cfg.get("consecutive_readings_required", 3)

        self._critical_streak = (self._critical_streak + 1) if level == "critical" else 0
        self.alarm.set_level(level)

        if level == "critical" and self._critical_streak >= required:
            logger.warning("🔴 ALARM CRITICAL (lokal, sirine menyala): %s", triggered)
        elif level == "warning":
            logger.warning("🟡 ALARM WARNING (lokal, sirine berdenyut): %s", triggered)

    # ─── Main loop ───────────────────────────────────────────────
    def run(self):
        logger.info("EFWS loop started. Baca+kirim tiap: %ds | Cek sinyal ulang tiap: %ds | GPS: %ds",
                    settings.SENSOR_READ_INTERVAL_SEC,
                    self.api._connectivity_check_interval,
                    self.GPS_UPDATE_INTERVAL)
        try:
            while True:
                now = time.time()

                if now - self._last_gps_update >= self.GPS_UPDATE_INTERVAL:
                    self._update_gps()

                # 1) Baca semua sensor
                data = self._read_all()
                level, triggered, statuses, smoke_pct = self._evaluate(data)
                payload = self._build_payload(data, statuses, level, triggered, smoke_pct)

                # 2) SELALU simpan ke DB dulu (sumber kebenaran lokal),
                #    baru dicoba dikirim. Kalau device mati/reboot di
                #    tengah jalan, data yang sudah masuk DB tidak hilang.
                reading_id = self.db.log_reading(data, payload)

                # 3) Sirine lokal (real-time, tidak nunggu backend)
                self._handle_alarm(level, triggered)

                # 4) Coba kirim SEKARANG. Kalau gagal (sinyal mati),
                #    otomatis masuk antrian (api.send_telemetry -> db.queue_api).
                #    Kalau sinyal memang lagi mati, publisher tidak akan
                #    nyoba re-connect tiap detik — hanya tiap
                #    _connectivity_check_interval (2 menit) supaya hemat sinyal.
                self.api.send_telemetry(payload, db=self.db)

                # 5) Setiap loop juga coba flush antrian lama (kalau ada).
                #    flush_queue() sendiri sudah dibatasi 2 menit lewat
                #    _check_connectivity() saat offline, jadi aman dipanggil
                #    tiap siklus baca tanpa membanjiri jaringan.
                self.api.flush_queue(self.db)

                pending   = self.db.count_pending_queue()
                net_tag   = "🔴 OFFLINE" if not self.api.online else "🟢 online "
                gps_tag   = f"📍{self._location['lat']:.4f},{self._location['lon']:.4f}"
                queue_tag = f" | 📦 queue={pending}" if pending > 0 else ""
                logger.info(
                    "READ #%d | %s | %s | smoke=%.1f%% "
                    "temp=%.1f°C hum=%.1f%% soil=%.1f%% "
                    "wind=%.1fm/s water=%.2fm batt=%.0f%% alarm=%s%s",
                    reading_id, net_tag, gps_tag, smoke_pct,
                    data["bme280"].get("temperature_c", 0) or 0,
                    data["bme280"].get("humidity_percent", 0) or 0,
                    payload["telemetry"][0].get("soilMoisture", 0) or 0,
                    data["wind"].get("speed_ms", 0) or 0,
                    data.get("pressure", {}).get("depth_m", 0) or 0,
                    data.get("battery", {}).get("percent", 0) or 0,
                    level, queue_tag,
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
