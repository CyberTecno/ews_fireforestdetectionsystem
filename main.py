"""
Early Fire Warning System (EFWS) - Main Orchestrator

ARSITEKTUR (per-endpoint scheduler, independent -- see REVISI below):
- Sensor Sampling (SENSOR_READ_INTERVAL_SEC): ONLY sensor read + evaluation
threshold + local siren. NEVER send to API, NEVER save
to SQLite, NEVER take GPS. Its only effect is outside itself
itself: set/clear status Emergency Mode (single source of truth for
NORMAL vs EMERGENCY) and save a snapshot of the latest sensor data.
- Location Publisher (own thread, LOCATION_INTERVAL_SEC = 30 minutes,
ALWAYS, never changes even though Emergency Mode is active): take GPS
(ONLY here GPS taken, just before send), then POST /sensors/location.
- Telemetry Publisher (own thread, one scheduler with intervals
ADAPTIVE: TELEMETRY_INTERVAL_SEC=30 minutes when NORMAL, switch to
EMERGENCY_TELEMETRY_INTERVAL_SEC=10 minutes while Emergency Mode is active).
This is where the data is saved to SQLite (sensor_readings) and
sent to POST /sensors/telemetry. Once Emergency Mode starts,
This thread is awakened RIGHT NOW (not waiting for the rest of the old interval).
- Heartbeat Publisher (own thread, HEARTBEAT_INTERVAL_SEC = 5 minutes,
ALWAYS, does not depend on Telemetry/Location/Emergency Same mode
once): POST /sensors/heartbeat. Endpoint 4 (/sensors/commands/ack)
ONLY goes from here, event-driven, if the heartbeat response takes it
'commands' -- outside of any schedule.
- Active threshold = remote config (from Telemetry response) is merged
per-field with hardcoded locale (config/threshold_resolver.py).
- Retry offline queue (every 2 minutes) remains in a separate, independent thread
of the four things above.
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

# ─── Create the required folders before the logger ──────────────────
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


# ─── GPS cache reader (read from file JSON written to ews_network_setup.sh) ──
def _read_gps_cache() -> "dict | None":
    """
Read cache file GPS written by ews_network_setup.sh / gps_refresh.sh.
Return dict GPS if fix=true, or None if none / fix=false.
main.py never opens the AT command serial port directly.
    """
    cache_path = settings.GPS_CACHE_FILE
    try:
        with open(cache_path) as f:
            data = json.load(f)
        if data.get("fix") is True:
            return data
        return None
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.debug("GPS cache read error: %s", e)
        return None


# ─── Sensor + alarm factory ──────────────────────────────────────
def _load_sensors_and_alarm():
    if settings.RUN_MODE == "mock":
        logger.info("Mode: MOCK — sensor dissimulated, no access GPIO/I2C")
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
        logger.info("Mode: HARDWARE — access real GPIO/SPI/I2C")
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
                    "Sensor '%s' FAILED is initialized (considered NOT INSTALLED,"
                    "value will be 0/null kept in log & payload until fixed): %s",
                    name, e,
                )
                sensors[name] = NullSensor(name, str(e))

        try:
            alarm = AlarmController()
        except Exception as e:
            logger.error(
                "Alarm controller (relay/siren) FAILED to initialize — local alarm "
                "disabled (system remains running, only siren is not on): %s", e,
            )
            alarm = NullAlarmController(str(e))

        return sensors, alarm


# ─── Threshold helpers ───────────────────────────────────────────
def _load_hardcoded_thresholds() -> dict:
    with open(settings.THRESHOLDS_PATH) as f:
        return json.load(f)


def _exceeds(value, danger, lower_is_worse) -> bool:
    """True if the value passes the danger threshold. None value -> always False (unknown, not an alarm)."""
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

        self._critical_streak = 0
        self._stop_flag = threading.Event()

        # ─── Inter-thread shared state for 3 independent schedulers ──
        # Emergency Mode: ONE source of truth (set/clear ONLY by
        # sampling loop). Location & Heartbeat NEVER read this --
        # only Telemetry Publisher reads to select the interval.
        self._emergency = threading.Event()

        # Indicates that Telemetry Publisher should perform
        # Immediate Emergency Send (only once during transition
        # NORMAL -> EMERGENCY).
        self._emergency_immediate_send = threading.Event()

        # A sampling loop is used to wake up the Telemetry Publisher
        # IMMEDIATELY when just entering Emergency Mode, without waiting for the rest
        # the normal interval waiting time (30 minutes) runs out first.
        self._telemetry_wake = threading.Event()
        # LATEST sensor data + smoke_pct snapshot from the sampling loop --
        # read by Telemetry Publisher every time he wants to send (not
        # read the sensor yourself, so that the "sampling sensor" remains the only one
        # that touches the sensor hardware).
        self._startup_telemetry_sent = False
        self._data_lock = threading.Lock()
        self._latest_data = None
        self._latest_smoke = None
        # Baseline to calculate "rainfall since PREVIOUS telemetry sending"
        # (delta of sensor cumulative counter) -- ONLY is updated each time
        # Telemetry Publisher actually sends, not every sampling cycle.
        self._last_rainfall_total_mm = None

        self._location = {
            "lat":    settings.DEVICE_LOCATION["lat"],
            "lon":    settings.DEVICE_LOCATION["lon"],
            "source": "config",
            "fix":    False,
        }
        # When can GPS LAST TIME actually be fixed (epoch seconds).
        # None = never at all since EFWS started. this device
        # installed PERMANENTLY at one point -- so if GPS fails to obtain a fix during a
        # cycle, it makes much more sense to use the LAST fixed position
        # known rather than directly dropping to static coordinates in config.
        self._last_gps_fix_at = None

        logger.info("EFWS initialised. Device: %s | Mode: %s | GPS cache: %s",
                    settings.DEVICE_ID, settings.RUN_MODE,
                    settings.GPS_CACHE_FILE)

        # Separate thread specifically for each offline queue retry
        # EFWS_CONNECTIVITY_CHECK_SEC (2 minutes) -- INTENTIONAL is independent of
        # sensor read cycle (3 minutes), so that the requirement "retry every
        # 2 minutes" is still fulfilled exactly even though the reading cycle is slower.
        self._flush_thread = threading.Thread(target=self._flush_queue_loop, daemon=True)
        self._flush_thread.start()

        # Separate thread: older auto-purge local data (SQLite).
        # from EFWS_DB_RETENTION_DAYS (default 3 days), checked every
        # EFWS_DB_RETENTION_CHECK_SEC (default 6 hours) -- independent of
        # sensor read cycle and offline queue retry.
        self._retention_thread = threading.Thread(target=self._retention_loop, daemon=True)
        self._retention_thread.start()

        # ─── 3 endpoint schedulers, each own thread ───────
        # No scheduler calls another scheduler. Failure in
        # one publisher never stops another publisher
        # (each has its own try/except in its loop).
        self._location_thread = threading.Thread(target=self._location_loop, daemon=True)
        self._location_thread.start()

        self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self._telemetry_thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    # ─── Background: retry offline queue, independent of read cycle ──
    def _flush_queue_loop(self):
        interval = settings.EFWS_CONNECTIVITY_CHECK_SEC
        while not self._stop_flag.is_set():
            try:
                self.api.flush_queue(self.db)
            except Exception:
                logger.error("Flush queue thread error:\n%s", traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── Background: auto-delete local data older than N days (default 3) ──
    def _retention_loop(self):
        days = settings.DB_RETENTION_DAYS
        interval = settings.DB_RETENTION_CHECK_SEC
        while not self._stop_flag.is_set():
            try:
                result = self.db.purge_old_data(days=days)
                if result["sensor_readings_deleted"] or result["api_queue_deleted"] or result["location_log_deleted"]:
                    logger.info(
                        "🧹 Retention: remove %d sensor_readings row, %d api_queue row,"
                        "%d location_log row (older than %d by days).",
                        result["sensor_readings_deleted"],
                        result["api_queue_deleted"],
                        result["location_log_deleted"],
                        days,
                    )
            except Exception:
                logger.error("Retention thread error:\n%s", traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── Publisher 1/3: Location -- ALWAYS every 30 minutes, never
    # affected by Emergency Mode. GPS JUST taken here, right before
    # send (not in sampling loop) -- according to spec. ──────────────────
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
                        "gps":        "Original GPS, NEW fix this cycle",
                        "gps_cached": "Original GPS, BUT position OLD (last known fix, resubmitted)",
                        "config":     "static fallback from config, NEVER can GPS fix",
                    }.get(self._location.get("source"), self._location.get("source")),
                )
                # Note BEFORE sending (same as Telemetry pattern) -- so
                # fixed "device once reported this position at this time" history
                # available locally even though delivery to API failed & entered the offline queue.
                self.db.log_location(self._location, payload)
                self.api.send_location(payload, db=self.db)
            except Exception:
                logger.error("Location Publisher error (does not affect Telemetry/Heartbeat):\n%s",
                             traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── Publisher 2/3: Telemetry -- SATU scheduler, interval ADAPTIF:
    # 30 minutes when NORMAL, 10 minutes while Emergency Mode is active. This is it
    # the only place data is saved to SQLite. Wake up instantly
    # (via _telemetry_wake) when Emergency Mode is just started. ────────
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
                # Not a single sampling cycle has been completed yet -- wait
                # sooner than sending an empty payload.
                continue

            immediate_send = self._emergency_immediate_send.is_set()
            if immediate_send:
                self._emergency_immediate_send.clear()

            try:
                payload = self._build_telemetry_payload(data, smoke_pct)
                # Save to local DB BEFORE sending (local source of truth,
                # and for auditing -- full_payload contains the body EXACTLY
                # sent to API). Auto-cleaned by _retention_loop.
                self.db.log_reading(data, payload)

                if immediate_send:
                    logger.warning(
                        "[Telemetry Publisher] Immediate Emergency Send"
                    )

                elif self._emergency.is_set():
                    logger.warning(
                        "[Telemetry Publisher] Emergency Scheduled Send "
                        "(interval=%ds)",
                        settings.EMERGENCY_TELEMETRY_INTERVAL_SEC,
                    )

                else:
                    logger.info(
                        "[Telemetry Publisher] Normal Scheduled Send"
                        "(interval=%ds)",
                        settings.TELEMETRY_INTERVAL_SEC,
                    )
                    
                self.api.send_telemetry(payload, db=self.db)

                pending = self.db.count_pending_queue()
                if pending:
                    logger.info("📦 %d item is still in the offline queue (retryed in a separate thread).", pending)
            except Exception:
                logger.error("Telemetry Publisher error (does not affect Location/Heartbeat):\n%s",
                             traceback.format_exc())

    # ─── Publisher 3/3: Heartbeat -- ALWAYS every 5 minutes, never
    # depends on Telemetry/Location/Emergency Mode. Endpoint 4 (command
    # ACK) ONLY goes from here, event-driven, if there are 'commands'. ──
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
                logger.error("Heartbeat Publisher error (does not affect Location/Telemetry):\n%s",
                             traceback.format_exc())
            self._stop_flag.wait(interval)

    # ─── GPS refresh (read cache from ews_network_setup/gps_refresh.sh) ────
    def _update_gps(self):
        """
Read position GPS from file cache written by:
- ews_network_setup.sh (on boot)
- gps_refresh.sh (every 30 minutes via systemd timer)

main.py DOES NOT open serial port AT command directly.
GPS fetch is the responsibility of the bash script, not Python.

        Fallback chain:
1) Cache file exists + fix=true → use coordinates from cache
2) Cache file exists + fix=false → use old position (gps_cached)
3) No cache at all → use .env (config)
        """
        if settings.RUN_MODE == "mock":
            # Mode mock: generate posisi simulasi
            self._location = {
                "lat":    settings.DEVICE_LOCATION["lat"] or -1.265400,
                "lon":    settings.DEVICE_LOCATION["lon"] or 116.831200,
                "altitude_m": 8.2,
                "source": "mock",
                "fix":    True,
            }
            self._last_gps_fix_at = time.time()
            logger.info("📍 [GPS] Mode MOCK: lat=%.6f, lon=%.6f",
                        self._location["lat"], self._location["lon"])
            return

        result = _read_gps_cache()

        if result is not None:
            # There is a fix for the cache
            cache_age_min = (time.time() - result.get("timestamp", 0)) / 60
            self._location = {
                "lat":        result["lat"],
                "lon":        result["lon"],
                "altitude_m": result.get("altitude_m"),
                "source":     "gps",
                "fix":        True,
            }
            self._last_gps_fix_at = result.get("timestamp") or time.time()
            logger.info(
                "📍 [GPS] Valid cache — lat=%.6f, lon=%.6f | cache age: %.1f minutes",
                result["lat"], result["lon"], cache_age_min,
            )
        else:
            self._gps_fallback(reason="Cache GPS is missing or fix=false")


    def _gps_fallback(self, reason: str):
        """
Called if GPS fails to fix (all attempts expired) OR modem
not available at all. Priority:
1) If NEVER can be fixed before -- this device is installed
PERMANENTLY at one point, so the old position is likely
STILL is accurate. Use it (source="gps_cached"), DO NOT silently
change to static coordinates config.
2) If NEVER can be fixed completely from start up -- then
falls to static coordinates DEVICE_LOCATION from config.
        """
        if self._last_gps_fix_at is not None:
            age_min = (time.time() - self._last_gps_fix_at) / 60
            self._location["source"] = "gps_cached"
            self._location["fix"] = False  # not this cycle's NEW fix, but the known old position
            logger.warning(
                "📍 %s -- send BELA known position GPS LAST"
                "(age %.1f minutes): lat=%s, lon=%s. (The device is assumed to be stationary"
                "at one point, so this old position is likely still correct.)",
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
                "📍 %s -- NEVER got GPS fixed from start, use it"
                "static coordinates from config: lat=%s, lon=%s.",
                reason, self._location["lat"], self._location["lon"],
            )

    # ─── Sensor reads ────────────────────────────────────────────
    def _read_all(self) -> dict:
        data = {}
        failed = []
        for key, sensor in self.sensors.items():
            try:
                data[key] = sensor.read()
                logger.debug("Sensor '%s' read: %s", key, data[key])
            except Exception as e:
                logger.error("Sensor '%s' read error: %s", key, e)
                data[key] = {"error": str(e)}

            if isinstance(data[key], dict) and data[key].get("error"):
                failed.append(key)

        # Per-cycle summary: any sensors that are unread/empty
        # this cycle -> the field automatically becomes 0/null in evaluation & payload
        # (lihat _exceeds, _calc_smoke_level, _build_telemetry_payload).
        if failed:
            logger.warning(
                "⚠️ Sensor UNREAD/EMPTY this cycle (value=0/null): %s",
                ", ".join(failed),
            )

        return data

    # ─── Evaluate (single-tier: exceeded / not, according to contract API) ──
    def _evaluate(self, data: dict):
        """
Active threshold = merge remote config (from response telemetry
last) with locally hardcoded, per-field (see threshold_resolver).
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
            "pressure":    _exceeds(data["pressure"].get("pressure_bar"), t["pressureDangerThreshold"], lower_is_worse=True),
            "soil_surface": _exceeds(surface, t["soilMoistureDangerThreshold"]["surface"], lower_is_worse=True),
            "soil_deep":    _exceeds(deep,    t["soilMoistureDangerThreshold"]["deep"],    lower_is_worse=True),
            "wind":        _exceeds(data["wind"].get("speed_ms"), t["windDangerThreshold"], lower_is_worse=False),
            # rainfall_last_hour_mm (NOT delta-since-telemetry) -- see
            # _rainfallDangerThreshold_note in thresholds.json why is it different
            # from the "rainfall" value sent in payload API.
            "rainfall":    _exceeds(data["rainfall"].get("rainfall_last_hour_mm"), t["rainfallDangerThreshold"], lower_is_worse=False),
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

    # ─── Calculate rainfall delta since PREVIOUS telemetry sending ──
    def _rainfall_delta(self, total_mm):
        """
        total_mm: CURRENT rainfall_total_mm (the sensor's cumulative counter,
        which always increases and never resets unless reset manually).
        Returns the rainfall in mm since this method's PREVIOUS call (that is,
        since telemetry was last sent) -- None if the sensor is unavailable
        (NullSensor), or 0.0 on the FIRST transmission (no comparison baseline yet).
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
                    "waterLevel": pressure.get("depth_m"),
                    "pressure": pressure.get("pressure_bar"),
                    # "rainfall" = mm rain SINCE PREVIOUS telemetry sending
                    # (delta of cumulative counter rainfall_total_mm), NOT
                    # Sensor built-in 1-hour window -- so the numbers always match
                    # with the actual sending period (30 minutes normal /
                    # 10 minutes emergency), not a fixed window that is not synchronized.
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

    # ─── LOCAL alarm handler (real-time siren) + single source of truth
    # for Emergency Mode status used by Telemetry Publisher ─────
    def _handle_alarm(self, any_triggered: bool, triggered: list):
        cfg      = self.hardcoded_thresholds.get("alarm", {})
        required = cfg.get("consecutive_readings_required", 3)

        self._critical_streak = (self._critical_streak + 1) if any_triggered else 0
        self.alarm.set_level("critical" if any_triggered else "normal")

        was_emergency = self._emergency.is_set()
        now_emergency = any_triggered and self._critical_streak >= required

        if now_emergency and not was_emergency:
            logger.warning("🔴 ALARM (local, siren on) — %d sequential reading: %s --"
                           "ENTER EMERGENCY MODE, Telemetry Publisher is developed now.",
                           self._critical_streak, triggered)
            self._emergency.set()
            # Immediate telemetry only SATU KALI
            self._emergency_immediate_send.set()
            self._telemetry_wake.set()  # wake the Telemetry Publisher NOW; do not wait for the old interval to expire
        elif not now_emergency and was_emergency:
            logger.warning("🟢 All return values ​​NORMAL -- EXIT EMERGENCY MODE,"
                           "Telemetry Publisher returns to a 30 minute schedule.")
            self._emergency.clear()

    # ─── Endpoint 4: execute command from heartbeat, then ACK ───
    def _process_commands(self, commands: list):
        for cmd in commands:
            command_id = cmd.get("id", "")
            command_name = cmd.get("command", "")
            logger.warning("📥 Command received from backend: id=%s command=%s", command_id, command_name)

            handler = self._COMMAND_HANDLERS.get(command_name)
            if handler is None:
                logger.error("Command '%s' is unknown.", command_name)
                ack = self._build_ack_payload(command_id, "FAILED", f"Unknown command: {command_name}")
                self.api.send_command_ack(ack, db=self.db)
                continue

            try:
                handler(self)
                ack = self._build_ack_payload(command_id, "SUCCESS")
            except Exception as e:
                logger.error("Command '%s' failed: %s", command_name, e)
                ack = self._build_ack_payload(command_id, "FAILED", str(e))

            self.api.send_command_ack(ack, db=self.db)

    def _cmd_reboot(self):
        """
IMPORTANT ARCHITECTURAL NOTE:
The spec asks for "execute -> wait until complete -> then send ACK". For
This Reboot command is TECHNICALLY IMPOSSIBLE is filled with literals:
once `systemctl restart efws.service` is executed, the Python process
which is running (this process itself) will be killed by BEFORE
sends ACK "once completed".

The solution used: dispatch restart via the child process
DETACHED with short delay (EFWS_REBOOT_DELAY_SEC, default 5s),
then consider it "successful" once that restart is scheduled (not after
restart completely completed) -- ACK SUCCESS sent by caller
(_process_commands) IMMEDIATELY after this function returns, gives the time
ACK is sent to the backend before the process actually dies.
        """
        delay = settings.COMMAND_REBOOT_DELAY_SEC
        logger.warning("🔄 Reboot scheduled %ds again (after ACK is sent)...", delay)
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

    # ─── Main loop -- SENSOR SAMPLING ONLY (read + threshold evaluation).
    # Doesn't send to API, doesn't save to SQLite, doesn't grab GPS here --
    # that's all the tasks of each Location/Telemetry/Heartbeat Publisher
    # in its own thread (see _location_loop/_telemetry_loop/_heartbeat_loop). ──
    def run(self):
        logger.info(
            "EFWS loop started. Sensor sampling tiap: %ds | "
            "Location: %ds (always) | Telemetry: %ds normal / %ds emergency |"
            "Heartbeat: %ds (always) | Retry queue: %ds (separate thread)",
            settings.SENSOR_READ_INTERVAL_SEC,
            settings.LOCATION_INTERVAL_SEC,
            settings.TELEMETRY_INTERVAL_SEC,
            settings.EMERGENCY_TELEMETRY_INTERVAL_SEC,
            settings.HEARTBEAT_INTERVAL_SEC,
            settings.EFWS_CONNECTIVITY_CHECK_SEC,
        )
        try:
            while True:
                # 1) Read all sensors each cycle (GPS NOT here).
                data = self._read_all()

                # 2) Active threshold evaluation (remote-first, per-field local fallback).
                any_triggered, triggered, smoke_pct = self._evaluate(data)

                # 3) Save the latest snapshot for Telemetry & Heartbeat
                #    Publisher (another thread) always has fresh data without
                #    need to read the sensors individually.
                with self._data_lock:
                    self._latest_data = data
                    self._latest_smoke = smoke_pct
                    if not self._startup_telemetry_sent:
                        self._startup_telemetry_sent = True
                        self._telemetry_wake.set()

                # 4) Local siren + Emergency Mode status (single source of
                #    truth for Telemetry Publisher) -- always evaluated
                #    real-time, independent of any publisher.
                self._handle_alarm(any_triggered, triggered)

                if not any_triggered:
                    logger.info(
                        "READ | all values ​​NORMAL. smoke=%.1f%% temp=%.1f°C hum=%.1f%%",
                        smoke_pct or 0,
                        data["bme280"].get("temperature_c", 0) or 0,
                        data["bme280"].get("humidity_percent", 0) or 0,
                    )

                time.sleep(settings.SENSOR_READ_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("EFWS was stopped by user (Ctrl+C).")
        except Exception:
            logger.critical("EFWS crash!\n%s", traceback.format_exc())
        finally:
            self._stop_flag.set()
            self._telemetry_wake.set()  # wake Telemetry Publisher so that it exits immediately
            self.alarm.silence()
            self.api.close()
            self.db.close()
            logger.info("EFWS shutdown completed.")


if __name__ == "__main__":
    efws = EFWS()
    efws.run()
