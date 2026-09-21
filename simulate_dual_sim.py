"""
Strict simulation: running sim_detector.py + a7670e.py + sim7600_legacy.py
property of this project (NOT new code) counters fake AT-command responses that
emulates two real physical modules: A7670E and SIM7600.

There are no new assumptions about the AT command / fingerprint -- all values ​​are below
taken directly from the existing code in communication/*.py.
"""
import sys
import os
import time
import serial as real_serial_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("EFWS_RUN_MODE", "hardware")  # forced through the real detector route, not Mock

# ── AT response profile per module (taken from _FINGERPRINTS & AT command in original code) ──
PROFILES = {
    "a7670e": {
        "AT":            "OK\r\n",
        "ATI":           "Model: A7670E\r\nOK\r\n",
        "AT+CGNSSPWR=1": "+CGNSSPWR: READY!\r\nOK\r\n",
        "AT+CGNSSPWR=0": "OK\r\n",
        "AT+CGPSINFO":   "+CGPSINFO: 0114.5506,S,11649.5982,E,260625,033042.0,8.2,0.0,0.0\r\nOK\r\n",
        "AT+CSQ":        "+CSQ: 22,0\r\nOK\r\n",
        "AT+CREG?":      "+CREG: 0,1\r\nOK\r\n",
        # SIM7600-only command intentionally NOT defined -> if called, it will
        # falls to the default blank, so it appears that the detector selected the wrong driver.
    },
    "sim7600": {
        "AT":            "OK\r\n",
        "ATI":           "Model: SIM7600E-H\r\nOK\r\n",
        "AT+CGPS=1":     "+CGPS: 1\r\nOK\r\n",
        "AT+CGPS=0":     "OK\r\n",
        "AT+CGPSINFO":   "+CGPSINFO: 0114.5506,S,11649.5982,E,260625,033042.0,8.2,0.0,0.0\r\nOK\r\n",
        "AT+CSQ":        "+CSQ: 18,0\r\nOK\r\n",
        "AT+CREG?":      "+CREG: 0,1\r\nOK\r\n",
        # A7670E-only command intentionally NOT defined.
    },
    "a7670e_via_sim7670_fingerprint": {
        # Edge case: some A7670E modules report themselves as "SIM7670" in ATI,
        # not "A7670E" -- this is why the documentation/project filenames use mixed names
        # stir. _FINGERPRINTS in sim_detector.py has put "SIM7670" as
        # alias for key "a7670e", so this tests whether it remains detected
        # CORRECT as a7670e (not sim7600, and not failed to recognize).
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
    """Emulates pyserial.Serial exactly the way sim_detector/a7670e/sim7600_legacy uses it:
write() then read(in_waiting or 1) after a short sleep."""

    def __init__(self, port, baudrate=115200, timeout=2, profile=None):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._profile = profile or {}
        self._pending = b""
        self.calls = []  # logs all commands sent, for strict verification

    def reset_input_buffer(self):
        self._pending = b""

    def write(self, data: bytes):
        cmd = data.decode(errors="ignore").strip()
        self.calls.append(cmd)
        resp = self._profile.get(cmd, "")  # unknown command -> empty string (exactly like no-response)
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
    """Return replacement serial.Serial(...) which selects the profile based on the requested port."""
    def factory(port, baudrate=115200, timeout=2, *a, **kw):
        profile_name = port_to_profile.get(port)
        if profile_name is None:
            raise real_serial_module.SerialException(f"no device on {port} (simulasi)")
        return FakeSerial(port, baudrate, timeout, profile=PROFILES[profile_name])
    return factory


def run_scenario(label: str, profile_name: str, sim_port: str = "/dev/ttyUSB2"):
    print(f"\n{'='*70}\nSKENARIO: {label}  (port={sim_port}, AT profile={profile_name})\n{'='*70}")

    # Patch serial.Serial BEFORE import communication.* so that all modules
    # (sim_detector, a7670e, sim7600_legacy) which has `import serial` patched,
    # because they all refer to the same object module `serial`.
    real_serial_module.Serial = make_fake_serial_factory({sim_port: profile_name})

    # os.path.exists calls scan_ports() to filter "existing" port candidates --
    # patch so that the simulation port is considered to exist, other ports are considered not to exist.
    import communication.sim_detector as sim_detector
    real_exists = os.path.exists
    os.path.exists = lambda p: (p == sim_port) or (not p.startswith("/dev/ttyUSB") and real_exists(p))

    # Reset the cache so that each scenario is actually rescanned, not using the results of another scenario
    import importlib
    importlib.reload(sim_detector)
    if sim_detector.CACHE_FILE.exists():
        sim_detector.CACHE_FILE.unlink()

    try:
        info = sim_detector.scan_ports()
        print(f"  scan_ports()   -> {info}")
        assert info is not None, "FAILED: not detected at all"
        expected_module = "a7670e" if "a7670e" in profile_name else "sim7600"
        assert info["module"] == expected_module, (
            f"FAILED: expected '{expected_module}', got '{info['module']}'"
        )
        print(f"[OK] module detected correctly:{info['module']}")

        sim = sim_detector.detect_sim(force_scan=True)
        print(f"  detect_sim()   -> {sim!r}, driver class = {type(sim._drv).__name__}")

        expected_driver = "A7670E" if expected_module == "a7670e" else "SIM7600"
        actual_driver = type(sim._drv).__name__
        assert actual_driver == expected_driver, (
            f"FAILED: expected driver {expected_driver}, got {actual_driver}"
        )
        print(f"[OK] Correct driver used:{actual_driver} "
              f"(from communication.{sim._drv.__class__.__module__.split('.')[-1]})")

        gps = sim.get_gps(timeout=5, interval=0.01)
        print(f"  get_gps()      -> {gps}")
        assert gps.get("fix") is True, f"FAILED: GPS not fixed --{gps}"
        print(f"[OK] GPS fix successfully obtained")

        cmds_sent = sim._drv.ser.calls
        gnss_cmd = "AT+CGNSSPWR=1" if expected_module == "a7670e" else "AT+CGPS=1"
        assert gnss_cmd in cmds_sent, (
            f"FAILED: correct command GNSS ({gnss_cmd}) was never sent."
            f"Commands actually sent:{cmds_sent}"
        )
        print(f"[OK] command GNSS used according to the module:{gnss_cmd}")

        print(f"[OK] ALL CHECK PASS for scenario:{label}")
        return True

    except AssertionError as e:
        print(f"  [FAIL] {e}")
        return False
    except Exception as e:
        print(f"  [UNEXPECTED ERROR] {type(e).__name__}: {e}")
        return False
    finally:
        os.path.exists = real_exists


def run_anemometer_conflict_check():
    """Regression check: scan_ports() must never open or write to
ANEMOMETER_PORT, even though the port is on the system and matches pattern /dev/ttyUSB*."""
    print(f"\n{'='*70}\nSCENARIO: Anemometer port may not be scanned\n{'='*70}")

    import communication.sim_detector as sim_detector
    import importlib
    importlib.reload(sim_detector)
    from config import settings as cfg

    anem_port = cfg.ANEMOMETER_PORT
    modem_port = "/dev/ttyUSB2"
    print(f"ANEMOMETER_PORT (should be avoided) ={anem_port}")
    print(f"  Port modem simulasi                = {modem_port}")

    opened_ports = []

    def spy_factory(port, baudrate=115200, timeout=2, *a, **kw):
        opened_ports.append(port)
        if port == modem_port:
            return FakeSerial(port, baudrate, timeout, profile=PROFILES["a7670e"])
        # if the anemometer port is opened, return a "successful" serial
        # so that this test purely checks WHETHER the port was touched, not the error
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
        print(f"Ports actually opened scan_ports():{opened_ports}")
        assert anem_port not in opened_ports, (
            f"FAIL:{anem_port}(anemometer port) is also opened when scanning the modem!"
        )
        print(f"  [OK] {anem_port}never touched by scan_ports()")
        assert info is not None and info["module"] == "a7670e"
        print(f"[OK] The modem is still detected correctly even if the port anemometer is excluded")
        return True
    except AssertionError as e:
        print(f"  [FAIL] {e}")
        return False
    finally:
        os.path.exists = real_exists


if __name__ == "__main__":
    results = {}
    results["A7670E (ATI='A7670E')"]              = run_scenario("Only A7670E installed", "a7670e")
    results["SIM7600 (ATI='SIM7600E-H')"]          = run_scenario("Only SIM7600 installed", "sim7600")
    results["A7670E via fingerprint 'SIM7670E'"]   = run_scenario(
        "A7670E whose ATI says 'SIM7670E' (firmware variant)", "a7670e_via_sim7670_fingerprint"
    )
    results["The port anemometer must not be scanned"] = run_anemometer_conflict_check()

    print(f"\n{'='*70}\nRINGKASAN\n{'='*70}")
    all_ok = True
    for label, ok in results.items():
        print(f"  {'[PASSED]' if ok else '[FAIL]'}  {label}")
        all_ok = all_ok and ok
    sys.exit(0 if all_ok else 1)
