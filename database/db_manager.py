"""
SQLite local data logger for EFWS.

Prinsip alur data:
read sensors → SAVE to DB first (sensor_readings, local source of truth)
→ try sending to API
→ failed (signal off)? → enter queue (api_queue), payload
saved AS IS (JSON exactly) so that when it is flushed
If you repeat later, the data will not change in the slightest
→ EFWSPublisher checks the signal again every EFWS_CONNECTIVITY_CHECK_SEC
(default 2 minutes) then auto flush when it's online again.

NOT stores any alarm_level / triggered_by / threshold — evaluate
alarm & threshold are now purely the backend's responsibility. Device only
Evaluate the status LOCAL (main.py) to activate the siren automatically
real-time, without persisting it here.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone, timedelta
from config import settings


class DBManager:
    def __init__(self, db_path: str = settings.DB_PATH):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    # ─── Schema ──────────────────────────────────────────────────
    def _init_tables(self):
        cur = self.conn.cursor()

        # Main table: one row per read cycle, column per raw sensor.
        # There's no status column/alarm/threshold — that's a backend thing.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp         TEXT    NOT NULL,
                device_id         TEXT    NOT NULL,
                mq2_voltage       REAL,
                mq2_ppm           REAL,
                mq135_voltage     REAL,
                mq135_ppm         REAL,
                temperature_c     REAL,
                humidity_pct      REAL,
                pressure_hpa      REAL,
                soil_surface_pct  REAL,
                soil_deep_pct     REAL,
                wind_speed_ms     REAL,
                wind_direction    TEXT,
                water_current_ma  REAL,
                water_depth_m     REAL,
                water_pressure_bar REAL,
                water_fault_open  INTEGER,
                battery_voltage   REAL,
                battery_pct       REAL,
                flame_detected    INTEGER,
rainfall_delta_mm REAL, -- mm since PREVIOUS telemetry (not a 1 hour window)
full_payload TEXT -- JSON EXACTLY sent to API (for audit)
            )
        """)

        # Failed send queue API (offline buffer)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                endpoint    TEXT    NOT NULL,
                payload     TEXT    NOT NULL,
                attempts    INTEGER DEFAULT 0,
                last_error  TEXT,
                sent        INTEGER DEFAULT 0
            )
        """)

        # Log every time Location Publisher TRY sends (not just the ones
        # success -- if it fails & enters api_queue, this line remains,
        # so that the history of "the device once reported position X at time Y" does not
        # missing, apart from the retry queue mechanism).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS location_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                device_id   TEXT    NOT NULL,
                latitude    REAL,
                longitude   REAL,
source TEXT, -- "gps" or "config" (fallback)
fix INTEGER, -- 1 if GPS is completely fixed, 0 if fallback
full_payload TEXT -- JSON EXACTLY sent to API (for audit)
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts ON sensor_readings(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_queue_sent  ON api_queue(sent)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_location_ts ON location_log(timestamp)")

        self.conn.commit()

    # ─── Logging sensor readings ──────────────────────────────────
    def log_reading(self, data: dict, api_payload: dict) -> int:
        """
Save one read cycle to database BEFORE attempting send to API.
- data: result dict EFWS._read_all() → {"mq2":{...}, "mq135":{...},
                       "bme280":{...}, "soil":{"surface":{...},"deep":{...}},
                       "wind":{...}, "pressure":{...}, "battery":{...}}
- api_payload: EXACT payload to be sent to API, kept intact
in the full_payload column for auditing/comparison with the contents
offline queue. The rainfall_delta_mm column is taken from
SINI (not recalculated from raw data), so
the value is EXACTLY the same as the one actually sent
(main.py EFWS._rainfall_delta() is the source of truth
the only one for this delta value).
        Return: row id.
        """
        mq2      = data.get("mq2", {})
        mq135    = data.get("mq135", {})
        bme      = data.get("bme280", {})
        soil     = data.get("soil", {})
        wind     = data.get("wind", {})
        pressure = data.get("pressure", {})
        battery  = data.get("battery", {})
        flame    = data.get("flame", {})
        rainfall_delta_mm = None
        try:
            rainfall_delta_mm = api_payload["telemetry"][0].get("rainfall")
        except (KeyError, IndexError, TypeError):
            pass

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO sensor_readings (
                timestamp, device_id,
                mq2_voltage, mq2_ppm,
                mq135_voltage, mq135_ppm,
                temperature_c, humidity_pct, pressure_hpa,
                soil_surface_pct, soil_deep_pct,
                wind_speed_ms, wind_direction,
                water_current_ma, water_depth_m, water_pressure_bar, water_fault_open,
                battery_voltage, battery_pct,
                flame_detected, rainfall_delta_mm,
                full_payload
            ) VALUES (
                ?,?,  ?,?,  ?,?,  ?,?,?,  ?,?,  ?,?,  ?,?,?,?,  ?,?,  ?,?,  ?
            )
        """, (
            datetime.now(timezone.utc).isoformat(),
            settings.DEVICE_ID,

            mq2.get("voltage"), mq2.get("ppm"),
            mq135.get("voltage"), mq135.get("ppm"),
            bme.get("temperature_c"), bme.get("humidity_percent"), bme.get("pressure_hpa"),
            soil.get("surface", {}).get("moisture_percent"),
            soil.get("deep", {}).get("moisture_percent"),
            wind.get("speed_ms"), data.get("wind_dir", {}).get("direction_abbr"),
            pressure.get("current_ma"), pressure.get("depth_m"), pressure.get("pressure_bar"),
            int(bool(pressure.get("fault_open_loop", False))),
            battery.get("voltage"), battery.get("percent"),
            int(bool(flame.get("flame_detected", False))) if flame.get("flame_detected") is not None else None,
            rainfall_delta_mm,
            json.dumps(api_payload, default=str),
        ))
        self.conn.commit()
        return cur.lastrowid

    # ─── Logging location (Location Publisher) ────────────────────
    def log_location(self, location: dict, api_payload: dict) -> int:
        """
Save every time Location Publisher TRY sends -- regardless
whether delivery succeeds or fails (if it fails, it is still recorded here AND
enter api_queue via a separate retry mechanism).
        - location:    dict {"lat", "lon", "source", "fix"} (self._location
belongs to EFWS in main.py).
- api_payload: EXACT payload sent to API (for auditing).
        Return: row id.
        """
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO location_log (
                timestamp, device_id, latitude, longitude, source, fix, full_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            settings.DEVICE_ID,
            location.get("lat"),
            location.get("lon"),
            location.get("source"),
            int(bool(location.get("fix", False))),
            json.dumps(api_payload, default=str),
        ))
        self.conn.commit()
        return cur.lastrowid

    # ─── API queue (offline buffer) ───────────────────────────────
    def queue_api(self, endpoint: str, payload: dict):
        """Save the payload to the offline queue AS IS (not changed/recalculated)."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO api_queue (timestamp, endpoint, payload)
            VALUES (?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            endpoint,
            json.dumps(payload, default=str),
        ))
        self.conn.commit()

    def get_pending_queue(self, limit: int = 20) -> list:
        """Retrieve unsent queue (FIFO). Items that fail >10x are passed (considered stale)."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, endpoint, payload, attempts
            FROM   api_queue
            WHERE  sent = 0 AND attempts < 10
            ORDER  BY id ASC
            LIMIT  ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def count_pending_queue(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM api_queue WHERE sent=0 AND attempts < 10")
        return cur.fetchone()[0]

    def mark_queue_sent(self, queue_id: int):
        self.conn.execute("UPDATE api_queue SET sent=1 WHERE id=?", (queue_id,))
        self.conn.commit()

    def mark_queue_failed(self, queue_id: int, error: str):
        self.conn.execute(
            "UPDATE api_queue SET attempts=attempts+1, last_error=? WHERE id=?",
            (error, queue_id)
        )
        self.conn.commit()

    # ─── Query helpers ────────────────────────────────────────────
    def recent_readings(self, limit: int = 20) -> list:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, timestamp, mq2_ppm, mq135_ppm,
                   temperature_c, humidity_pct,
                   soil_surface_pct, soil_deep_pct, wind_speed_ms,
                   water_depth_m, water_fault_open, battery_pct
            FROM   sensor_readings
            ORDER  BY id DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        self.conn.close()

    # ─── Retensi data (auto-cleanup) ──────────────────────────────
    def purge_old_data(self, days: int = 3) -> dict:
        """
Delete row OLD (older than `days` days) from the local database.
Called automatically by the background thread (main.py:
EFWS._retention_loop), instead of deleting the database file itself --
only the old rows in it, so that the data is latest (<= `days` days)
persists and the file size does not continue to swell.

- sensor_readings : all rows older than cutoff are deleted.
- api_queue : ONLY rows whose status is "completed"
(sent=1, or attempts>=10 aka considered
permanently failed) are removed. Items are still available
actively waiting for retry NOT to be deleted though
it's more than `days` days old, so don't
Loss of data that has not been sent.

        Return: {"sensor_readings_deleted": int, "api_queue_deleted": int}
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self.conn.cursor()

        cur.execute("DELETE FROM sensor_readings WHERE timestamp < ?", (cutoff,))
        deleted_readings = cur.rowcount

        cur.execute(
            "DELETE FROM api_queue WHERE timestamp < ? AND (sent = 1 OR attempts >= 10)",
            (cutoff,),
        )
        deleted_queue = cur.rowcount

        cur.execute("DELETE FROM location_log WHERE timestamp < ?", (cutoff,))
        deleted_location = cur.rowcount

        self.conn.commit()
        if deleted_readings or deleted_queue or deleted_location:
            self.conn.execute("VACUUM")  # reduce size of .db file after delete

        return {
            "sensor_readings_deleted": deleted_readings,
            "api_queue_deleted": deleted_queue,
            "location_log_deleted": deleted_location,
        }
