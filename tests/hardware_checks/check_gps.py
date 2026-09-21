"""
CHECK — GPS / GNSS (verify data GPS REALLY comes from the physical module
A7670E/SIM7670E or SIM7600, not the old cache/fallback config)

Why do you need this script:
main.py only uses GPS passively (polls every cycle). This script
  secara eksplisit:
1. Detect the installed module (A7670E or SIM7600) along with its port.
2. Check that the module really responds to AT commands (not dead port/nyasar).
3. Turn on GNSS & poll AT+CGPSINFO until it can fix or timeout.
4. Display RAW NMEA response from the module (+CGPSINFO: ...) as proof
that data is really just being read now from the GNSS engine, isn't it
an old/hardcoded value.
5. Print a summary of PASS/FAIL, and AT THE SAME TIME write the results to efws.log
(the same logger is used main.py) so that there is a permanent trace.

IMPORTANT (why is this file NOT named tests/test_gps.py):
Placed in tests/hardware_checks/ with the prefix "check_" (not "test_")
so that it is NOT collected by pytest -- this script accesses the hardware
real serial (open port /dev/ttyUSBx) which will crash/hang if
pytest tries to import it in a modemless environment (CI, dev laptop,
etc.). Run it manually, not via pytest.

Usage:
  python3 tests/hardware_checks/check_gps.py
  python3 tests/hardware_checks/check_gps.py --timeout 120
  python3 tests/hardware_checks/check_gps.py --force        # abaikan .sim_cache, scan ulang port
  python3 tests/hardware_checks/check_gps.py --port /dev/ttyUSB2 --module a7670e   # paksa, skip auto-detect
"""
import sys
import os
import json
import argparse
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import settings

# ─── Logger: use the SAME handler as main.py (console + efws.log) ────
# So that the results of this check are also permanently recorded in the same log file,
# not just appear on the screen and then disappear.
Path(settings.LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.LOG_PATH, mode="a"),
    ],
)
logger = logging.getLogger("efws.check_gps")

OK, FAIL, WARN, INFO = "[OK]  ", "[FAIL]", "[WARN]", "[INFO]"
SEP = "-" * 64


def header(title):
    line = f"\n{SEP}\n  {title}\n{SEP}"
    print(line)
    logger.info("=== %s ===", title)


def result(status, label, value=""):
    val = f"  -> {value}" if value else ""
    print(f"  {status} {label}{val}")
    logger.info("%s %s%s", status.strip(), label, (f" -> {value}" if value else ""))


def main():
    parser = argparse.ArgumentParser(description="Check whether GPS actually retrieves data from A7670E/SIM7600")
    parser.add_argument("--timeout", type=int, default=settings._int("EFWS_GPS_TIMEOUT", 90),
                         help="Seconds waiting for GNSS fix (default: EFWS_GPS_TIMEOUT / 90s)")
    parser.add_argument("--force", action="store_true", help="Ignore .sim_cache, rescan all ports")
    parser.add_argument("--port", default=None, help="Force certain ports (skip auto-scan), requires --module")
    parser.add_argument("--module", choices=["a7670e", "sim7600"], default=None,
                         help="Force a specific module (used with --port)")
    args = parser.parse_args()

    header("CHECK GPS — Detect module & retrieve real fix")

    if settings.RUN_MODE == "mock":
        result(WARN, "RUN_MODE=mock", "GPS will be simulated (MockSimInterface), NOT real hardware data")
        print("Set EFWS_RUN_MODE=hardware in .env for real physical module tests.")

    # ── 1) Detect/select module ──────────────────────────────────
    from communication.sim_detector import detect_sim, SimInterface, scan_ports

    try:
        if args.port and args.module:
            header(f"Force module:{args.module.upper()} @ {args.port}")
            sim = SimInterface(port=args.port, module=args.module)
        else:
            header("Auto-detect SIM module (A7670E vs SIM7600)")
            sim = detect_sim(force_scan=args.force)
    except Exception as e:
        result(FAIL, "Module detection", str(e))
        logger.error("GPS CHECK FAILED completely -- no SIM module detected: %s", e)
        sys.exit(1)

    is_mock = getattr(sim, "module", "") == "mock"
    result(OK if not is_mock else WARN, "Module detected", f"{sim.module.upper()} @ {sim.port}")

    # ── 2) Module actually responds to AT (not dead port) ────────
    header("Check the module responds to AT commands")
    try:
        alive = sim.check_module()
        result(OK if alive else FAIL, "AT ping", "OK" if alive else "NOT responding")
        if not alive and not is_mock:
            logger.error("GPS CHECK: module %s @ %s is NOT responding to AT command.", sim.module.upper(), sim.port)
    except Exception as e:
        result(FAIL, "AT ping", str(e))

    try:
        csq = sim.signal_quality().strip()
        result(INFO, "Signal quality (AT+CSQ)", csq.replace("\r\n", " | "))
    except Exception as e:
        result(WARN, "Signal quality", f"failed to read:{e}")

    # ── 3) Take the REAL GPS fix (AT+CGPSINFO poll) ──────────────
    header(f"Minta GPS fix (timeout {args.timeout}s) -- this will wait, make sure the antenna GNSS outside /langit is open")
    logger.info("GPS CHECK: start polling fix from %s @ %s (timeout=%ds)",
                sim.module.upper(), sim.port, args.timeout)

    gps_result = sim.get_gps(timeout=args.timeout)

    if gps_result.get("fix"):
        result(OK, "GPS FIX received", f"lat={gps_result['lat']:.6f}, lon={gps_result['lon']:.6f}")
        result(INFO, "Altitude", f"{gps_result.get('altitude_m')} m")
        result(INFO, "Fixed time (UTC)", f"{gps_result.get('date_utc')} {gps_result.get('time_utc')}")

        # Direct proof that this is LIVE data from the module, not old values:
        # display raw NMEA response exactly as the module sent.
        raw_nmea = gps_result.get("raw")
        if raw_nmea:
            result(INFO, "RAW +CGPSINFO from the module", raw_nmea)
        if gps_result.get("_mock"):
            result(WARN, "NOTICE", "This is MOCK data (RUN_MODE=mock) -- NOT from real GPS hardware.")

        logger.info(
            "GPS CHECK SUCCESS: real fix from %s @ %s -> lat=%.6f lon=%.6f alt=%sm time=%s %s | raw=%s",
            sim.module.upper(), sim.port,
            gps_result["lat"], gps_result["lon"],
            gps_result.get("altitude_m"), gps_result.get("date_utc"), gps_result.get("time_utc"),
            raw_nmea,
        )
        exit_code = 0
    else:
        reason = gps_result.get("reason", "unknown")
        result(FAIL, "GPS NOT fixed", reason)
        logger.warning(
            "GPS CHECK FAILED fix: module %s @ %s did not get a fix in %ds. Reason: %s",
            sim.module.upper(), sim.port, args.timeout, reason,
        )
        print("\n  Possible causes:")
        print("- The GNSS antenna is not installed / the cable is loose")
        print("- Indoor/closed sky module (GNSS needs line-of-sight to satellite)")
        print("- The first cold start can take 30-60+ seconds, try a larger --timeout")
        exit_code = 1

    sim.close()

    header("Summary")
    print(json.dumps({
        "module": sim.module,
        "port": sim.port,
        "fix": gps_result.get("fix", False),
        "lat": gps_result.get("lat"),
        "lon": gps_result.get("lon"),
        "mock": bool(gps_result.get("_mock", False)),
    }, indent=2))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
