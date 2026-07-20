"""
NullSensor — fallback kalau sensor fisik GAGAL diinisialisasi
(tidak terpasang, driver tidak ada, port/bus tidak ketemu saat startup).

Tujuan: supaya EFWS tetap bisa jalan walau salah satu sensor (apapun itu)
tidak ada, tanpa harus mengubah kode payload builder / threshold evaluator
di main.py sama sekali.

PENTING soal tipe data: semua field numerik di bawah SELALU bernilai Python
`None` (bukan string "None", bukan pesan error). `None` -> JSON `null` dan
SQLite `NULL` secara otomatis, jadi kolom REAL/float tidak pernah menerima
teks. Pesan error/alasan kenapa sensor tidak terbaca HANYA disimpan di key
terpisah `"error"` (bertipe string), TIDAK PERNAH dicampur ke field angka.

SENSOR_SCHEMAS mendaftarkan field apa saja yang harusnya ada di setiap
sensor (persis sama dengan bentuk return sensor aslinya saat sukses), biar
NullSensor.read() selalu mengembalikan bentuk (shape) yang identik --
lengkap dengan semua key, cuma isinya null -- baik diakses lewat
`.get(...)` maupun langsung `dict[...]`.
"""

SENSOR_SCHEMAS = {
    "mq2":      {"voltage": None, "ppm": None},
    "mq135":    {"voltage": None, "ppm": None},
    "bme280":   {"temperature_c": None, "humidity_percent": None, "pressure_hpa": None},
    "pressure": {"current_ma": None, "depth_m": None, "pressure_bar": None, "fault_open_loop": None},
    "soil": {
        "surface": {"raw": None, "moisture_percent": None},
        "deep":    {"raw": None, "moisture_percent": None},
    },
    "wind":    {"speed_ms": None},
    "battery": {"voltage": None, "percent": None},
}


class NullSensor:
    def __init__(self, name: str, reason: str):
        self.name = name
        self.reason = reason
        self._fields = SENSOR_SCHEMAS.get(name, {})

    def read(self) -> dict:
        # Copy dangkal cukup: semua isi field adalah None (immutable) atau
        # dict nested yang juga cuma berisi None, jadi aman tidak dimutasi.
        result = dict(self._fields)
        result["error"] = (
            f"sensor '{self.name}' tidak terbaca/tidak terpasang: {self.reason}"
        )
        return result


class NullAlarmController:
    """Fallback kalau relay/sirine gagal diinisialisasi — alarm lokal jadi no-op,
    tapi status level tetap dicatat, supaya operator tahu."""

    current_level = "none"

    def __init__(self, reason: str):
        self.reason = reason

    def set_level(self, level: str):
        self.current_level = level

    def silence(self):
        self.current_level = "none"
