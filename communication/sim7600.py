"""
SIM7600E-H 4G HAT controller via AT commands.

Fitur:
  - Diagnostik modem (signal, registrasi jaringan, IP)
  - GPS: ambil koordinat lat/lon real dari antena GPS bawaan SIM7600E
    (frekuensi antena 1532.24 MHz L-Band)

AT command GPS flow:
  AT+CGPS=1       → nyalakan GPS engine
  AT+CGPSINFO     → baca NMEA fix (lat, lon, alt, kecepatan, arah, waktu)
  AT+CGPS=0       → matikan GPS (opsional, hemat daya)

Requires: pip install pyserial
"""
import re
import time
import logging
import serial
from config import settings

logger = logging.getLogger("efws.sim7600")


class SIM7600:
    def __init__(self, port=settings.SIM7600_AT_PORT, baudrate=settings.SIM7600_BAUDRATE):
        self.ser = serial.Serial(port, baudrate, timeout=2)
        self._gps_on = False

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
        """AT+CSQ → +CSQ: <rssi>,<ber>. rssi 0–31 (makin tinggi makin kuat), 99=tidak diketahui."""
        return self.send_at("AT+CSQ")

    def network_registration(self) -> str:
        return self.send_at("AT+CREG?")

    def apn_setup(self, apn: str = settings.APN) -> str:
        self.send_at(f'AT+CGDCONT=1,"IP","{apn}"')
        return self.send_at("AT+CGATT=1")

    def get_ip(self) -> str:
        return self.send_at("AT+CGPADDR=1")

    # ─── GPS ─────────────────────────────────────────────────────
    def gps_power_on(self) -> bool:
        """Nyalakan GPS engine SIM7600E. Perlu 30–60 detik untuk cold fix."""
        resp = self.send_at("AT+CGPS=1", wait=1.5)
        if "OK" in resp or "already" in resp.lower():
            self._gps_on = True
            logger.info("GPS engine ON. Tunggu fix (cold: ~60 detik, warm: ~15 detik).")
            return True
        logger.warning("GPS power ON gagal: %s", resp.strip())
        return False

    def gps_power_off(self) -> bool:
        """Matikan GPS engine (hemat daya jika tidak dibutuhkan terus-menerus)."""
        resp = self.send_at("AT+CGPS=0", wait=1.0)
        self._gps_on = False
        return "OK" in resp

    def _parse_cgpsinfo(self, raw: str) -> dict | None:
        """
        Parse respons AT+CGPSINFO.

        Format NMEA dari SIM7600E:
          +CGPSINFO: <lat>,<N/S>,<lon>,<E/W>,<date>,<utc_time>,<alt>,<speed>,<course>

        Contoh ada fix:
          +CGPSINFO: 0114.5506,S,11649.5982,E,260625,033042.0,8.2,0.0,0.0

        Contoh tidak ada fix:
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
                """Konversi NMEA ddmm.mmmm → decimal degrees."""
                # Cari titik desimal, 2 digit sebelumnya adalah menit
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

            # Format waktu UTC: HHMMSS.s → HH:MM:SS
            utc_fmt = f"{utc[:2]}:{utc[2:4]}:{utc[4:]}" if len(utc) >= 6 else utc
            # Format tanggal: DDMMYY → DD/MM/20YY
            date_fmt = f"{date[:2]}/{date[2:4]}/20{date[4:]}" if len(date) == 6 else date

            return {
                "fix":          True,
                "lat":          lat,
                "lon":          lon,
                "altitude_m":   alt,
                "speed_kmh":    round(spd * 1.852, 2) if spd is not None else None,  # knot→km/h
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
        Ambil koordinat GPS dari SIM7600E.

        Jika GPS engine belum ON, akan dinyalakan otomatis.
        Akan polling AT+CGPSINFO sampai ada fix atau timeout.

        Return dict:
          fix=True  → {"fix": True, "lat": float, "lon": float, ...}
          fix=False → {"fix": False, "reason": str}
        """
        if not self._gps_on:
            if not self.gps_power_on():
                return {"fix": False, "reason": "GPS engine gagal dinyalakan"}

        logger.info("Menunggu GPS fix (timeout %ds)...", timeout)
        elapsed = 0.0

        while elapsed < timeout:
            raw = self.send_at("AT+CGPSINFO", wait=1.0)
            result = self._parse_cgpsinfo(raw)

            if result:
                logger.info(
                    "✅ GPS fix! lat=%.6f, lon=%.6f, alt=%.1fm, spd=%.1fkm/h",
                    result["lat"], result["lon"],
                    result.get("altitude_m") or 0,
                    result.get("speed_kmh") or 0,
                )
                return result

            logger.debug("Belum ada fix (%.0fs/%.0fs)...", elapsed, timeout)
            time.sleep(interval)
            elapsed += interval + 1.0   # +1 dari wait send_at

        return {
            "fix":    False,
            "reason": f"Timeout {timeout}s — pastikan antena GPS terpasang dan langit terbuka",
        }

    def get_gps_location(self) -> tuple[float, float] | None:
        """
        Shortcut: return (lat, lon) atau None jika tidak ada fix.
        Cocok untuk dipakai di main.py saat startup.
        """
        result = self.get_gps()
        if result.get("fix"):
            return result["lat"], result["lon"]
        return None

    def close(self):
        if self._gps_on:
            self.gps_power_off()
        self.ser.close()


# ─── Mock GPS untuk mode testing ─────────────────────────────────
class MockSIM7600:
    """Dipakai saat RUN_MODE=mock — tidak butuh hardware SIM7600."""
    _gps_on = False

    def gps_power_on(self) -> bool:
        self._gps_on = True
        return True

    def gps_power_off(self) -> bool:
        self._gps_on = False
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

    def get_gps_location(self) -> tuple[float, float]:
        return (-1.265400, 116.831200)

    def check_module(self) -> bool: return True
    def signal_quality(self) -> str: return "+CSQ: 20,0\r\nOK"
    def network_registration(self) -> str: return "+CREG: 0,1\r\nOK"
    def send_at(self, cmd, wait=1.0) -> str: return "OK"
    def close(self): pass


if __name__ == "__main__":
    # Test langsung: python sim7600.py
    import json
    modem = SIM7600()
    print("Module:", modem.check_module())
    print("Signal:", modem.signal_quality().strip())
    result = modem.get_gps(timeout=90)
    print("GPS:", json.dumps(result, indent=2))
    modem.close()
