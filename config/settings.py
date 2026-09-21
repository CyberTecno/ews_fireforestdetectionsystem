"""
Global configuration for EFWS.
All sensitive values ​​are read from the .env file (via python-dotenv).
The .env file can NOT be committed to git — see .env.example for the template.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Search for .env automatically (go up the folders until you find it) ───────────────────
def _find_and_load_dotenv():
    """
Look for the .env file starting from the settings.py location, going up 2 levels.
This is so it doesn't matter how deep the project folder structure is.
    """
    search_start = Path(__file__).resolve().parent  # starting from config/
    for candidate in [search_start, *search_start.parents[:2]]:
        env_file = candidate / ".env"
        if env_file.exists():
            print(f"✅  Found .env at {env_file}, loading...")
            load_dotenv(env_file, override=True)
            return candidate   # return found root
    # Can't find .env — load_dotenv still works (reads from system env var only)
    print("❌  .env not found, using system environment variables only.")
    load_dotenv(override=True)
    return search_start

_ROOT = _find_and_load_dotenv()


# ─── Helper ──────────────────────────────────────────────────────────────────
def _req(key: str) -> str:
    """Read the mandatory env var. Raise error is clear if there is none."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"\n\n  ❌  Environment variable '{key}' not found.\n"
            f"Make sure the .env file is in the root of the project and is filled in.\n"
            f"Example: cp .env.example .env\n"
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

# ─── GPS — position read from file cache (written by ews_network_setup.sh) ───
# ews_network_setup.sh (boot) + gps_refresh.sh (every 30 minutes via systemd timer)
# retrieves GPS via AT command and writes the results to GPS_CACHE_FILE.
# main.py is just READ this file — never opens the AT serial port.
# Fallback: if cache is missing or fix=false, use EFWS_LAT/EFWS_LON from .env.
GPS_CACHE_FILE = _opt("EFWS_GPS_CACHE", "/tmp/ews_gps_cache.json")

# ─── Mode operasi ────────────────────────────────────────────────────────────
RUN_MODE = _opt("EFWS_RUN_MODE", "mock")

# ─── I2C (BME280 — ambient temperature/humidity/pressure, native I2C) ────────────
I2C_BUS        = _int("EFWS_I2C_BUS", 1)
BME280_ADDRESS = int(_opt("EFWS_BME280_ADDR", "0x76"), 16)

# ─── SPI / MCP3008 (ADC 8-channel, SATU Logic Level Converter) ─────────────
# hardware version: 1x MCP3008, 1x LLC (min. 6-channel, i.e. 8-ch module),
# 2x soil probe, MQ-2, MQ-135, anemometer RS485 (directly USB, without LLC),
# submersible pressure sensor (loop 4-20mA + burden resistor), sensor module
# battery voltage DC 0-25V, and 4G modem SIM7600 (ttyUSB2 = AT command port).
#
#   LLC (HV=5V, LV=3.3V) — 4 channels, ONLY for 0-5V analog sensors
#   genuinely needs a step-down (MQ-2, MQ-135, soil x2). Pressure & Battery
#   NOT through this LLC (see respective notes below).
#     LLC CH1 : MQ-2   AOUT                    → MCP3008 CH0
#     LLC CH2 : MQ-135 AOUT                     → MCP3008 CH1
#     LLC CH3 : Soil Surface AOUT                → MCP3008 CH2
#     LLC CH4 : Soil Deep    AOUT                → MCP3008 CH3
#   (LLC physical module only has 4 channels, already fully used above)
#
#   WITHOUT LLC (direct to MCP3008):
#     Pressure sensor (via R_BURDEN 100 Ohm) → MCP3008 CH4
#     Voltage Sensor Module "S" (native 3.3V)     → MCP3008 CH5
#     Flame sensor AO (native 3.3V)               → MCP3008 CH6
#   MCP3008 CH7: spare, not wired
SPI_BUS          = _int("EFWS_SPI_BUS", 0)
SPI_DEVICE       = _int("EFWS_SPI_DEVICE", 0)
SPI_MAX_SPEED_HZ = _int("EFWS_SPI_SPEED", 1350000)
MCP3008_VREF     = _float("EFWS_MCP3008_VREF", 3.3)

ADC_CHANNEL_MQ2             = _int("EFWS_ADC_MQ2",          0)   # LLC CH1
ADC_CHANNEL_MQ135           = _int("EFWS_ADC_MQ135",         1)   # LLC CH2
ADC_CHANNEL_SOIL_SURFACE    = _int("EFWS_ADC_SOIL_SURFACE",  2)   # LLC CH3 (probe 0-30cm)
ADC_CHANNEL_SOIL_DEEP       = _int("EFWS_ADC_SOIL_DEEP",     3)   # LLC CH4 (probe 30-60cm)
ADC_CHANNEL_PRESSURE        = _int("EFWS_ADC_PRESSURE",      4)   # DIRECT to MCP3008 CH4 via R_BURDEN 100 Ohm, NOT via LLC
ADC_CHANNEL_BATTERY         = _int("EFWS_ADC_BATTERY",       5)   # DIRECTLY to MCP3008 CH5, NOT via LLC (see notes on sensors/battery.py)
ADC_CHANNEL_FLAME_AO   = _int("EFWS_ADC_FLAME_AO", 6)          # MCP3008 CH6, directly without LLC. CH7 = spare.
# CH7 spare (physically empty, at the end after flame)

# ─── Gravity Rainfall Sensor (DFRobot SEN0575) ─────────────────────────────
# (I2C_BUS is used in conjunction with BME280 -- see definition above, NO
# redefined here again. Previously there was a line "I2C_BUS=1" in
# here which silently overwrote the EFWS_I2C_BUS value from .env -- it was removed.)
RAINFALL_I2C_ADDRESS = 0x1D
# Reading interval (seconds)
RAINFALL_READ_INTERVAL = 2

# ─── Battery — Voltage Sensor Module DC 0-25V (voltage divider 5:1) ────────
# CONFIRMED from the official datasheet of this module (osoyoo.com/2024/09/08/lesson-13-
# voltage-sensor-for-raspberry-pi/): the module has a FIXED 1:5 voltage-divider ratio
# (not dependent on VREF). This module has a safe input limit of "less than 16.5V"
# when its ADC is given VREF 3.3V (3.3 x 5 = 16.5V) -- NOT 25V like value
# here for a long time. The old value (25.0) is incorrect and will result in V_battery
# under-read around 34%. If your physical module is of a different brand, /rasio, adjust accordingly
# via EFWS_BATTERY_SENSOR_MAX_V.
BATTERY_SENSOR_MAX_V = _float("EFWS_BATTERY_SENSOR_MAX_V", 16.5)  # sensor module max input (V) @ VREF 3.3V, ratio 1:5
# BATTERY_MAX_V confirmed by the user: physical power supply/battery maximum is 14.4 V
BATTERY_MAX_V        = _float("EFWS_BATTERY_MAX_V",        14.4)  # full battery voltage (V)
BATTERY_MIN_V        = _float("EFWS_BATTERY_MIN_V",         10.7)  # empty battery voltage (V)

# ─── Submersible / Pressure Water Level Sensor — loop 4-20mA ───────────────
# NOTE: submersible.py (stand alone script, uses channels & formulas
# same) has already been MERGED here/removed -- pressure.py is the only one
# implementation for this sensor is now (see sensors/pressure.py).
PRESSURE_BURDEN_OHM = _float("EFWS_PRESSURE_BURDEN_OHM",     100.0)  # 4mA→1V, 20mA→5V
PRESSURE_MIN_MA     = _float("EFWS_PRESSURE_MIN_MA",       4.032)
PRESSURE_MAX_MA     = _float("EFWS_PRESSURE_MAX_MA",      20.0)
PRESSURE_RANGE_M    = _float("EFWS_PRESSURE_RANGE_M",      3.0)  # full range of sensors, adjust datasheet

# ─── Flame Sensor (IR, read via AO/analog at MCP3008 CH6) ───────────────
# User decision: use AO via MCP3008 CH6, NOT via GPIO digital DO.
# The YET voltage threshold is calibrated to the physical unit -- see comments
# calibration on sensors/flame.py before use in the field.
ADC_CHANNEL_FLAME_AO   = _int("EFWS_ADC_FLAME_AO", 6)          # MCP3008 CH6, directly without LLC. CH7 = spare.
FLAME_AO_THRESHOLD_V   = _float("EFWS_FLAME_AO_THRESHOLD_V", 1.65)  # INITIAL ESTIMATE (half VREF) -- MANDATORY recalibrated in the field

# ─── smokeLevel: combined MQ-2 + MQ-135 → percentage 0-100% ────────────────
# Formula: smokeLevel = (mq2_ppm/MQ2_CRIT * W_MQ2 + mq135_ppm/MQ135_CRIT * W_MQ135) * 100
# Limits: 60-70% = WARNING, ≥70% = CRITICAL, 100% = both sensors at critical threshold
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
# IMPORTANT: make sure Bluetooth is disabled (dtoverlay=disable-bt) and
# console serial is turned off in raspi-config, or this port conflicts/baudrate
# drift. See full note at sensors/wind_direction.py.
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

# ─── SIM7600 4G LTE (kartu biasa, APN: internet) ────────────────────────────
# ttyUSB2 = AT command port SIM7600 (Waveshare 4G HAT)
# ttyUSB0 = DM, ttyUSB1 = AT secondary, ttyUSB3 = PPP/modem (do not use)
SIM7600_AT_PORT  = _opt("EFWS_SIM_PORT",    "/dev/ttyUSB2")
SIM7600_BAUDRATE = _int("EFWS_SIM_BAUD",     115200)
APN              = _opt("EFWS_APN",          "internet")

# ─── REST API ──────────────────────────────── ────────────────────────────────
API_BASE_URL       = _req("EFWS_API_URL")
# NOTE: endpoint URL INTENTIONAL is not defined as a constant
# module, but via the dynamic function below, so that URL is in effect when
# runtime always uses the latest EFWS_API_URL from the env — including if
# .env changed and service restarted. There are 4 endpoints:
#   telemetry_endpoint()   -> /sensors/telemetry     (scheduled, bawa config remote)
#   location_endpoint()    -> /sensors/location       (scheduled)
#   heartbeat_endpoint()   -> /sensors/heartbeat      (scheduled, bawa commands)
#   command_ack_endpoint() -> /sensors/commands/ack (event-driven, from commands)

def _base_url() -> str:
    return os.getenv("EFWS_API_URL", API_BASE_URL).rstrip("/")

def telemetry_endpoint() -> str:
    """Sensor data + smokeLevel, etc. The response carries 'config' (remote thresholds)."""
    return _base_url() + "/sensors/telemetry"

def location_endpoint() -> str:
    """Update posisi GPS/fallback device."""
    return _base_url() + "/sensors/location"

def heartbeat_endpoint() -> str:
    """Health check and the place where the backend supplies 'commands' (for example, Reboot)."""
    return _base_url() + "/sensors/heartbeat"

def command_ack_endpoint() -> str:
    """ACK is the result of executing the command received via heartbeat. Event-driven, not scheduled."""
    return _base_url() + "/sensors/commands/ack"

API_SECRET_KEY     = _opt("EFWS_API_KEY", "")
API_VERIFY_SSL     = _bool("EFWS_VERIFY_SSL", True)
API_TIMEOUT_SEC    = _int("EFWS_API_TIMEOUT", 10)
API_MAX_RETRIES    = _int("EFWS_API_RETRIES", 3)
API_RETRY_DELAY    = _int("EFWS_API_RETRY_DELAY", 5)

# ─── Local database ───────────────────────────── ─────────────────────────────
DB_PATH = _opt("EFWS_DB_PATH", str(_ROOT / "database" / "efws_data.db"))

# Local data retention -- sensor_readings & api_queue rows (which state
# completed: sent OR has been permanently discarded) which is older than
# this is automatically DELETED by the background thread (see main.py:
# EFWS._retention_loop). This deletes old ROWS from the database,
# NOT delete the database file itself -- the latest tables & data remain.
DB_RETENTION_DAYS        = _int("EFWS_DB_RETENTION_DAYS", 3)
DB_RETENTION_CHECK_SEC   = _int("EFWS_DB_RETENTION_CHECK_SEC", 6 * 3600)  # check every 6 hours

# ─── Log files ───────────────────────────────────────────────────────────────
LOG_PATH = _opt("EFWS_LOG_PATH", str(_ROOT / "logs" / "efws.log"))

# ─── Timing ──────────────────────────────────────────────────────────────────
# Sensor CHECK cycle -- always runs at this interval, purely for evaluation
# threshold (fast, for responsive emergency detection). NEVER send to
# API and NEVER save to SQLite here -- that's a Telemetry job
# Publisher (see below). This cycle also no longer fetches GPS --
# GPS is only picked up by Location Publisher, right before sending.
SENSOR_READ_INTERVAL_SEC = _int("EFWS_READ_INTERVAL", 180)

# ─── 3 scheduler independen (Location / Telemetry / Heartbeat) ────────────
# Each endpoint has its OWN scheduler & thread (see main.py:
# EFWS._location_loop / _telemetry_loop / _heartbeat_loop). Nothing is
# waiting for each other or triggering each other.
#
# Location -- ALWAYS every 30 minutes, not affected by Emergency Mode
#              once (spec: "Emergency Mode must never modify the execution
#              interval of Location or Heartbeat").
LOCATION_INTERVAL_SEC = _int("EFWS_LOCATION_INTERVAL_SEC", 1800)

# Telemetry -- 30 minutes when NORMAL. When Emergency Mode is active, the scheduler
#              the SAME (not the second scheduler) switches to interval
#              EMERGENCY_TELEMETRY_INTERVAL_SEC below, so no
#              there may be two overlapping telemetry transmissions.
TELEMETRY_INTERVAL_SEC = _int("EFWS_TELEMETRY_INTERVAL_SEC", 1800)

# Current Telemetry EMERGENCY -- 10 minutes, ONLY this endpoint changed
# schedule during an emergency (Location & Heartbeat remains on its normal schedule).
EMERGENCY_TELEMETRY_INTERVAL_SEC = _int("EFWS_EMERGENCY_TELEMETRY_INTERVAL_SEC", 600)

# Heartbeat -- ALWAYS every 5 minutes. Never rely on Telemetry,
# Location, or Emergency Mode (explicit specs about this).
HEARTBEAT_INTERVAL_SEC = _int("EFWS_HEARTBEAT_INTERVAL_SEC", 300)

# Retry offline queue -- runs on thread SEPARATE from the sensor read cycle
# and the three publishers above, every 2 minutes (confirmed by user).
EFWS_CONNECTIVITY_CHECK_SEC = _int("EFWS_CONNECTIVITY_CHECK_SEC", 120)

# ─── Command executor (endpoint 4: /sensors/commands/ack) ──────────────────
# Delay before actually restarting after the "Reboot" command is received.
# Why does it need to be delayed: this process must have time SENDING ack SUCCESS first
# before systemctl restart kills the running Python process.
# See main.py: EFWS._cmd_reboot() for details.
COMMAND_REBOOT_DELAY_SEC = _int("EFWS_REBOOT_DELAY_SEC", 5)

# ─── File threshold ───────────────────────────── ─────────────────────────────
THRESHOLDS_PATH = str(_ROOT / "config" / "thresholds.json")
