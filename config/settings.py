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
    Cari file .env mulai dari lokasi settings.py, naik ke atas sampai 5 level.
    Ini agar tidak peduli seberapa dalam struktur folder project-nya.
    """
    search_start = Path(__file__).resolve().parent  # mulai dari config/
    for candidate in [search_start, *search_start.parents[:5]]:
        env_file = candidate / ".env"
        if env_file.exists():
            print(f"✅  Found .env at {env_file}, loading...")
            load_dotenv(env_file, override=False)
            return candidate   # return root yang ditemukan
    # Tidak ketemu .env — load_dotenv tetap jalan (baca dari env var sistem saja)
    print("❌  .env not found, using system environment variables only.")
    load_dotenv(override=False)
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
DEVICE_ID = _opt("EFWS_DEVICE_ID", "efws-001")
DEVICE_LOCATION = {
    "lat": _float("EFWS_LAT", 0.0),
    "lon": _float("EFWS_LON", 0.0),
}

# ─── Mode operasi ────────────────────────────────────────────────────────────
RUN_MODE = _opt("EFWS_RUN_MODE", "mock")

# ─── I2C / GPIO ──────────────────────────────────────────────────────────────
I2C_BUS           = _int("EFWS_I2C_BUS", 1)
BME280_ADDRESS    = int(_opt("EFWS_BME280_ADDR", "0x76"), 16)
ADS1115_ADDRESS   = int(_opt("EFWS_ADS1115_ADDR", "0x48"), 16)

ADC_CHANNEL_MQ2   = _int("EFWS_ADC_MQ2",   0)
ADC_CHANNEL_MQ135 = _int("EFWS_ADC_MQ135", 1)
ADC_CHANNEL_SOIL  = _int("EFWS_ADC_SOIL",  2)

GPIO_FLAME_SENSOR = _int("EFWS_GPIO_FLAME",  17)
GPIO_RELAY_SIREN  = _int("EFWS_GPIO_RELAY",  27)
GPIO_BUZZER       = _int("EFWS_GPIO_BUZZER", 22)
GPIO_STATUS_LED   = _int("EFWS_GPIO_LED",    23)

# ─── Anemometer RS485 ────────────────────────────────────────────────────────
ANEMOMETER_PORT     = _opt("EFWS_ANEM_PORT", "/dev/ttyUSB0")
ANEMOMETER_BAUDRATE = _int("EFWS_ANEM_BAUD", 4800)
ANEMOMETER_SLAVE_ID = _int("EFWS_ANEM_SLAVE", 1)
ANEMOMETER_REGISTER = int(_opt("EFWS_ANEM_REG", "0x0000"), 16)

# ─── SIM7600 4G HAT ──────────────────────────────────────────────────────────
SIM7600_AT_PORT  = _opt("EFWS_SIM_PORT", "/dev/ttyUSB2")
SIM7600_BAUDRATE = _int("EFWS_SIM_BAUD", 115200)
APN              = _opt("EFWS_APN", "internet")

# ─── REST API ────────────────────────────────────────────────────────────────
API_BASE_URL       = _req("EFWS_API_URL")
API_DATA_ENDPOINT  = f"{API_BASE_URL}/data"
API_ALARM_ENDPOINT = f"{API_BASE_URL}/alarm"
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
SENSOR_READ_INTERVAL_SEC = _int("EFWS_READ_INTERVAL", 5)
API_PUBLISH_INTERVAL_SEC = _int("EFWS_PUBLISH_INTERVAL", 10)

# ─── Threshold file ──────────────────────────────────────────────────────────
THRESHOLDS_PATH = str(_ROOT / "config" / "thresholds.json")
