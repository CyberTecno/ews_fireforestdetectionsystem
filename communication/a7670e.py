"""
SIMCom A7670E / SIM7670E (LTE Cat-1 4G) controller via AT command - GPS/GNSS.

CATATAN PENTING soal kompatibilitas AT command:
  Modul A7670E/SIM7670E SECARA UMUM kompatibel dengan AT command set
  A7670E kompatibel dengan AT command SIM7600 untuk fungsi modem dasar (AT, AT+CSQ, AT+CREG?, AT+CGDCONT,
  AT+CGPADDR), TAPI untuk GNSS/GPS perintahnya BERBEDA:

    SIM7600 lama : AT+CGPS=1 / AT+CGPS=0   (nyalakan/matikan GPS engine)
    A7670E/SIM7670E : AT+CGNSSPWR=1 / AT+CGNSSPWR=0  (nyalakan/matikan GNSS)

  Sedangkan AT+CGPSINFO untuk membaca hasil fix formatnya SAMA di kedua
  keluarga modul ini, jadi parser NMEA di bawah tetap dipakai apa adanya.
  (Referensi: SIMCom A76XX Series AT Command Manual & GNSS Application Note)

Fitur:
  - Diagnostik modem (signal, registrasi jaringan, IP)
  - GPS: ambil koordinat lat/lon real dari antena GNSS modul

Alur AT command GNSS:
  AT+CGNSSPWR=1   -> nyalakan GNSS engine (tunggu "+CGNSSPWR: READY!")
  AT+CGPSINFO     -> baca NMEA fix (lat, lon, alt, kecepatan, arah, waktu)
  AT+CGNSSPWR=0   -> matikan GNSS (opsional, hemat daya)

Requires: pip install pyserial
"""
import re
import time
import logging
try:
    import serial
except ImportError:
    serial = None
from config import settings

logger = logging.getLogger("efws.a7670e")


class A7670E:
    """
    Module A7670E/SIM7670E - class utama untuk akses AT command dan GNSS.
    
    """

    def __init__(self, port=None, baudrate=None):
        if serial is None:
            raise RuntimeError("pyserial tidak terinstall - pip install pyserial")
        self.ser = serial.Serial(
            port or settings.A7670E_AT_PORT,
            baudrate or settings.A7670E_BAUDRATE,
            timeout=2,
        )
        self._gnss_on = False

    # ─── AT command primitif ─────────────────────────────────────
    def send_at(self, command: str, wait: float = 1.0) -> str:
        """Kirim AT command, return response string."""
        self.ser.reset_input_buffer()
        self.ser.write((command + "\r\n").encode())
        time.sleep(wait)
        raw = self.ser.read(self.ser.in_waiting or 1)
        return raw.decode(errors="ignore")

    # ─── Diagnostik modem ────────────────────────────────────────
    def check_module(self) -> bool:
        return "OK" in self.send_at("AT")

    def signal_quality(self) -> str:
        """AT+CSQ -> +CSQ: <rssi>,<ber>. rssi 0-31 (makin tinggi makin kuat), 99=tidak diketahui."""
        return self.send_at("AT+CSQ")

    def network_registration(self) -> str:
        return self.send_at("AT+CREG?")

    def apn_setup(self, apn: str = None) -> str:
        apn = apn or settings.APN
        self.send_at(f'AT+CGDCONT=1,"IP","{apn}"')
        return self.send_at("AT+CGATT=1")

    def get_ip(self) -> str:
        return self.send_at("AT+CGPADDR=1")

    # ─── GNSS / GPS (A7670E/SIM7670E command set) ─────────────────
    def gps_power_on(self) -> bool:
        """
        Nyalakan GNSS engine A7670E/SIM7670E. Perlu 15-60 detik untuk fix
        pertama (cold start) di luar ruangan dengan antena GNSS terpasang.
        """
        resp = self.send_at("AT+CGNSSPWR=1", wait=2.0)
        if "OK" in resp or "READY" in resp:
            self._gnss_on = True
            logger.info("GNSS engine ON. Tunggu fix (cold: ~15-60 detik).")
            return True
        logger.warning("GNSS power ON gagal: %s", resp.strip())
        return False

    def gps_power_off(self) -> bool:
        """Matikan GNSS engine (hemat daya jika tidak dibutuhkan terus-menerus)."""
        resp = self.send_at("AT+CGNSSPWR=0", wait=1.0)
        self._gnss_on = False
        return "OK" in resp

    def _parse_cgpsinfo(self, raw: str) -> dict | None:
        """
        Parse respons AT+CGPSINFO (format sama untuk semua modul SIMCom A76XX/ SIM76XX series).

        Format NMEA:
          +CGPSINFO: <lat>,<N/S>,<lon>,<E/W>,<date>,<utc_time>,<alt>,<speed>,<course>

        Contoh ada fix:
          +CGPSINFO: 0114.5506,S,11649.5982,E,260625,033042.0,8.2,0.0,0.0

        Contoh belum ada fix:
          +CGPSINFO: ,,,,,,,,
        """
        match = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", raw)
        if not match:
            return None

        parts = [p.strip() for p in match.group(1).split(",")]
        if len(parts) < 9 or parts[0] == "":
            return None   # belum ada fix

        try:
            def _nmea_to_dd(nmea: str, direction: str) -> float:
                """Konversi NMEA ddmm.mmmm -> decimal degrees."""
                dot = nmea.index(".")
                deg = float(nmea[:dot - 2])
                minutes = float(nmea[dot - 2:])
                dd = deg + minutes / 60.0
                if direction in ("S", "W"):
                    dd = -dd
                return round(dd, 6)

            lat  = _nmea_to_dd(parts[0], parts[1])
            lon  = _nmea_to_dd(parts[2], parts[3])
            date = parts[4]   # DDMMYY
            utc  = parts[5]   # HHMMSS.s
            alt  = float(parts[6]) if parts[6] else None
            spd  = float(parts[7]) if parts[7] else None
            crs  = float(parts[8]) if parts[8] else None

            utc_fmt = f"{utc[:2]}:{utc[2:4]}:{utc[4:]}" if len(utc) >= 6 else utc
            date_fmt = f"{date[:2]}/{date[2:4]}/20{date[4:]}" if len(date) == 6 else date

            return {
                "fix":          True,
                "lat":          lat,
                "lon":          lon,
                "altitude_m":   alt,
                "speed_kmh":    round(spd * 1.852, 2) if spd is not None else None,  # knot->km/h
                "course_deg":   crs,
                "date_utc":     date_fmt,
                "time_utc":     utc_fmt,
                "raw":          match.group(1).strip(),
            }
        except (ValueError, IndexError) as e:
            logger.debug("GPS parse error: %s | raw: %s", e, raw.strip())
            return None

    def get_gps(self, timeout: int = 90, interval: float = 3.0) -> dict:
        """
        Ambil koordinat GPS dari A7670E/SIM7670E.
        Jika GNSS engine belum ON, akan dinyalakan otomatis.
        Polling AT+CGPSINFO sampai ada fix atau timeout.

        Return dict:
          fix=True  -> {"fix": True, "lat": float, "lon": float, ...}
          fix=False -> {"fix": False, "reason": str}
        """
        if not self._gnss_on:
            if not self.gps_power_on():
                return {"fix": False, "reason": "GNSS engine gagal dinyalakan"}

        logger.info("Menunggu GNSS fix (timeout %ds)...", timeout)
        elapsed = 0.0

        while elapsed < timeout:
            raw = self.send_at("AT+CGPSINFO", wait=1.0)
            result = self._parse_cgpsinfo(raw)

            if result:
                logger.info(
                    "GNSS fix! lat=%.6f, lon=%.6f, alt=%.1fm, spd=%.1fkm/h",
                    result["lat"], result["lon"],
                    result.get("altitude_m") or 0,
                    result.get("speed_kmh") or 0,
                )
                return result

            logger.debug("Belum ada fix (%.0fs/%.0fs)...", elapsed, timeout)
            time.sleep(interval)
            elapsed += interval + 1.0

        return {
            "fix":    False,
            "reason": f"Timeout {timeout}s - pastikan antena GNSS terpasang dan langit terbuka",
        }

    def get_gps_location(self) -> "tuple[float, float] | None":
        """Shortcut: return (lat, lon) atau None jika tidak ada fix."""
        result = self.get_gps()
        if result.get("fix"):
            return result["lat"], result["lon"]
        return None

    def close(self):
        if self._gnss_on:
            self.gps_power_off()
        self.ser.close()


# ─── Mock GPS untuk mode testing ─────────────────────────────────
class MockA7670E:
    """Dipakai saat RUN_MODE=mock - tidak butuh hardware A7670E/SIM7670E."""
    _gnss_on = False

    def gps_power_on(self) -> bool:
        self._gnss_on = True
        return True

    def gps_power_off(self) -> bool:
        self._gnss_on = False
        return True

    def get_gps(self, timeout=90, interval=3.0) -> dict:
        return {
            "fix":        True,
            "lat":        -1.265400,
            "lon":        116.831200,
            "altitude_m": 8.2,
            "speed_kmh":  0.0,
            "course_deg": 0.0,
            "date_utc":   "26/06/2025",
            "time_utc":   "03:30:42",
            "_mock":      True,
        }

    def get_gps_location(self) -> tuple:
        return (-1.265400, 116.831200)

    def check_module(self) -> bool: return True
    def signal_quality(self) -> str: return "+CSQ: 20,0\r\nOK"
    def network_registration(self) -> str: return "+CREG: 0,1\r\nOK"
    def send_at(self, cmd, wait=1.0) -> str: return "OK"
    def close(self): pass


if __name__ == "__main__":
    # Test langsung: python communication/a7670e.py
    import json
    modem = A7670E()
    print("Module:", modem.check_module())
    print("Signal:", modem.signal_quality().strip())
    result = modem.get_gps(timeout=90)
    print("GPS:", json.dumps(result, indent=2))
    modem.close()
