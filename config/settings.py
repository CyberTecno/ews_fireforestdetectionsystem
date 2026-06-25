"""
Global configuration for Early Fire Warning System (EFWS).
Komunikasi: HTTP REST API (menggantikan MQTT & Telegram).
Edit file ini sebelum deployment ke hardware nyata.
"""
import os

# ─── Device Identity ─────────────────────────────────────────────
DEVICE_ID       = os.getenv("EFWS_DEVICE_ID", "efws-001")
DEVICE_LOCATION = {
    "lat": float(os.getenv("EFWS_LAT", "0.0")),
    "lon": float(os.getenv("EFWS_LON", "0.0")),
}

# ─── Mode: "mock" (testing tanpa hardware) atau "hardware" ───────
RUN_MODE = os.getenv("EFWS_RUN_MODE", "mock")   # ganti ke "hardware" di Pi asli

# ─── I2C / GPIO (hanya dipakai saat RUN_MODE=hardware) ──────────
I2C_BUS          = 1
BME280_ADDRESS   = 0x76
ADS1115_ADDRESS  = 0x48

ADC_CHANNEL_MQ2   = 0
ADC_CHANNEL_MQ135 = 1
ADC_CHANNEL_SOIL  = 2

GPIO_FLAME_SENSOR = 17
GPIO_RELAY_SIREN  = 27
GPIO_BUZZER       = 22
GPIO_STATUS_LED   = 23

# ─── Anemometer RS485 ────────────────────────────────────────────
ANEMOMETER_PORT      = os.getenv("EFWS_ANEM_PORT", "/dev/ttyUSB0")
ANEMOMETER_BAUDRATE  = 4800
ANEMOMETER_SLAVE_ID  = 1
ANEMOMETER_REGISTER  = 0x0000

# ─── SIM7600 4G HAT ──────────────────────────────────────────────
SIM7600_AT_PORT  = os.getenv("EFWS_SIM_PORT", "/dev/ttyUSB2")
SIM7600_BAUDRATE = 115200
APN              = os.getenv("EFWS_APN", "internet")

# ─── REST API (open endpoint, tidak butuh broker) ────────────────
# Ganti ke URL server/backend kamu, atau pakai webhook.site untuk testing cepat
API_BASE_URL       = os.getenv("EFWS_API_URL", "https://webhook.site/your-unique-id")
API_DATA_ENDPOINT  = f"{API_BASE_URL}/data"
API_ALARM_ENDPOINT = f"{API_BASE_URL}/alarm"
API_TIMEOUT_SEC    = 10
API_SECRET_KEY     = os.getenv("EFWS_API_KEY", "")          # Bearer token, kosongkan jika tidak ada
API_VERIFY_SSL     = os.getenv("EFWS_VERIFY_SSL", "true").lower() == "true"

# Retry logic untuk saat jaringan putus
API_MAX_RETRIES    = 3
API_RETRY_DELAY    = 5   # detik

# ─── Database lokal ──────────────────────────────────────────────
DB_PATH = os.getenv("EFWS_DB_PATH", "database/efws_data.db")

# ─── Timing ──────────────────────────────────────────────────────
SENSOR_READ_INTERVAL_SEC = int(os.getenv("EFWS_READ_INTERVAL", "5"))
API_PUBLISH_INTERVAL_SEC = int(os.getenv("EFWS_PUBLISH_INTERVAL", "10"))

# ─── Threshold file ──────────────────────────────────────────────
THRESHOLDS_PATH = "config/thresholds.json"
