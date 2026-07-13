"""
SIM7600 driver (LTE Cat-4 / 3G) — dipanggil oleh sim_detector.py
ketika hardware SIM7600 terdeteksi di port serial.

Perbedaan utama dari A7670E (a7670e.py):
  GPS power:  AT+CGPS=1  / AT+CGPS=0       (bukan AT+CGNSSPWR)
  GPS query:  AT+CGPSINFO                   (sama)
  Register:   AT+CREG? / AT+CSQ            (sama)

Interface publik (get_gps, get_gps_location, signal_quality, dll) identik
dengan A7670E sehingga SimInterface di sim_detector.py bisa panggil keduanya
tanpa tahu modul mana yang dipakai.
"""
import re
import time
import logging
try:
    import serial
except ImportError:
    serial = None
from config import settings

logger = logging.getLogger("efws.sim7600")


class SIM7600:
    def __init__(self, port=None, baudrate=None):
        if serial is None:
            raise RuntimeError("pyserial tidak terinstall - pip install pyserial")
        self.ser = serial.Serial(
            port or settings.A7670E_AT_PORT,
            baudrate or settings.A7670E_BAUDRATE,
            timeout=2,
        )
        self._gnss_on = False

    def send_at(self, command: str, wait: float = 1.0) -> str:
        self.ser.reset_input_buffer()
        self.ser.write((command + "\r\n").encode())
        time.sleep(wait)
        raw = self.ser.read(self.ser.in_waiting or 1)
        return raw.decode(errors="ignore")

    def check_module(self) -> bool:
        return "OK" in self.send_at("AT")

    def signal_quality(self) -> str:
        return self.send_at("AT+CSQ")

    def network_registration(self) -> str:
        return self.send_at("AT+CREG?")

    def gps_power_on(self) -> bool:
        # SIM7600 pakai AT+CGPS=1 (berbeda dari A7670E yang pakai AT+CGNSSPWR=1)
        resp = self.send_at("AT+CGPS=1", wait=2.0)
        if "OK" in resp or "+CGPS:" in resp:
            self._gnss_on = True
            logger.info("SIM7600 GPS engine ON.")
            return True
        logger.warning("SIM7600 GPS power ON gagal: %s", resp.strip())
        return False

    def gps_power_off(self) -> bool:
        resp = self.send_at("AT+CGPS=0", wait=1.0)
        self._gnss_on = False
        return "OK" in resp

    def _parse_cgpsinfo(self, raw: str) -> "dict | None":
        match = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", raw)
        if not match:
            return None
        parts = [p.strip() for p in match.group(1).split(",")]
        if len(parts) < 9 or parts[0] == "":
            return None
        try:
            def nmea_to_dd(nmea, direction):
                dot = nmea.index(".")
                dd = float(nmea[:dot - 2]) + float(nmea[dot - 2:]) / 60.0
                return round(-dd if direction in ("S", "W") else dd, 6)

            lat = nmea_to_dd(parts[0], parts[1])
            lon = nmea_to_dd(parts[2], parts[3])
            alt = float(parts[6]) if parts[6] else None
            spd = float(parts[7]) if parts[7] else None
            utc = parts[5]
            date = parts[4]

            return {
                "fix": True, "lat": lat, "lon": lon, "altitude_m": alt,
                "speed_kmh": round(spd * 1.852, 2) if spd else None,
                "course_deg": float(parts[8]) if parts[8] else None,
                "date_utc": f"{date[:2]}/{date[2:4]}/20{date[4:]}" if len(date) == 6 else date,
                "time_utc": f"{utc[:2]}:{utc[2:4]}:{utc[4:]}" if len(utc) >= 6 else utc,
                "raw": match.group(1).strip(),
            }
        except Exception as e:
            logger.debug("GPS parse error: %s", e)
            return None

    def get_gps(self, timeout: int = 90, interval: float = 3.0) -> dict:
        if not self._gnss_on:
            if not self.gps_power_on():
                return {"fix": False, "reason": "GPS engine gagal dinyalakan (SIM7600)"}

        elapsed = 0.0
        while elapsed < timeout:
            raw = self.send_at("AT+CGPSINFO", wait=1.0)
            result = self._parse_cgpsinfo(raw)
            if result:
                logger.info("SIM7600 GPS fix! lat=%.6f, lon=%.6f", result["lat"], result["lon"])
                return result
            time.sleep(interval)
            elapsed += interval + 1.0

        return {"fix": False, "reason": f"SIM7600 GPS timeout {timeout}s"}

    def get_gps_location(self) -> "tuple | None":
        result = self.get_gps()
        if result.get("fix"):
            return result["lat"], result["lon"]
        return None

    def close(self):
        if self._gnss_on:
            self.gps_power_off()
        self.ser.close()
