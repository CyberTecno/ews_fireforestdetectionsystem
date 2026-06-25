"""
SQLite local data logger untuk EFWS.
Menyimpan data per-sensor dalam kolom terpisah (bukan hanya JSON blob)
agar mudah di-query, di-export, dan diaudit.
Juga menyimpan antrian (queue) payload yang gagal terkirim ke API,
sehingga bisa di-retry saat koneksi kembali.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone
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

        # Tabel utama: satu baris per siklus baca, kolom per sensor
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT    NOT NULL,
                device_id       TEXT    NOT NULL,
                -- MQ-2 (smoke/gas)
                mq2_voltage     REAL,
                mq2_ppm         REAL,
                mq2_status      TEXT,
                -- MQ-135 (air quality)
                mq135_voltage   REAL,
                mq135_ppm       REAL,
                mq135_status    TEXT,
                -- Flame sensor
                flame_detected  INTEGER,
                flame_raw       INTEGER,
                flame_status    TEXT,
                -- BME280
                temperature_c   REAL,
                humidity_pct    REAL,
                pressure_hpa    REAL,
                temp_status     TEXT,
                humidity_status TEXT,
                -- Soil moisture
                soil_raw        INTEGER,
                soil_moisture   REAL,
                soil_status     TEXT,
                -- Wind (anemometer)
                wind_speed_ms   REAL,
                wind_status     TEXT,
                -- Overall alarm
                alarm_level     TEXT,
                triggered_by    TEXT,   -- JSON array
                full_payload    TEXT    -- JSON lengkap untuk referensi
            )
        """)

        # Tabel alarm: hanya saat level warning/critical
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alarm_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT    NOT NULL,
                device_id    TEXT    NOT NULL,
                level        TEXT    NOT NULL,
                triggered_by TEXT    NOT NULL,
                reading_id   INTEGER REFERENCES sensor_readings(id),
                payload      TEXT
            )
        """)

        # Antrian pengiriman API yang gagal
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                endpoint    TEXT    NOT NULL,
                payload     TEXT    NOT NULL,
                priority    INTEGER DEFAULT 0,  -- 1 = alarm (prioritas tinggi)
                attempts    INTEGER DEFAULT 0,
                last_error  TEXT,
                sent        INTEGER DEFAULT 0
            )
        """)

        # Index agar query per waktu cepat
        cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts  ON sensor_readings(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alarms_ts    ON alarm_events(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_queue_sent   ON api_queue(sent)")

        self.conn.commit()

    # ─── Logging sensor readings ──────────────────────────────────
    def log_reading(self, payload: dict) -> int:
        """Simpan satu siklus baca ke database. Return row id."""
        s   = payload.get("sensors", {})
        st  = payload.get("statuses", {})
        alm = payload.get("alarm", {})

        mq2     = s.get("mq2", {})
        mq135   = s.get("mq135", {})
        flame   = s.get("flame", {})
        bme     = s.get("bme280", {})
        soil    = s.get("soil", {})
        wind    = s.get("wind", {})

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO sensor_readings (
                timestamp, device_id,
                mq2_voltage, mq2_ppm, mq2_status,
                mq135_voltage, mq135_ppm, mq135_status,
                flame_detected, flame_raw, flame_status,
                temperature_c, humidity_pct, pressure_hpa, temp_status, humidity_status,
                soil_raw, soil_moisture, soil_status,
                wind_speed_ms, wind_status,
                alarm_level, triggered_by, full_payload
            ) VALUES (
                ?,?,  ?,?,?,  ?,?,?,  ?,?,?,  ?,?,?,?,?,  ?,?,?,  ?,?,  ?,?,?
            )
        """, (
            payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
            payload.get("device_id", settings.DEVICE_ID),

            mq2.get("voltage"), mq2.get("ppm"), st.get("mq2"),
            mq135.get("voltage"), mq135.get("ppm"), st.get("mq135"),
            int(flame.get("flame_detected", False)), flame.get("raw"), st.get("flame"),
            bme.get("temperature_c"), bme.get("humidity_percent"), bme.get("pressure_hpa"),
            st.get("temperature"), st.get("humidity_low"),
            soil.get("raw"), soil.get("moisture_percent"), st.get("soil_dry"),
            wind.get("speed_ms"), st.get("wind"),
            alm.get("level"), json.dumps(alm.get("triggered_by", [])),
            json.dumps(payload, default=str),
        ))
        self.conn.commit()
        return cur.lastrowid

    # ─── Logging alarm events ─────────────────────────────────────
    def log_alarm(self, level: str, triggered_by: list, payload: dict, reading_id: int = None):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO alarm_events (timestamp, device_id, level, triggered_by, reading_id, payload)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            payload.get("device_id", settings.DEVICE_ID),
            level,
            json.dumps(triggered_by),
            reading_id,
            json.dumps(payload, default=str),
        ))
        self.conn.commit()

    # ─── API queue (offline buffer) ───────────────────────────────
    def queue_api(self, endpoint: str, payload: dict, priority: bool = False):
        """
        Simpan payload ke antrian offline.
        priority=True → alarm event, diutamakan saat flush (dikirim lebih dulu).
        """
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO api_queue (timestamp, endpoint, payload, priority)
            VALUES (?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            endpoint,
            json.dumps(payload, default=str),
            1 if priority else 0,
        ))
        self.conn.commit()

    def get_pending_queue(self, limit: int = 20) -> list:
        """
        Ambil antrian yang belum terkirim, alarm (priority=1) didahulukan.
        Item yang sudah gagal >10x dilewati (dianggap corrupt/stale).
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, endpoint, payload, attempts, priority
            FROM   api_queue
            WHERE  sent = 0 AND attempts < 10
            ORDER  BY priority DESC, id ASC
            LIMIT  ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def count_pending_queue(self) -> int:
        """Jumlah item di antrian yang belum terkirim."""
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
            SELECT id, timestamp, alarm_level, mq2_ppm, mq135_ppm,
                   flame_detected, temperature_c, humidity_pct,
                   soil_moisture, wind_speed_ms
            FROM   sensor_readings
            ORDER  BY id DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def recent_alarms(self, limit: int = 10) -> list:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, timestamp, level, triggered_by
            FROM   alarm_events
            ORDER  BY id DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        self.conn.close()
