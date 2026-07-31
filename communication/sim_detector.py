"""
SIM Auto-Detector — mendeteksi otomatis apakah node ini menggunakan
modul A7670E/SIM7670E (LTE Cat-1) atau SIM7600 (LTE Cat-4/3G).

Cara kerja:
  1. Scan semua port /dev/ttyUSBx yang tersedia.
  2. Kirim AT command ke tiap port; kalau ada yang merespons, cek identitas
     modul lewat ATI (Product Identification Information).
  3. A7670E/SIM7670E → instantiasi class A7670E (command GNSS: AT+CGNSSPWR)
  4. SIM7600           → instantiasi class SIM7600 (command GNSS: AT+CGPS)
  5. Hasil deteksi disimpan di .sim_cache (file teks) sehingga boot berikutnya
     langsung ke port yang benar tanpa scan ulang.

Kenapa dua class terpisah (bukan satu unified)?
  AT command untuk GNSS berbeda antara A7670E dan SIM7600, dan
  mencampur keduanya dalam satu class akan mengorbankan kejelasan kode.
  Auto-detector ini menjadi jembatan — callers di main.py tidak perlu tahu
  modul mana yang dipakai, karena interface publiknya sama.

Usage:
  from communication.sim_detector import detect_sim, SimInterface
  sim = detect_sim()              # auto-detect saat startup
  coords = sim.get_gps()          # unified API, terlepas dari modul fisik
"""
import os
import time
import logging
import glob
import json
from pathlib import Path

try:
    import serial
except ImportError:
    serial = None

from config import settings

logger = logging.getLogger("efws.sim_detector")

CACHE_FILE = Path(__file__).parent.parent / ".sim_cache"
SCAN_PORTS = ["/dev/ttyUSB2", "/dev/ttyUSB3", "/dev/ttyUSB1"]
BAUD       = 115200
TIMEOUT    = 2


# ─── ATI fingerprint → modul ─────────────────────────────────────────────────
# Kata kunci yang muncul di respons ATI untuk masing-masing modul.
# Tambahkan variant lain kalau ada modul SIMCom lain di project ini.
_FINGERPRINTS = {
    "a7670e":  ["A7670E", "A7670", "SIM7670"],
    "sim7600": ["SIM7600", "SIM7600E", "SIM7600G"],
}


def _send_at(ser, cmd: str, wait: float = 1.0) -> str:
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)
    return ser.read(ser.in_waiting or 1).decode(errors="ignore")


def _identify_port(port: str) -> "str | None":
    """
    Buka port, kirim AT, kirim ATI.
    Return: "a7670e", "sim7600", atau None (tidak dikenali / tidak merespons).
    """
    if serial is None:
        raise RuntimeError("pyserial tidak terinstall - pip install pyserial")
    try:
        ser = serial.Serial(port, BAUD, timeout=TIMEOUT)
        at_resp = _send_at(ser, "AT", wait=1.0)
        if "OK" not in at_resp:
            ser.close()
            return None

        ati_resp = _send_at(ser, "ATI", wait=1.0).upper()
        ser.close()

        for module_key, keywords in _FINGERPRINTS.items():
            if any(kw.upper() in ati_resp for kw in keywords):
                return module_key

        # Merespons AT tapi ATI tidak cocok fingerprint — kemungkinan modul SIMCom lain
        logger.warning("Port %s merespons AT tapi tidak dikenali dari ATI: %s",
                       port, ati_resp[:80])
        return None

    except serial.SerialException as e:
        logger.debug(
            "%s busy (%s)",
            port,
            e
        )

        return None

    except OSError as e:
        logger.debug(
            "%s error (%s)",
            port,
            e
        )

        return None


def scan_ports() -> "dict | None":
    """
    Scan semua kandidat port serial, return dict {port, module} saat ketemu,
    atau None kalau tidak ada yang merespons.
    """
    # Port yang SUDAH DIPASTIKAN dipakai peripheral lain (bukan modem) -- JANGAN
    # ikut discan. Kalau ikut discan, _identify_port() akan buka port itu dan
    # menembakkan "AT"/"ATI" ke bus-nya, yang akan mengacaukan komunikasi
    # peripheral asli di port tsb (terbukti: anemometer RS485 di ANEMOMETER_PORT
    # kehilangan data tiap kali _load_sim()/scan_ports() jalan, karena port yang
    # sama ikut ter-scan sebagai kandidat modem).
    RESERVED_PORTS = {settings.ANEMOMETER_PORT}

    # Gabungkan dengan hasil glob supaya dapat port yang tidak ada di SCAN_PORTS
    candidates = [
        p for p in dict.fromkeys(SCAN_PORTS + sorted(glob.glob("/dev/ttyUSB*")))
        if p not in RESERVED_PORTS
    ]

    logger.info("🔍 Scanning %d port kandidat untuk modul SIM...", len(candidates))
    for port in candidates:
        if not os.path.exists(port):
            continue
        logger.debug("  Mencoba %s ...", port)
        module = _identify_port(port)
        if module:
            logger.info("  ✅ Modul %s ditemukan di %s", module.upper(), port)
            return {"port": port, "module": module}

    logger.warning("❌ Tidak ada modul SIM yang terdeteksi di port manapun.")
    return None


def _load_cache() -> "dict | None":
    try:
        data = json.loads(CACHE_FILE.read_text())
        # Validasi port masih ada (bisa berubah setelah reboot)
        if os.path.exists(data.get("port", "")):
            logger.info("📋 SIM cache: port=%s module=%s", data["port"], data["module"])
            return data
        logger.info("Cache stale (port %s tidak ada), scan ulang...", data.get("port"))
    except Exception:
        pass
    return None


def _save_cache(info: dict):
    try:
        CACHE_FILE.write_text(json.dumps(info))
    except Exception:
        pass


def detect_sim(force_scan: bool = False) -> "SimInterface":

    if settings.RUN_MODE == "mock":
        logger.info("Mode MOCK — pakai MockSimInterface.")
        return MockSimInterface()

    info = None if force_scan else _load_cache()

    # ==========================
    # VALIDASI CACHE
    # ==========================

    if info is not None:

        try:

            sim = SimInterface(
                port=info["port"],
                module=info["module"],
            )

            if sim.check_module():
                return sim

            logger.warning(
                "Cache tidak valid (AT tidak merespons), scan ulang..."
            )

        except Exception as e:

            logger.warning(
                "Cache gagal (%s), scan ulang...",
                e
            )

        info = None

    # ==========================
    # SCAN ULANG
    # ==========================

    if info is None:

        info = scan_ports()

        if info:
            _save_cache(info)

        else:
            raise RuntimeError(
                "Tidak ada modul SIM yang terdeteksi."
            )

    return SimInterface(
        port=info["port"],
        module=info["module"],
    )
# ─── Unified interface ────────────────────────────────────────────────────────

class SimInterface:
    """
    Wrapper unified di atas A7670E atau SIM7600 — callers tidak perlu tahu
    modul mana yang dipakai, interface publiknya identik.
    """

    def __init__(self, port: str, module: str):
        self.port   = port
        self.module = module   # "a7670e" atau "sim7600"
        self._drv   = self._init_driver(port, module)
        logger.info("SimInterface: %s @ %s", module.upper(), port)

    def _init_driver(self, port: str, module: str):
        if module == "a7670e":
            from communication.a7670e import A7670E
            return A7670E(port=port, baudrate=BAUD)
        elif module == "sim7600":
            from communication.sim7600_legacy import SIM7600
            return SIM7600(port=port, baudrate=BAUD)
        else:
            raise ValueError(f"Module tidak dikenal: {module}")

    # ── Public API (sama untuk keduanya) ─────────────────────────
    def get_gps(self, timeout: int = None, interval: float = 3.0) -> dict:
        t = timeout if timeout is not None else settings.GPS_TIMEOUT
        return self._drv.get_gps(timeout=t, interval=interval)

    def get_gps_location(self) -> "tuple | None":
        return self._drv.get_gps_location()

    def signal_quality(self) -> str:
        return self._drv.signal_quality()

    def network_registration(self) -> str:
        return self._drv.network_registration()

    def check_module(self) -> bool:
        return self._drv.check_module()

    def close(self):
        self._drv.close()

    def __repr__(self):
        return f"<SimInterface module={self.module} port={self.port}>"


class MockSimInterface:
    """Dipakai saat RUN_MODE=mock — tidak butuh hardware apapun."""
    module = "mock"
    port   = "mock"

    def get_gps(self, timeout=90, interval=3.0) -> dict:
        return {
            "fix": True, "lat": -1.265400, "lon": 116.831200,
            "altitude_m": 8.2, "speed_kmh": 0.0, "course_deg": 0.0,
            "date_utc": "30/06/2025", "time_utc": "07:00:42", "_mock": True,
        }

    def get_gps_location(self) -> tuple:
        return (-1.265400, 116.831200)

    def signal_quality(self) -> str:
        return "+CSQ: 20,0\r\nOK"

    def network_registration(self) -> str:
        return "+CREG: 0,1\r\nOK"

    def check_module(self) -> bool:
        return True

    def close(self):
        pass

    def __repr__(self):
        return "<MockSimInterface>"
