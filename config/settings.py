"""
Global configuration untuk EFWS.
Semua nilai sensitif dibaca dari file .env (via python-dotenv).
File .env TIDAK boleh di-commit ke git — lihat .env.example untuk templatenya.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Cari .env secara otomatis (naik folder sampai ketemu) ───────────────────
def _find_and_load_dotenv():
    """
    Cari file .env mulai dari lokasi settings.py, naik ke atas sampai 2 level.
    Ini agar tidak peduli seberapa dalam struktur folder project-nya.
    """
    search_start = Path(__file__).resolve().parent  # mulai dari config/
    for candidate in [search_start, *search_start.parents[:2]]:
        env_file = candidate / ".env"
        if env_file.exists():
            print(f"✅  Found .env at {env_file}, loading...")
            load_dotenv(env_file, override=True)
            return candidate   # return root yang ditemukan
    # Tidak ketemu .env — load_dotenv tetap jalan (baca dari env var sistem saja)
    print("❌  .env not found, using system environment variables only.")
    load_dotenv(override=True)
    return search_start

_ROOT = _find_and_load_dotenv()


# ─── Helper ──────────────────────────────────────────────────────────────────
def _req(key: str) -> str:
    """Baca env var wajib. Raise error jelas jika tidak ada."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"\n\n  ❌  Environment variable '{key}' tidak ditemukan.\n"
            f"      Pastikan file .env ada di root project dan sudah diisi.\n"
            f"      Contoh: cp .env.example .env\n"
        )
    return val

def _opt(key: str, default: str = "") -> str:
    return os.getenv(key, default)

def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))

def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))

def _bool(key: str, default: bool = True) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


# ─── Device Identity ─────────────────────────────────────────────────────────
DEVICE_ID    = _opt("EFWS_DEVICE_ID",    "DEV-JAM-TEST02")
DEVICE_TOKEN = _opt("EFWS_DEVICE_TOKEN", "test")

DEVICE_LOCATION = {
    "lat": _float("EFWS_LAT", 0.0),
    "lon": _float("EFWS_LON", 0.0),
}

# ─── GPS acquisition (Location Publisher) ──────────────────────────────────
# Dikonfirmasi dari pengalaman lapangan user: cold-fix GPS lewat modul
# A7670E/SIM7600 biasanya butuh 2 percobaan, masing-masing 2-5 menit. Jadi
# defaultnya BUKAN satu percobaan singkat -- 2 percobaan @ 4 menit (tengah
# rentang 2-5 menit), baru dianggap gagal kalau keduanya tidak fix.
GPS_FIX_ATTEMPTS    = _int("EFWS_GPS_FIX_ATTEMPTS",    2)
GPS_TIMEOUT_SEC     = _int("EFWS_GPS_TIMEOUT_SEC",     240)  # detik PER percobaan (4 menit)
GPS_RETRY_DELAY_SEC = _int("EFWS_GPS_RETRY_DELAY_SEC", 10)   # jeda sebelum percobaan berikutnya

# ─── Mode operasi ────────────────────────────────────────────────────────────
RUN_MODE = _opt("EFWS_RUN_MODE", "mock")

# ─── I2C (BME280 — suhu/kelembaban/tekanan ambient, native I2C) ────────────
I2C_BUS        = _int("EFWS_I2C_BUS", 1)
BME280_ADDRESS = int(_opt("EFWS_BME280_ADDR", "0x76"), 16)

# ─── SPI / MCP3008 (ADC 8-channel, SATU Logic Level Converter) ─────────────
# Versi hardware: 1x MCP3008, 1x LLC (min. 6-channel, mis. modul 8-ch),
# 2x soil probe, MQ-2, MQ-135, anemometer RS485 (langsung USB, tanpa LLC),
# submersible pressure sensor (loop 4-20mA + burden resistor), modul sensor
# tegangan baterai DC 0-25V, dan modem 4G (A7670E ATAU SIM7600 — auto-detect,
# hanya satu yang dipasang).
#
#   LLC (HV=5V, LV=3.3V) — 4 channel, HANYA untuk sensor analog 0-5V yang
#   genuinely butuh step-down (MQ-2, MQ-135, soil x2). Pressure & Battery
#   TIDAK lewat LLC ini (lihat catatan masing-masing di bawah).
#     LLC CH1 : MQ-2   AOUT                    → MCP3008 CH0
#     LLC CH2 : MQ-135 AOUT                     → MCP3008 CH1
#     LLC CH3 : Soil Surface AOUT                → MCP3008 CH2
#     LLC CH4 : Soil Deep    AOUT                → MCP3008 CH3
#   (LLC modul fisik cuma 4 channel, sudah penuh terpakai di atas)
#
#   TANPA LLC (langsung ke MCP3008):
#     Pressure sensor (lewat R_BURDEN 100 Ohm)   → MCP3008 CH4
#     Voltage Sensor Module "S" (native 3.3V)     → MCP3008 CH5
#     Flame sensor AO (native 3.3V)               → MCP3008 CH6
#   MCP3008 CH7 : spare, tidak dikabel
SPI_BUS          = _int("EFWS_SPI_BUS", 0)
SPI_DEVICE       = _int("EFWS_SPI_DEVICE", 0)
SPI_MAX_SPEED_HZ = _int("EFWS_SPI_SPEED", 1350000)
MCP3008_VREF     = _float("EFWS_MCP3008_VREF", 3.3)

ADC_CHANNEL_MQ2             = _int("EFWS_ADC_MQ2",          0)   # LLC CH1
ADC_CHANNEL_MQ135           = _int("EFWS_ADC_MQ135",         1)   # LLC CH2
ADC_CHANNEL_SOIL_SURFACE    = _int("EFWS_ADC_SOIL_SURFACE",  2)   # LLC CH3 (probe 0-30cm)
ADC_CHANNEL_SOIL_DEEP       = _int("EFWS_ADC_SOIL_DEEP",     3)   # LLC CH4 (probe 30-60cm)
ADC_CHANNEL_PRESSURE        = _int("EFWS_ADC_PRESSURE",      4)   # LANGSUNG ke MCP3008 CH4 lewat R_BURDEN 100 Ohm, TIDAK lewat LLC
ADC_CHANNEL_BATTERY         = _int("EFWS_ADC_BATTERY",       5)   # LANGSUNG ke MCP3008 CH5, TIDAK lewat LLC (lihat catatan di sensors/battery.py)
ADC_CHANNEL_FLAME_AO   = _int("EFWS_ADC_FLAME_AO", 6)          # MCP3008 CH6, langsung tanpa LLC. CH7 = spare.
# CH7 spare (fisik kosong, di ujung setelah flame)

# ─── Gravity Rainfall Sensor (DFRobot SEN0575) ─────────────────────────────
# (I2C_BUS dipakai bersama dengan BME280 -- lihat definisi di atas, TIDAK
# didefinisikan ulang di sini lagi. Sebelumnya ada baris "I2C_BUS = 1" di
# sini yang diam-diam menimpa nilai EFWS_I2C_BUS dari .env -- sudah dihapus.)
RAINFALL_I2C_ADDRESS = 0x1D
# Interval pembacaan (detik)
RAINFALL_READ_INTERVAL = 2

# ─── Battery — Modul Sensor Tegangan DC 0-25V (voltage divider 5:1) ────────
# DIKONFIRMASI dari datasheet resmi modul ini (osoyoo.com/2024/09/08/lesson-13-
# voltage-sensor-for-raspberry-pi/): rasio pembagi tegangan modul = 1/5 TETAP
# (bukan tergantung VREF). Modul ini punya batas input aman "less than 16.5V"
# ketika ADC-nya diberi VREF 3.3V (3.3 x 5 = 16.5V) -- BUKAN 25V seperti nilai
# lama di sini. Nilai lama (25.0) salah dan akan menghasilkan V_battery yang
# under-read sekitar 34%. Kalau modul fisik Anda beda merek/rasio, sesuaikan
# lewat EFWS_BATTERY_SENSOR_MAX_V.
BATTERY_SENSOR_MAX_V = _float("EFWS_BATTERY_SENSOR_MAX_V", 16.5)  # max input modul sensor (V) @ VREF 3.3V, rasio 1:5
# BATTERY_MAX_V DIKONFIRMASI user: catu daya/baterai fisiknya max 14.4V
BATTERY_MAX_V        = _float("EFWS_BATTERY_MAX_V",        14.4)  # tegangan baterai penuh (V)
BATTERY_MIN_V        = _float("EFWS_BATTERY_MIN_V",         10.7)  # tegangan baterai kosong (V)

# ─── Submersible / Pressure Water Level Sensor — loop 4-20mA ───────────────
# CATATAN: submersible.py (script berdiri sendiri, pakai channel & rumus yang
# sama) sudah DIGABUNG ke sini / dihapus -- pressure.py adalah satu-satunya
# implementasi untuk sensor ini sekarang (lihat sensors/pressure.py).
PRESSURE_BURDEN_OHM = _float("EFWS_PRESSURE_BURDEN_OHM",     100.0)  # 4mA→1V, 20mA→5V
PRESSURE_MIN_MA     = _float("EFWS_PRESSURE_MIN_MA",       4.032)
PRESSURE_MAX_MA     = _float("EFWS_PRESSURE_MAX_MA",      20.0)
PRESSURE_RANGE_M    = _float("EFWS_PRESSURE_RANGE_M",      3.0)  # rentang penuh sensor, sesuaikan datasheet

# ─── Flame Sensor (IR, dibaca via AO/analog di MCP3008 CH6) ───────────────
# Keputusan user: pakai AO lewat MCP3008 CH6, BUKAN lewat GPIO digital DO.
# Threshold voltase BELUM dikalibrasi ke unit fisik -- lihat comment
# kalibrasi di sensors/flame.py sebelum dipakai di lapangan.
FLAME_AO_THRESHOLD_V   = _float("EFWS_FLAME_AO_THRESHOLD_V", 1.65)  # PERKIRAAN AWAL (setengah VREF) -- WAJIB dikalibrasi ulang di lapangan

# ─── smokeLevel: gabungan MQ-2 + MQ-135 → persentase 0-100% ────────────────
# Formula: smokeLevel = (mq2_ppm/MQ2_CRIT * W_MQ2 + mq135_ppm/MQ135_CRIT * W_MQ135) * 100
# Batas:   60-70% = WARNING, ≥70% = CRITICAL, 100% = kedua sensor di angka critical threshold
SMOKE_MQ2_CRIT_PPM   = _float("EFWS_SMOKE_MQ2_CRIT",   1000.0)
SMOKE_MQ135_CRIT_PPM = _float("EFWS_SMOKE_MQ135_CRIT", 1000.0)
SMOKE_WEIGHT_MQ2     = _float("EFWS_SMOKE_W_MQ2",       0.55)
SMOKE_WEIGHT_MQ135   = _float("EFWS_SMOKE_W_MQ135",     0.45)
SMOKE_WARNING_PCT    = _float("EFWS_SMOKE_WARN",         60.0)
SMOKE_CRITICAL_PCT   = _float("EFWS_SMOKE_CRIT",         70.0)

GPIO_RELAY_SIREN  = _int("EFWS_GPIO_RELAY",  27)
GPIO_STATUS_LED   = _int("EFWS_GPIO_LED",    23)

# ─── Wind Direction Sensor -- UART GPIO14(TXD)/GPIO15(RXD), pin 8/10 ────────
# VCC(merah)->3.3V, GND(hitam)->GND, TX(kuning)->GPIO14/pin8, RX(hijau)->GPIO15/pin10.
# PENTING: pastikan Bluetooth di-nonaktifkan (dtoverlay=disable-bt) dan
# console serial dimatikan di raspi-config, atau port ini bentrok/baudrate
# drift. Lihat catatan lengkap di sensors/wind_direction.py.
WIND_DIR_PORT     = _opt("EFWS_WIND_DIR_PORT", "/dev/serial0")
WIND_DIR_BAUDRATE = _int("EFWS_WIND_DIR_BAUD", 9600)
WIND_DIR_TIMEOUT  = _float("EFWS_WIND_DIR_TIMEOUT", 1.0)

# ─── Anemometer RS485 ────────────────────────────────────────────────────────

ANEMOMETER_PORT = _opt(
    "EFWS_ANEM_PORT",
    "/dev/ttyUSB0"
)

ANEMOMETER_SLAVE_ID = _int(
    "EFWS_ANEM_SLAVE",
    2
)

ANEMOMETER_BAUDRATE = _int(
    "EFWS_ANEM_BAUD",
    9600
)

ANEMOMETER_BYTESIZE = _int(
    "EFWS_ANEM_BYTESIZE",
    8
)

ANEMOMETER_STOPBITS = _int(
    "EFWS_ANEM_STOPBITS",
    1
)

ANEMOMETER_TIMEOUT = _float(
    "EFWS_ANEM_TIMEOUT",
    1.0
)

ANEMOMETER_REGISTER = int(
    _opt(
        "EFWS_ANEM_REGISTER",
        "0x0000"
    ),
    16
)

ANEMOMETER_DECIMALS = _int(
    "EFWS_ANEM_DECIMALS",
    1
)

ANEMOMETER_FUNCTION_CODE = _int(
    "EFWS_ANEM_FUNCTION",
    3
)

# ─── A7670E / SIM7670E 4G LTE Cat-1 ──────────────────────────────────────────────────────────
A7670E_AT_PORT  = _opt("EFWS_SIM_PORT", "/dev/ttyUSB2")
A7670E_BAUDRATE = _int("EFWS_A7670E_BAUD", 115200)
APN              = _opt("EFWS_APN", "internet")

# ─── REST API ────────────────────────────────────────────────────────────────
API_BASE_URL       = _req("EFWS_API_URL")
# CATATAN: endpoint URL SENGAJA tidak didefinisikan sebagai konstanta
# modul, tapi lewat fungsi dinamis di bawah, supaya URL yang berlaku saat
# runtime selalu memakai EFWS_API_URL terkini dari env — termasuk kalau
# .env diubah dan service di-restart. Ada 4 endpoint:
#   telemetry_endpoint()   -> /sensors/telemetry     (scheduled, bawa config remote)
#   location_endpoint()    -> /sensors/location       (scheduled)
#   heartbeat_endpoint()   -> /sensors/heartbeat      (scheduled, bawa commands)
#   command_ack_endpoint() -> /sensors/commands/ack   (event-driven, dari commands)

def _base_url() -> str:
    return os.getenv("EFWS_API_URL", API_BASE_URL).rstrip("/")

def telemetry_endpoint() -> str:
    """Data sensor + smokeLevel dsb. Response-nya membawa 'config' (threshold remote)."""
    return _base_url() + "/sensors/telemetry"

def location_endpoint() -> str:
    """Update posisi GPS/fallback device."""
    return _base_url() + "/sensors/location"

def heartbeat_endpoint() -> str:
    """Health check + tempat backend menitipkan 'commands' (mis. Reboot)."""
    return _base_url() + "/sensors/heartbeat"

def command_ack_endpoint() -> str:
    """ACK hasil eksekusi command yang diterima lewat heartbeat. Event-driven, tidak scheduled."""
    return _base_url() + "/sensors/commands/ack"

API_SECRET_KEY     = _opt("EFWS_API_KEY", "")
API_VERIFY_SSL     = _bool("EFWS_VERIFY_SSL", True)
API_TIMEOUT_SEC    = _int("EFWS_API_TIMEOUT", 10)
API_MAX_RETRIES    = _int("EFWS_API_RETRIES", 3)
API_RETRY_DELAY    = _int("EFWS_API_RETRY_DELAY", 5)

# ─── Database lokal ──────────────────────────────────────────────────────────
DB_PATH = _opt("EFWS_DB_PATH", str(_ROOT / "database" / "efws_data.db"))

# Retensi data lokal -- baris sensor_readings & api_queue (yang statusnya
# sudah selesai: terkirim ATAU sudah dibuang permanen) yang lebih tua dari
# ini otomatis DIHAPUS oleh background thread (lihat main.py:
# EFWS._retention_loop). Ini menghapus BARIS-BARIS lama di dalam database,
# BUKAN menghapus file database itu sendiri -- tabel & data terbaru tetap ada.
DB_RETENTION_DAYS        = _int("EFWS_DB_RETENTION_DAYS", 3)
DB_RETENTION_CHECK_SEC   = _int("EFWS_DB_RETENTION_CHECK_SEC", 6 * 3600)  # cek tiap 6 jam

# ─── Log files ───────────────────────────────────────────────────────────────
LOG_PATH = _opt("EFWS_LOG_PATH", str(_ROOT / "logs" / "efws.log"))

# ─── Timing ──────────────────────────────────────────────────────────────────
# Siklus CEK sensor -- selalu jalan tiap interval ini, murni evaluasi
# threshold (cepat, demi deteksi darurat responsif). TIDAK PERNAH kirim ke
# API dan TIDAK PERNAH simpan ke SQLite di sini -- itu tugas Telemetry
# Publisher (lihat di bawah). Siklus ini juga tidak lagi mengambil GPS --
# GPS hanya diambil oleh Location Publisher, tepat sebelum dikirim.
SENSOR_READ_INTERVAL_SEC = _int("EFWS_READ_INTERVAL", 180)

# ─── 3 scheduler independen (Location / Telemetry / Heartbeat) ────────────
# Masing-masing endpoint punya scheduler & thread SENDIRI (lihat main.py:
# EFWS._location_loop / _telemetry_loop / _heartbeat_loop). Tidak ada yang
# saling menunggu atau saling memicu satu sama lain.
#
# Location  -- SELALU tiap 30 menit, tidak terpengaruh Emergency Mode sama
#              sekali (spec: "Emergency Mode must never modify the execution
#              interval of Location or Heartbeat").
LOCATION_INTERVAL_SEC = _int("EFWS_LOCATION_INTERVAL_SEC", 1800)

# Telemetry -- 30 menit saat NORMAL. Saat Emergency Mode aktif, scheduler
#              yang SAMA (bukan scheduler kedua) beralih ke interval
#              EMERGENCY_TELEMETRY_INTERVAL_SEC di bawah, supaya tidak
#              mungkin ada dua pengiriman telemetry yang tumpang tindih.
TELEMETRY_INTERVAL_SEC = _int("EFWS_TELEMETRY_INTERVAL_SEC", 1800)

# Telemetry saat EMERGENCY -- 10 menit, HANYA endpoint ini yang berubah
# jadwalnya saat emergency (Location & Heartbeat tetap di jadwal normalnya).
EMERGENCY_TELEMETRY_INTERVAL_SEC = _int("EFWS_EMERGENCY_TELEMETRY_INTERVAL_SEC", 600)

# Heartbeat -- SELALU tiap 5 menit. Tidak pernah bergantung pada Telemetry,
# Location, ataupun Emergency Mode (spec eksplisit soal ini).
HEARTBEAT_INTERVAL_SEC = _int("EFWS_HEARTBEAT_INTERVAL_SEC", 300)

# Retry offline queue -- berjalan di thread TERPISAH dari siklus baca sensor
# maupun ketiga publisher di atas, tiap 2 menit (dikonfirmasi user).
EFWS_CONNECTIVITY_CHECK_SEC = _int("EFWS_CONNECTIVITY_CHECK_SEC", 120)

# ─── Command executor (endpoint 4: /sensors/commands/ack) ──────────────────
# Delay sebelum benar-benar restart setelah command "Reboot" diterima.
# Kenapa perlu delay: proses ini harus sempat MENGIRIM ack SUCCESS dulu
# sebelum systemctl restart membunuh proses Python yang sedang jalan.
# Lihat main.py: EFWS._cmd_reboot() untuk detail.
COMMAND_REBOOT_DELAY_SEC = _int("EFWS_REBOOT_DELAY_SEC", 5)

# ─── Threshold file ──────────────────────────────────────────────────────────
THRESHOLDS_PATH = str(_ROOT / "config" / "thresholds.json")
