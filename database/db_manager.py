"""
SQLite local data logger untuk EFWS.

Prinsip alur data:
  baca sensor → SIMPAN ke DB dulu (sensor_readings, sumber kebenaran lokal)
              → coba kirim ke API
              → gagal (sinyal mati)? → masuk antrian (api_queue), payload
                disimpan APA ADANYA (JSON persis) supaya waktu di-flush
                ulang nanti datanya tidak berubah sedikit pun
              → EFWSPublisher cek sinyal ulang tiap EFWS_CONNECTIVITY_CHECK_SEC
                (default 2 menit) lalu auto flush kalau sudah online lagi.

TIDAK menyimpan alarm_level / triggered_by / threshold apa pun — evaluasi
alarm & threshold sekarang murni tanggung jawab backend. Device cuma
mengevaluasi status secara LOKAL (main.py) untuk menyalakan sirine secara
real-time, tanpa mempersistensikannya di sini.
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

        # Tabel utama: satu baris per siklus baca, kolom per sensor mentah.
        # Tidak ada kolom status/alarm/threshold — itu urusan backend.
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
                water_current_ma  REAL,
                water_depth_m     REAL,
                water_fault_open  INTEGER,
                battery_voltage   REAL,
                battery_pct       REAL,
                full_payload      TEXT    -- JSON PERSIS yang dikirim ke API (untuk audit)
            )
        """)

        # Antrian pengiriman API yang gagal (offline buffer)
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

        cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts ON sensor_readings(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_queue_sent  ON api_queue(sent)")

        self.conn.commit()

    # ─── Logging sensor readings ──────────────────────────────────
    def log_reading(self, data: dict, api_payload: dict) -> int:
        """
        Simpan satu siklus baca ke database SEBELUM dicoba dikirim ke API.
        - data:        dict hasil EFWS._read_all() → {"mq2":{...}, "mq135":{...},
                       "bme280":{...}, "soil":{"surface":{...},"deep":{...}},
                       "wind":{...}, "pressure":{...}, "battery":{...}}
        - api_payload: payload PERSIS yang akan dikirim ke API, disimpan utuh
                       di kolom full_payload untuk audit/pembanding dengan isi
                       antrian offline.
        Return: row id.
        """
        mq2      = data.get("mq2", {})
        mq135    = data.get("mq135", {})
        bme      = data.get("bme280", {})
        soil     = data.get("soil", {})
        wind     = data.get("wind", {})
        pressure = data.get("pressure", {})
        battery  = data.get("battery", {})

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO sensor_readings (
                timestamp, device_id,
                mq2_voltage, mq2_ppm,
                mq135_voltage, mq135_ppm,
                temperature_c, humidity_pct, pressure_hpa,
                soil_surface_pct, soil_deep_pct,
                wind_speed_ms,
                water_current_ma, water_depth_m, water_fault_open,
                battery_voltage, battery_pct,
                full_payload
            ) VALUES (
                ?,?,  ?,?,  ?,?,  ?,?,?,  ?,?,  ?,  ?,?,?,  ?,?,  ?
            )
        """, (
            datetime.now(timezone.utc).isoformat(),
            settings.DEVICE_ID,

            mq2.get("voltage"), mq2.get("ppm"),
            mq135.get("voltage"), mq135.get("ppm"),
            bme.get("temperature_c"), bme.get("humidity_percent"), bme.get("pressure_hpa"),
            soil.get("surface", {}).get("moisture_percent"),
            soil.get("deep", {}).get("moisture_percent"),
            wind.get("speed_ms"),
            pressure.get("current_ma"), pressure.get("depth_m"),
            int(bool(pressure.get("fault_open_loop", False))),
            battery.get("voltage"), battery.get("percent"),
            json.dumps(api_payload, default=str),
        ))
        self.conn.commit()
        return cur.lastrowid

    # ─── API queue (offline buffer) ───────────────────────────────
    def queue_api(self, endpoint: str, payload: dict):
        """Simpan payload ke antrian offline APA ADANYA (tidak diubah/dihitung ulang)."""
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
        """Ambil antrian yang belum terkirim (FIFO). Item gagal >10x dilewati (dianggap stale)."""
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
