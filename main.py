"""
Early Fire Warning System (EFWS) - Main Orchestrator

ARSITEKTUR (scheduler per-endpoint, independen -- lihat REVISI di bawah):
  - Sensor Sampling (SENSOR_READ_INTERVAL_SEC): HANYA baca sensor + evaluasi
    threshold + sirine lokal. TIDAK PERNAH kirim ke API, TIDAK PERNAH simpan
    ke SQLite, TIDAK PERNAH ambil GPS. Satu-satunya efeknya ke luar dirinya
    sendiri: set/clear status Emergency Mode (single source of truth untuk
    NORMAL vs EMERGENCY) dan simpan snapshot data sensor terbaru.
  - Location Publisher (thread sendiri, LOCATION_INTERVAL_SEC = 30 menit,
    SELALU, tidak pernah berubah walau Emergency Mode aktif): ambil GPS
    (HANYA di sini GPS diambil, tepat sebelum kirim), lalu POST /sensors/location.
  - Telemetry Publisher (thread sendiri, satu scheduler yang interval-nya
    ADAPTIF: TELEMETRY_INTERVAL_SEC=30 menit saat NORMAL, beralih ke
    EMERGENCY_TELEMETRY_INTERVAL_SEC=10 menit selama Emergency Mode aktif).
    Baru di sinilah data disimpan ke SQLite (sensor_readings) dan
    dikirim ke POST /sensors/telemetry. Begitu Emergency Mode dimulai,
    thread ini dibangunkan SEKARANG JUGA (tidak menunggu sisa interval lama).
  - Heartbeat Publisher (thread sendiri, HEARTBEAT_INTERVAL_SEC = 5 menit,
    SELALU, tidak bergantung ke Telemetry/Location/Emergency Mode sama
    sekali): POST /sensors/heartbeat. Endpoint 4 (/sensors/commands/ack)
    HANYA jalan dari sini, event-driven, kalau response heartbeat bawa
    'commands' -- di luar jadwal manapun.
  - Threshold aktif = remote config (dari response Telemetry) di-merge
    per-field dengan hardcoded lokal (config/threshold_resolver.py).
  - Retry offline queue (tiap 2 menit) tetap di thread terpisah, independen
    dari keempat hal di atas.
"""
import json
import time
import logging
import threading
import subprocess
import traceback
from pathlib import Path
from datetime import UTC, datetime, timezone
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
def _calc_smoke_level(mq2_ppm, mq135_ppm):

    if mq2_ppm is None and mq135_ppm is None:
        return None

    mq2 = 0 if mq2_ppm is None else mq2_ppm
    mq135 = 0 if mq135_ppm is None else mq135_ppm

    n2 = min(mq2 / settings.SMOKE_MQ2_CRIT_PPM,1.5)
    n135 = min(mq135 / settings.SMOKE_MQ135_CRIT_PPM,1.5)

    raw = (
        n2*settings.SMOKE_WEIGHT_MQ2
        +
        n135*settings.SMOKE_WEIGHT_MQ135
    )*100

    return round(min(raw,100),2)


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
            MockSoilMoisture, MockAnemometer, MockWindDirection, MockBattery,
            MockFlame, MockRainfall, MockAlarmController,
        )
        return {
            "mq2":      MockMQ2(),
            "mq135":    MockMQ135(),
            "bme280":   MockBME280(),
            "pressure": MockPressureWater(),
            "soil":     MockSoilMoisture(),
            "wind":     MockAnemometer(),
            "wind_dir": MockWindDirection(),
            "battery":  MockBattery(),
            "flame":    MockFlame(),
            "rainfall": MockRainfall(),
        }, MockAlarmController()
    else:
        logger.info("Mode: HARDWARE — mengakses GPIO/SPI/I2C nyata")
        from sensors.mq2         import MQ2Sensor
        from sensors.mq135       import MQ135Sensor
        from sensors.bme280      import BME280Sensor
        from sensors.pressure    import PressureWaterSensor
        from sensors.soil        import SoilMoistureSensor
        from sensors.anemometer  import AnemometerSensor
        from sensors.wind_direction import WindDirectionSensor
        from sensors.battery     import BatterySensor
        from sensors.flame       import FlameSensor
        from sensors.rainfall    import RainfallSensor
        from sensors.null_sensor import NullSensor, NullAlarmController
        from alarm.siren         import AlarmController

        factories = {
            "mq2":      MQ2Sensor,
            "mq135":    MQ135Sensor,
            "bme280":   BME280Sensor,
            "pressure": PressureWaterSensor,
            "soil":     SoilMoistureSensor,
            "wind":     AnemometerSensor,
            "wind_dir": WindDirectionSensor,
            "battery":  BatterySensor,
            "flame":    FlameSensor,
            "rainfall": RainfallSensor,
        }
        sensors = {}
        for name, factory in factories.items():
            try:
                sensors[name] = factory()
            except Exception as e:
                logger.error(
                    "Sensor '%s' GAGAL diinisialisasi (dianggap TIDAK TERPASANG, "
                    "nilainya akan 0/null terus di log & payload sampai diperbaiki): %s",
                    name, e,
                )
                sensors[name] = NullSensor(name, str(e))

        try:
            alarm = AlarmController()
        except Exception as e:
            logger.error(
                "Alarm controller (relay/sirine) GAGAL diinisialisasi — alarm lokal "
                "dinonaktifkan (sistem tetap jalan, hanya sirine yang tidak menyala): %s", e,
            )
            alarm = NullAlarmController(str(e))

        return sensors, alarm


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
        # Diaktifkan lagi setelah scan_ports() dipatch untuk mengecualikan
        # ANEMOMETER_PORT dari daftar kandidat -- sebelumnya di-None-kan karena
        # scan sempat ikut membuka port anemometer dan mengacaukan Modbus RTU.
        # Lihat communication/sim_detector.py::scan_ports().

        self._critical_streak = 0
        self._stop_flag = threading.Event()

        # ─── State bersama antar-thread untuk 3 scheduler independen ──
        # Emergency Mode: SATU sumber kebenaran (di-set/clear HANYA oleh
        # sampling loop). Location & Heartbeat TIDAK PERNAH membaca ini --
        # cuma Telemetry Publisher yang membaca untuk memilih interval.
        self._emergency = threading.Event()
        # Dipakai sampling loop untuk membangunkan Telemetry Publisher
        # SEKETIKA saat baru masuk Emergency Mode, tanpa menunggu sisa
        # waktu tunggu interval normal (30 menit) habis dulu.
        self._telemetry_wake = threading.Event()
        # Snapshot data sensor + smoke_pct TERBARU dari sampling loop --
        # dibaca oleh Telemetry Publisher tiap kali dia mau kirim (bukan
        # baca sensor sendiri, supaya "sensor sampling" tetap satu-satunya
        # yang menyentuh hardware sensor).
        self._startup_telemetry_sent = False
        self._data_lock = threading.Lock()
        self._latest_data = None
        self._latest_smoke = None
        # Baseline utk hitung "rainfall sejak pengiriman telemetry SEBELUMNYA"
        # (delta dari counter kumulatif sensor) -- HANYA di-update tiap kali
        # Telemetry Publisher benar-benar kirim, bukan tiap siklus sampling.
        self._last_rainfall_total_mm = None

        self._location = {
            "lat":    settings.DEVICE_LOCATION["lat"],
            "lon":    settings.DEVICE_LOCATION["lon"],
            "source": "config",
            "fix":    False,
        }
        # Kapan GPS TERAKHIR KALI benar-benar dapat fix (epoch seconds).
        # None = belum pernah sama sekali sejak EFWS ini start. Device ini
        # terpasang PERMANEN di satu titik -- jadi kalau GPS gagal fix di
        # suatu siklus, jauh lebih masuk akal pakai posisi fix TERAKHIR yang
        # diketahui daripada langsung jatuh ke koordinat statis di config.
        self._last_gps_fix_at = None

        logger.info("EFWS initialised. Device: %s | Mode: %s | SIM: %s",
                    settings.DEVICE_ID, settings.RUN_MODE,
                    self.sim.module.upper() if self.sim else "none")

        # Thread terpisah khusus retry offline queue tiap
        # EFWS_CONNECTIVITY_CHECK_SEC (2 menit) -- SENGAJA independen dari
        # siklus baca sensor (3 menit), supaya requirement "retry every
        # 2 minutes" tetap terpenuhi persis walau siklus baca lebih lambat.
        self._flush_thread = threading.Thread(target=self._flush_queue_loop, daemon=True)
        self._flush_thread.start()

        # Thread terpisah: auto-purge data lokal (SQLite) yang lebih tua
        # dari EFWS_DB_RETENTION_DAYS (default 3 hari), dicek tiap
        # EFWS_DB_RETENTION_CHECK_SEC (default 6 jam) -- independen dari
        # siklus baca sensor maupun retry offline queue.
        self._retention_thread = threading.Thread(target=self._retention_loop, daemon=True)
        self._retention_thread.start()

        # ─── 3 scheduler endpoint, masing-masing thread sendiri ───────
        # Tidak ada scheduler yang memanggil scheduler lain. Kegagalan di
        # satu publisher tidak pernah menghentikan publisher lainnya
        # (masing-masing punya try/except sendiri di loop-nya).
        self._location_thread = threading.Thread(target=self._location_loop, daemon=True)
        self._location_thread.start()

        self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self._telemetry_thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    # ─── Background: retry offline queue, independen dari siklus baca ──
    def _flush_queue_loop(self):
        interval = settings.EFWS_CONNECTIVITY_CHECK_SEC
        while not self._stop_flag.is_set():
            try:
                self.api.flush_queue(self.db)
            except Exception:
                logger.error("Flush queue thread error:\n%s", traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── Background: auto-hapus data lokal lebih dari N hari (default 3) ──
    def _retention_loop(self):
        days = settings.DB_RETENTION_DAYS
        interval = settings.DB_RETENTION_CHECK_SEC
        while not self._stop_flag.is_set():
            try:
                result = self.db.purge_old_data(days=days)
                if result["sensor_readings_deleted"] or result["api_queue_deleted"] or result["location_log_deleted"]:
                    logger.info(
                        "🧹 Retention: hapus %d baris sensor_readings, %d baris api_queue, "
                        "%d baris location_log (lebih tua dari %d hari).",
                        result["sensor_readings_deleted"],
                        result["api_queue_deleted"],
                        result["location_log_deleted"],
                        days,
                    )
            except Exception:
                logger.error("Retention thread error:\n%s", traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── Publisher 1/3: Location -- SELALU tiap 30 menit, tidak pernah
    # terpengaruh Emergency Mode. GPS HANYA diambil di sini, tepat sebelum
    # kirim (bukan di sampling loop) -- sesuai spec. ──────────────────
    def _location_loop(self):
        interval = settings.LOCATION_INTERVAL_SEC
        while not self._stop_flag.is_set():
            try:
                self._update_gps()
                payload = self._build_location_payload()
                logger.info(
                    "📍 [Location Publisher] lat=%s, lon=%s | source=%s (%s)",
                    self._location.get("lat"), self._location.get("lon"),
                    self._location.get("source"),
                    {
                        "gps":        "GPS asli, fix BARU siklus ini",
                        "gps_cached": "GPS asli, TAPI posisi LAMA (fix terakhir yang diketahui, dikirim ulang)",
                        "config":     "fallback statis dari config, BELUM PERNAH dapat GPS fix",
                    }.get(self._location.get("source"), self._location.get("source")),
                )
                # Dicatat SEBELUM kirim (sama seperti pola Telemetry) -- supaya
                # riwayat "device pernah lapor posisi ini pada waktu ini" tetap
                # ada di lokal walau pengiriman ke API gagal & masuk offline queue.
                self.db.log_location(self._location, payload)
                self.api.send_location(payload, db=self.db)
            except Exception:
                logger.error("Location Publisher error (tidak mempengaruhi Telemetry/Heartbeat):\n%s",
                             traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── Publisher 2/3: Telemetry -- SATU scheduler, interval ADAPTIF:
    # 30 menit saat NORMAL, 10 menit selama Emergency Mode aktif. Inilah
    # satu-satunya tempat data disimpan ke SQLite. Dibangunkan seketika
    # (lewat _telemetry_wake) saat Emergency Mode baru dimulai. ────────
    def _telemetry_loop(self):
        while not self._stop_flag.is_set():
            interval = (
                settings.EMERGENCY_TELEMETRY_INTERVAL_SEC
                if self._emergency.is_set()
                else settings.TELEMETRY_INTERVAL_SEC
            )
            self._telemetry_wake.wait(timeout=interval)
            self._telemetry_wake.clear()
            if self._stop_flag.is_set():
                break

            with self._data_lock:
                data, smoke_pct = self._latest_data, self._latest_smoke
            if data is None:
                # Belum ada satu pun siklus sampling yang selesai -- tunggu
                # sebentar lagi daripada kirim payload kosong.
                continue

            try:
                payload = self._build_telemetry_payload(data, smoke_pct)
                # Simpan ke DB lokal SEBELUM dikirim (sumber kebenaran lokal,
                # dan untuk audit -- full_payload berisi PERSIS body yang
                # dikirim ke API). Dibersihkan otomatis oleh _retention_loop.
                self.db.log_reading(data, payload)
                mode = "EMERGENCY" if self._emergency.is_set() else "rutin"
                logger.warning("📡 [Telemetry Publisher] kirim (%s, interval=%ds)", mode, interval)
                self.api.send_telemetry(payload, db=self.db)

                pending = self.db.count_pending_queue()
                if pending:
                    logger.info("📦 %d item masih di offline queue (di-retry thread terpisah).", pending)
            except Exception:
                logger.error("Telemetry Publisher error (tidak mempengaruhi Location/Heartbeat):\n%s",
                             traceback.format_exc())

    # ─── Publisher 3/3: Heartbeat -- SELALU tiap 5 menit, tidak pernah
    # bergantung ke Telemetry/Location/Emergency Mode. Endpoint 4 (command
    # ACK) HANYA jalan dari sini, event-driven, kalau ada 'commands'. ──
    def _heartbeat_loop(self):
        interval = settings.HEARTBEAT_INTERVAL_SEC
        while not self._stop_flag.is_set():
            try:
                with self._data_lock:
                    data = self._latest_data or {}
                payload = self._build_heartbeat_payload(data)
                delivered, commands = self.api.send_heartbeat(payload, db=self.db)
                if delivered and commands:
                    self._process_commands(commands)
            except Exception:
                logger.error("Heartbeat Publisher error (tidak mempengaruhi Location/Telemetry):\n%s",
                             traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── GPS refresh (dipanggil HANYA oleh _location_loop, bukan sampling) ──
    def _update_gps(self):
        if self.sim is None:
            self._gps_fallback(reason="SIM/GPS tidak tersedia")
            return

        module_name = self.sim.module.upper() if hasattr(self.sim, "module") else "SIM"
        attempts = settings.GPS_FIX_ATTEMPTS

        for attempt in range(1, attempts + 1):
            logger.info(
                "📡 GPS percobaan %d/%d dari %s (port=%s, timeout %ds)...",
                attempt, attempts, module_name, getattr(self.sim, "port", "?"),
                settings.GPS_TIMEOUT_SEC,
            )
            try:
                result = self.sim.get_gps(timeout=settings.GPS_TIMEOUT_SEC)
            except Exception as e:
                logger.warning("📍 GPS error dari %s (percobaan %d/%d): %s",
                               module_name, attempt, attempts, e)
                result = {"fix": False, "reason": str(e)}

            if result.get("fix"):
                self._location = {
                    "lat":        result["lat"],
                    "lon":        result["lon"],
                    "altitude_m": result.get("altitude_m"),
                    "source":     "gps",
                    "fix":        True,
                }
                self._last_gps_fix_at = time.time()
                logger.info(
                    "📍 GPS FIX NYATA (percobaan %d/%d) dari %s: lat=%.6f, lon=%.6f, alt=%sm%s",
                    attempt, attempts, module_name, result["lat"], result["lon"],
                    result.get("altitude_m"),
                    " | mock=True (bukan hardware asli)" if result.get("_mock") else "",
                )
                if result.get("raw"):
                    logger.debug("📍 Raw +CGPSINFO dari %s: %s", module_name, result["raw"])
                return  # sukses -- tidak perlu percobaan berikutnya

            logger.warning("📍 GPS percobaan %d/%d dari %s TIDAK fix (%s).",
                           attempt, attempts, module_name, result.get("reason"))
            if attempt < attempts:
                self._stop_flag.wait(settings.GPS_RETRY_DELAY_SEC)

        self._gps_fallback(reason=f"semua {attempts} percobaan GPS gagal fix")

    def _gps_fallback(self, reason: str):
        """
        Dipanggil kalau GPS gagal fix (semua percobaan habis) ATAU modem
        tidak tersedia sama sekali. Prioritas:
          1) Kalau PERNAH dapat fix sebelumnya -- device ini terpasang
             PERMANEN di satu titik, jadi posisi lama kemungkinan besar
             MASIH akurat. Pakai itu (source="gps_cached"), JANGAN diam-diam
             ganti ke koordinat statis config.
          2) Kalau BELUM PERNAH dapat fix sama sekali sejak start -- baru
             jatuh ke koordinat statis DEVICE_LOCATION dari config.
        """
        if self._last_gps_fix_at is not None:
            age_min = (time.time() - self._last_gps_fix_at) / 60
            self._location["source"] = "gps_cached"
            self._location["fix"] = False  # bukan fix BARU siklus ini, tapi posisi lama yang diketahui
            logger.warning(
                "📍 %s -- kirim ULANG posisi GPS TERAKHIR yang diketahui "
                "(usia %.1f menit): lat=%s, lon=%s. (Device diasumsikan diam "
                "di satu titik, jadi posisi lama ini kemungkinan besar masih benar.)",
                reason, age_min, self._location.get("lat"), self._location.get("lon"),
            )
        else:
            self._location = {
                "lat":    settings.DEVICE_LOCATION["lat"],
                "lon":    settings.DEVICE_LOCATION["lon"],
                "source": "config",
                "fix":    False,
            }
            logger.warning(
                "📍 %s -- BELUM PERNAH dapat GPS fix sejak start, pakai "
                "koordinat statis dari config: lat=%s, lon=%s.",
                reason, self._location["lat"], self._location["lon"],
            )

    # ─── Sensor reads ────────────────────────────────────────────
    def _read_all(self) -> dict:
        data = {}
        failed = []
        for key, sensor in self.sensors.items():
            try:
                data[key] = sensor.read()
                print(f"Sensor '{key}' read: {data[key]}")
            except Exception as e:
                logger.error("Sensor '%s' read error: %s", key, e)
                data[key] = {"error": str(e)}

            if isinstance(data[key], dict) and data[key].get("error"):
                failed.append(key)

        # Ringkasan per-siklus: sensor mana saja yang tidak terbaca/kosong
        # siklus ini -> field-nya otomatis jadi 0/null di evaluasi & payload
        # (lihat _exceeds, _calc_smoke_level, _build_telemetry_payload).
        if failed:
            logger.warning(
                "⚠️ Sensor TIDAK TERBACA/KOSONG siklus ini (nilai=0/null): %s",
                ", ".join(failed),
            )

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
            data["mq2"].get("ppm", None),
            data["mq135"].get("ppm", None),
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

    # ─── Hitung rainfall delta sejak pengiriman telemetry SEBELUMNYA ──
    def _rainfall_delta(self, total_mm):
        """
        total_mm: rainfall_total_mm SAAT INI (counter kumulatif dari sensor,
        selalu naik/tidak pernah reset sendiri kecuali di-set manual).
        Return: mm yang turun sejak panggilan TERAKHIR method ini (yaitu
        sejak telemetry SEBELUMNYA benar-benar dikirim) -- None kalau
        sensor tidak tersedia (NullSensor), 0.0 di pengiriman PERTAMA
        (belum ada baseline pembanding).
        """
        if total_mm is None:
            return None
        if self._last_rainfall_total_mm is None:
            delta = 0.0
        else:
            delta = max(0.0, round(total_mm - self._last_rainfall_total_mm, 4))
        self._last_rainfall_total_mm = total_mm
        return delta

    def _build_telemetry_payload(self, data, smoke_pct) -> dict:
        soil     = data.get("soil", {})
        bme      = data.get("bme280", {})
        wind     = data.get("wind", {})
        pressure = data.get("pressure", {})
        battery  = data.get("battery", {})
        flame    = data.get("flame", {})
        rainfall = data.get("rainfall", {})

        timestamp = (
            datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

        return {
            "deviceId": settings.DEVICE_ID,
            "deviceToken": settings.DEVICE_TOKEN,
            "telemetry": [
                {
                    "timestamp": timestamp,
                    "smokeLevel": smoke_pct,
                    "temp": bme.get("temperature_c"),
                    "humidity": bme.get("humidity_percent"),
                    "soilMoisture": {
                        "surface": soil.get("surface", {}).get("moisture_percent"),
                        "deep":    soil.get("deep", {}).get("moisture_percent"),
                    },
                    "windSpeed": wind.get("speed_ms") if wind.get("speed_ms") is not None else 0,
                    "windDirection": data.get("wind_dir", {}).get("direction_abbr"),
                    "batteryLevel": battery.get("percent"),
                    "flame": flame.get("flame_detected"),
                    "waterLevel": pressure.get("depth_m"),
                    "pressure": pressure.get("pressure_bar"),
                    # "rainfall" = mm hujan SEJAK pengiriman telemetry SEBELUMNYA
                    # (delta dari counter kumulatif rainfall_total_mm), BUKAN
                    # window 1-jam bawaan sensor -- supaya angkanya selalu pas
                    # dengan periode kirim yang sebenarnya (30 menit normal /
                    # 10 menit darurat), bukan window tetap yang tidak sinkron.
                    "rainfall": self._rainfall_delta(rainfall.get("rainfall_total_mm")),
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

    # ─── Alarm handler LOKAL (sirine real-time) + single source of truth
    # untuk status Emergency Mode yang dipakai Telemetry Publisher ─────
    def _handle_alarm(self, any_triggered: bool, triggered: list):
        cfg      = self.hardcoded_thresholds.get("alarm", {})
        required = cfg.get("consecutive_readings_required", 3)

        self._critical_streak = (self._critical_streak + 1) if any_triggered else 0
        self.alarm.set_level("critical" if any_triggered else "normal")

        was_emergency = self._emergency.is_set()
        now_emergency = any_triggered and self._critical_streak >= required

        if now_emergency and not was_emergency:
            logger.warning("🔴 ALARM (lokal, sirine menyala) — %d bacaan berturut: %s -- "
                           "MASUK EMERGENCY MODE, Telemetry Publisher dibangunkan sekarang.",
                           self._critical_streak, triggered)
            self._emergency.set()
            self._telemetry_wake.set()  # bangunkan Telemetry Publisher SEKARANG, jangan tunggu interval lama habis
        elif not now_emergency and was_emergency:
            logger.warning("🟢 Semua nilai kembali NORMAL -- KELUAR EMERGENCY MODE, "
                           "Telemetry Publisher kembali ke jadwal 30 menit.")
            self._emergency.clear()

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

    # ─── Main loop -- SENSOR SAMPLING SAJA (baca + evaluasi threshold).
    # Tidak kirim ke API, tidak simpan ke SQLite, tidak ambil GPS di sini --
    # itu semua tugas Location/Telemetry/Heartbeat Publisher masing-masing
    # di thread sendiri (lihat _location_loop/_telemetry_loop/_heartbeat_loop). ──
    def run(self):
        logger.info(
            "EFWS loop started. Sensor sampling tiap: %ds | "
            "Location: %ds (selalu) | Telemetry: %ds normal / %ds emergency | "
            "Heartbeat: %ds (selalu) | Retry queue: %ds (thread terpisah)",
            settings.SENSOR_READ_INTERVAL_SEC,
            settings.LOCATION_INTERVAL_SEC,
            settings.TELEMETRY_INTERVAL_SEC,
            settings.EMERGENCY_TELEMETRY_INTERVAL_SEC,
            settings.HEARTBEAT_INTERVAL_SEC,
            settings.EFWS_CONNECTIVITY_CHECK_SEC,
        )
        try:
            while True:
                # 1) Baca semua sensor tiap siklus (GPS TIDAK di sini).
                data = self._read_all()

                # 2) Evaluasi threshold aktif (remote-first, fallback lokal per-field).
                any_triggered, triggered, smoke_pct = self._evaluate(data)

                # 3) Simpan snapshot terbaru supaya Telemetry & Heartbeat
                #    Publisher (thread lain) selalu punya data segar tanpa
                #    perlu baca sensor sendiri-sendiri.
                with self._data_lock:
                    self._latest_data = data
                    self._latest_smoke = smoke_pct
                    if not self._startup_telemetry_sent:
                        self._startup_telemetry_sent = True
                        self._telemetry_wake.set()

                # 4) Sirine lokal + status Emergency Mode (single source of
                #    truth untuk Telemetry Publisher) -- selalu dievaluasi
                #    real-time, independen dari publisher mana pun.
                self._handle_alarm(any_triggered, triggered)

                if not any_triggered:
                    logger.info(
                        "READ | semua nilai NORMAL. smoke=%.1f%% temp=%.1f°C hum=%.1f%%",
                        smoke_pct or 0,
                        data["bme280"].get("temperature_c", 0) or 0,
                        data["bme280"].get("humidity_percent", 0) or 0,
                    )

                time.sleep(settings.SENSOR_READ_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("EFWS dihentikan oleh user (Ctrl+C).")
        except Exception:
            logger.critical("EFWS crash!\n%s", traceback.format_exc())
        finally:
            self._stop_flag.set()
            self._telemetry_wake.set()  # bangunkan Telemetry Publisher supaya langsung keluar, tidak nunggu interval
            self.alarm.silence()
            self.api.close()
            if self.sim:
                self.sim.close()
            self.db.close()
            logger.info("EFWS shutdown selesai.")


if __name__ == "__main__":
    efws = EFWS()
    efws.run()
