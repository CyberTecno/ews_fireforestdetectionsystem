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
print("ROOT :", _ROOT)
print("EFWS_API_URL =", os.getenv("EFWS_API_URL"))


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
#   LLC (HV=5V, LV=3.3V) — semua sensor analog 0-5V:
#     HV-1 → LV-1 : MQ-2   AOUT                    → CH0
#     HV-2 → LV-2 : MQ-135 AOUT                     → CH1
#     HV-3 → LV-3 : Soil Surface AOUT                → CH2
#     HV-4 → LV-4 : Soil Deep    AOUT                → CH3
#     HV-5 → LV-5 : Pressure sensor (lewat R_BURDEN) → CH4
#     HV-6 → LV-6 : Voltage Sensor Module OUT         → CH5
#     HV-7..8 / CH6-CH7 : spare, tidak dikabel
SPI_BUS          = _int("EFWS_SPI_BUS", 0)
SPI_DEVICE       = _int("EFWS_SPI_DEVICE", 0)
SPI_MAX_SPEED_HZ = _int("EFWS_SPI_SPEED", 1350000)
MCP3008_VREF     = _float("EFWS_MCP3008_VREF", 3.3)

ADC_CHANNEL_MQ2             = _int("EFWS_ADC_MQ2",          0)   # LLC HV-1
ADC_CHANNEL_MQ135           = _int("EFWS_ADC_MQ135",         1)   # LLC HV-2
ADC_CHANNEL_SOIL_SURFACE    = _int("EFWS_ADC_SOIL_SURFACE",  2)   # LLC HV-3 (probe 0-30cm)
ADC_CHANNEL_SOIL_DEEP       = _int("EFWS_ADC_SOIL_DEEP",     3)   # LLC HV-4 (probe 30-60cm)
ADC_CHANNEL_PRESSURE        = _int("EFWS_ADC_PRESSURE",      4)   # LLC HV-5 (pressure sensor via R_BURDEN)
ADC_CHANNEL_BATTERY         = _int("EFWS_ADC_BATTERY",       5)   # LLC HV-6 (voltage sensor module OUT)
# CH6-CH7 tidak dikabel — spare fisik di MCP3008

# ─── Battery — Modul Sensor Tegangan DC 0-25V ────────────────────────────────
BATTERY_SENSOR_MAX_V = _float("EFWS_BATTERY_SENSOR_MAX_V", 25.0)  # max input modul sensor (V)
BATTERY_MAX_V        = _float("EFWS_BATTERY_MAX_V",        12.6)  # tegangan baterai penuh (V)
BATTERY_MIN_V        = _float("EFWS_BATTERY_MIN_V",         9.0)  # tegangan baterai kosong (V)

# ─── Submersible Pressure Sensor — loop 4-20mA ──────────────────────────────
# Sensor loop-powered 2-kabel, dibaca via burden resistor presisi lalu LLC
# (lihat sensors/pressure.py untuk detail kalkulasi & wiring).
PRESSURE_BURDEN_OHM = _float("EFWS_PRESSURE_BURDEN_OHM", 250.0)  # 4mA→1V, 20mA→5V
PRESSURE_MIN_MA     = _float("EFWS_PRESSURE_MIN_MA",       4.0)
PRESSURE_MAX_MA     = _float("EFWS_PRESSURE_MAX_MA",      20.0)
PRESSURE_RANGE_M    = _float("EFWS_PRESSURE_RANGE_M",      5.0)  # rentang penuh sensor, sesuaikan datasheet

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

# ─── Anemometer RS485 ────────────────────────────────────────────────────────
ANEMOMETER_PORT     = _opt("EFWS_ANEM_PORT", "/dev/ttyUSB0")
ANEMOMETER_BAUDRATE = _int("EFWS_ANEM_BAUD", 4800)
ANEMOMETER_SLAVE_ID = _int("EFWS_ANEM_SLAVE", 1)
ANEMOMETER_REGISTER = int(_opt("EFWS_ANEM_REG", "0x0000"), 16)

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

# ─── Log files ───────────────────────────────────────────────────────────────
LOG_PATH = _opt("EFWS_LOG_PATH", str(_ROOT / "logs" / "efws.log"))

# ─── Timing ──────────────────────────────────────────────────────────────────
# Siklus CEK sensor -- selalu jalan tiap interval ini, murni evaluasi
# threshold (cepat, demi deteksi darurat responsif). TIDAK selalu berarti
# kirim data -- lihat ROUTINE_SEND_INTERVAL_SEC di bawah.
SENSOR_READ_INTERVAL_SEC = _int("EFWS_READ_INTERVAL", 180)

# Siklus KIRIM rutin (location+telemetry+heartbeat) saat kondisi NORMAL --
# SENGAJA dipisah dari SENSOR_READ_INTERVAL_SEC: threshold tetap dicek tiap
# 3 menit (respons cepat kalau darurat), tapi kalau semua normal, device
# cukup lapor ke backend tiap ROUTINE_SEND_INTERVAL_SEC (default 3600s /
# 60 menit) supaya tidak terlihat mati/hilang tanpa membanjiri API.
# Begitu ada threshold yang dilewati, kirim LANGSUNG saat itu juga
# ("emergency upload") tanpa menunggu jadwal rutin ini, dan jadwal rutin
# di-reset dari titik itu (karena backend baru saja menerima laporan).
ROUTINE_SEND_INTERVAL_SEC = _int("EFWS_ROUTINE_SEND_INTERVAL_SEC", 360)

# Retry offline queue -- berjalan di thread TERPISAH dari siklus baca sensor
# (lihat main.py EFWS._flush_queue_loop), supaya tetap tiap 2 menit persis
# walau siklus baca sekarang 3 menit.
EFWS_CONNECTIVITY_CHECK_SEC = _int("EFWS_CONNECTIVITY_CHECK_SEC", 120)

# ─── Command executor (endpoint 4: /sensors/commands/ack) ──────────────────
# Delay sebelum benar-benar restart setelah command "Reboot" diterima.
# Kenapa perlu delay: proses ini harus sempat MENGIRIM ack SUCCESS dulu
# sebelum systemctl restart membunuh proses Python yang sedang jalan.
# Lihat main.py: EFWS._cmd_reboot() untuk detail.
COMMAND_REBOOT_DELAY_SEC = _int("EFWS_REBOOT_DELAY_SEC", 5)

# ─── Threshold file ──────────────────────────────────────────────────────────
THRESHOLDS_PATH = str(_ROOT / "config" / "thresholds.json")
