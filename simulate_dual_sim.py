"""
Simulasi ketat: menjalankan sim_detector.py + a7670e.py + sim7600_legacy.py
milik project ini (BUKAN kode baru) melawan respons AT-command palsu yang
meniru dua modul fisik sungguhan: A7670E dan SIM7600.

Tidak ada asumsi baru soal AT command / fingerprint -- semua nilai di bawah
diambil langsung dari kode yang sudah ada di communication/*.py.
"""
import sys
import os
import time
import serial as real_serial_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("EFWS_RUN_MODE", "hardware")  # paksa lewat jalur real detector, bukan Mock

# ── Profil respons AT per modul (diambil dari _FINGERPRINTS & AT command di kode asli) ──
PROFILES = {
    "a7670e": {
        "AT":            "OK\r\n",
        "ATI":           "Model: A7670E\r\nOK\r\n",
        "AT+CGNSSPWR=1": "+CGNSSPWR: READY!\r\nOK\r\n",
        "AT+CGNSSPWR=0": "OK\r\n",
        "AT+CGPSINFO":   "+CGPSINFO: 0114.5506,S,11649.5982,E,260625,033042.0,8.2,0.0,0.0\r\nOK\r\n",
        "AT+CSQ":        "+CSQ: 22,0\r\nOK\r\n",
        "AT+CREG?":      "+CREG: 0,1\r\nOK\r\n",
        # SIM7600-only command sengaja TIDAK didefinisikan -> kalau kepanggil, akan
        # jatuh ke default kosong, supaya kelihatan kalau detector salah pilih driver.
    },
    "sim7600": {
        "AT":            "OK\r\n",
        "ATI":           "Model: SIM7600E-H\r\nOK\r\n",
        "AT+CGPS=1":     "+CGPS: 1\r\nOK\r\n",
        "AT+CGPS=0":     "OK\r\n",
        "AT+CGPSINFO":   "+CGPSINFO: 0114.5506,S,11649.5982,E,260625,033042.0,8.2,0.0,0.0\r\nOK\r\n",
        "AT+CSQ":        "+CSQ: 18,0\r\nOK\r\n",
        "AT+CREG?":      "+CREG: 0,1\r\nOK\r\n",
        # A7670E-only command sengaja TIDAK didefinisikan.
    },
    "a7670e_via_sim7670_fingerprint": {
        # Kasus tepi: sebagian modul A7670E melaporkan dirinya "SIM7670" di ATI,
        # bukan "A7670E" -- ini yang bikin dokumentasi/nama file project campur
        # aduk. _FINGERPRINTS di sim_detector.py sudah menaruh "SIM7670" sebagai
        # alias untuk key "a7670e", jadi ini menguji apakah itu tetap terdeteksi
        # BENAR sebagai a7670e (bukan sim7600, dan bukan gagal dikenali).
        "AT":            "OK\r\n",
        "ATI":           "Model: SIM7670E\r\nOK\r\n",
        "AT+CGNSSPWR=1": "+CGNSSPWR: READY!\r\nOK\r\n",
        "AT+CGNSSPWR=0": "OK\r\n",
        "AT+CGPSINFO":   "+CGPSINFO: 0114.5506,S,11649.5982,E,260625,033042.0,8.2,0.0,0.0\r\nOK\r\n",
        "AT+CSQ":        "+CSQ: 20,0\r\nOK\r\n",
        "AT+CREG?":      "+CREG: 0,1\r\nOK\r\n",
    },
}


class FakeSerial:
    """Meniru pyserial.Serial persis sesuai cara sim_detector/a7670e/sim7600_legacy memakainya:
    write() lalu read(in_waiting or 1) setelah sleep singkat."""

    def __init__(self, port, baudrate=115200, timeout=2, profile=None):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._profile = profile or {}
        self._pending = b""
        self.calls = []  # log semua command yang dikirim, untuk verifikasi ketat

    def reset_input_buffer(self):
        self._pending = b""

    def write(self, data: bytes):
        cmd = data.decode(errors="ignore").strip()
        self.calls.append(cmd)
        resp = self._profile.get(cmd, "")  # command tak dikenal -> string kosong (persis spt no-response)
        self._pending = resp.encode()

    @property
    def in_waiting(self):
        return len(self._pending)

    def read(self, n):
        data, self._pending = self._pending[:n], self._pending[n:]
        return data

    def close(self):
        pass


def make_fake_serial_factory(port_to_profile: dict):
    """Return pengganti serial.Serial(...) yang pilih profil berdasarkan port yang diminta."""
    def factory(port, baudrate=115200, timeout=2, *a, **kw):
        profile_name = port_to_profile.get(port)
        if profile_name is None:
            raise real_serial_module.SerialException(f"no device on {port} (simulasi)")
        return FakeSerial(port, baudrate, timeout, profile=PROFILES[profile_name])
    return factory


def run_scenario(label: str, profile_name: str, sim_port: str = "/dev/ttyUSB2"):
    print(f"\n{'='*70}\nSKENARIO: {label}  (port={sim_port}, profil AT={profile_name})\n{'='*70}")

    # Patch serial.Serial SEBELUM import communication.* supaya semua modul
    # (sim_detector, a7670e, sim7600_legacy) yang sudah `import serial` ikut kepatch,
    # karena mereka semua merujuk ke object module `serial` yang sama.
    real_serial_module.Serial = make_fake_serial_factory({sim_port: profile_name})

    # os.path.exists dipanggil scan_ports() untuk memfilter kandidat port yang "ada" --
    # patch supaya port simulasi dianggap ada, port lain dianggap tidak ada.
    import communication.sim_detector as sim_detector
    real_exists = os.path.exists
    os.path.exists = lambda p: (p == sim_port) or (not p.startswith("/dev/ttyUSB") and real_exists(p))

    # Reset cache supaya tiap skenario benar-benar scan ulang, bukan pakai hasil skenario lain
    import importlib
    importlib.reload(sim_detector)
    if sim_detector.CACHE_FILE.exists():
        sim_detector.CACHE_FILE.unlink()

    try:
        info = sim_detector.scan_ports()
        print(f"  scan_ports()   -> {info}")
        assert info is not None, "GAGAL: tidak terdeteksi sama sekali"
        expected_module = "a7670e" if "a7670e" in profile_name else "sim7600"
        assert info["module"] == expected_module, (
            f"GAGAL: seharusnya terdeteksi '{expected_module}', malah '{info['module']}'"
        )
        print(f"  [OK] modul terdeteksi benar: {info['module']}")

        sim = sim_detector.detect_sim(force_scan=True)
        print(f"  detect_sim()   -> {sim!r}, driver class = {type(sim._drv).__name__}")

        expected_driver = "A7670E" if expected_module == "a7670e" else "SIM7600"
        actual_driver = type(sim._drv).__name__
        assert actual_driver == expected_driver, (
            f"GAGAL: driver seharusnya {expected_driver}, malah dapat {actual_driver}"
        )
        print(f"  [OK] driver yang dipakai benar: {actual_driver} "
              f"(dari communication.{sim._drv.__class__.__module__.split('.')[-1]})")

        gps = sim.get_gps(timeout=5, interval=0.01)
        print(f"  get_gps()      -> {gps}")
        assert gps.get("fix") is True, f"GAGAL: GPS tidak fix -- {gps}"
        print(f"  [OK] GPS fix berhasil didapat")

        cmds_sent = sim._drv.ser.calls
        gnss_cmd = "AT+CGNSSPWR=1" if expected_module == "a7670e" else "AT+CGPS=1"
        assert gnss_cmd in cmds_sent, (
            f"GAGAL: perintah GNSS yang benar ({gnss_cmd}) tidak pernah dikirim. "
            f"Command yang benar-benar terkirim: {cmds_sent}"
        )
        print(f"  [OK] perintah GNSS yang dipakai sesuai modul: {gnss_cmd}")

        print(f"  [OK] SEMUA CEK LULUS untuk skenario: {label}")
        return True

    except AssertionError as e:
        print(f"  [FAIL] {e}")
        return False
    except Exception as e:
        print(f"  [ERROR TAK TERDUGA] {type(e).__name__}: {e}")
        return False
    finally:
        os.path.exists = real_exists


def run_anemometer_conflict_check():
    """Verifikasi fix: scan_ports() tidak boleh pernah membuka/menulis ke
    ANEMOMETER_PORT, walau port itu ada di sistem dan match pola /dev/ttyUSB*."""
    print(f"\n{'='*70}\nSKENARIO: Port anemometer tidak boleh ikut ter-scan\n{'='*70}")

    import communication.sim_detector as sim_detector
    import importlib
    importlib.reload(sim_detector)
    from config import settings as cfg

    anem_port = cfg.ANEMOMETER_PORT
    modem_port = "/dev/ttyUSB2"
    print(f"  ANEMOMETER_PORT (harus dihindari) = {anem_port}")
    print(f"  Port modem simulasi                = {modem_port}")

    opened_ports = []

    def spy_factory(port, baudrate=115200, timeout=2, *a, **kw):
        opened_ports.append(port)
        if port == modem_port:
            return FakeSerial(port, baudrate, timeout, profile=PROFILES["a7670e"])
        # kalau sampai port anemometer dibuka, kembalikan serial yang "berhasil"
        # supaya test ini murni mengecek APAKAH port itu disentuh, bukan errornya
        return FakeSerial(port, baudrate, timeout, profile={})

    real_serial_module.Serial = spy_factory
    real_exists = os.path.exists
    os.path.exists = lambda p: p in (modem_port, anem_port) or (
        not p.startswith("/dev/ttyUSB") and real_exists(p)
    )

    try:
        if sim_detector.CACHE_FILE.exists():
            sim_detector.CACHE_FILE.unlink()
        info = sim_detector.scan_ports()
        print(f"  Port yang benar-benar dibuka scan_ports(): {opened_ports}")
        assert anem_port not in opened_ports, (
            f"GAGAL: {anem_port} (port anemometer) ikut dibuka saat scan modem!"
        )
        print(f"  [OK] {anem_port} tidak pernah disentuh oleh scan_ports()")
        assert info is not None and info["module"] == "a7670e"
        print(f"  [OK] modem tetap terdeteksi benar walau anemometer port dikecualikan")
        return True
    except AssertionError as e:
        print(f"  [FAIL] {e}")
        return False
    finally:
        os.path.exists = real_exists


if __name__ == "__main__":
    results = {}
    results["A7670E (ATI='A7670E')"]              = run_scenario("Hanya A7670E terpasang", "a7670e")
    results["SIM7600 (ATI='SIM7600E-H')"]          = run_scenario("Hanya SIM7600 terpasang", "sim7600")
    results["A7670E via fingerprint 'SIM7670E'"]   = run_scenario(
        "A7670E yang ATI-nya bilang 'SIM7670E' (varian firmware)", "a7670e_via_sim7670_fingerprint"
    )
    results["Anemometer port tidak boleh ke-scan"] = run_anemometer_conflict_check()

    print(f"\n{'='*70}\nRINGKASAN\n{'='*70}")
    all_ok = True
    for label, ok in results.items():
        print(f"  {'[LULUS]' if ok else '[GAGAL]'}  {label}")
        all_ok = all_ok and ok
    sys.exit(0 if all_ok else 1)
