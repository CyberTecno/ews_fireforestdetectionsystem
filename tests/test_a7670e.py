"""
TEST 8 — A7670E / SIM7670E (LTE Cat-1 4G + GNSS) Diagnostic Test

Complete check: serial connection, basic AT, SIM card, signal quality, GPS fix,
and internet data connection status (brought up via ModemManager/NetworkManager,
not directly via AT - see docs/DEPLOYMENT.md).

Usage:
  python3 tests/test_a7670e.py
  python3 tests/test_a7670e.py --port /dev/ttyUSB2
  python3 tests/test_a7670e.py --port /dev/ttyUSB2 --gps-timeout 120
  python3 tests/test_a7670e.py --skip-gps
"""
import sys
import re
import time
import argparse
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import serial
import serial.tools.list_ports

OK, FAIL, WARN, INFO = "[OK]  ", "[FAIL]", "[WARN]", "[INFO]"
SEP = "-" * 60


def header(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


def result(status, label, value=""):
    val = f"  -> {value}" if value else ""
    print(f"  {status} {label}{val}")


def send_at(ser, cmd, wait=1.5):
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)
    raw = ser.read(ser.in_waiting or 1)
    return raw.decode(errors="ignore").strip()


def test_find_port(preferred=None):
    header("TEST 1: Deteksi Port Serial")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        result(FAIL, "No serial port detected.")
        print("Make sure the A7670E/SIM7670E is installed and the drivers are installed.")
        print("Try: ls /dev/ttyUSB*")
        return None

    print(f"Port detected ({len(ports)}):")
    for p in ports:
        print(f"    {p.device:20s} | {p.description}")

    candidates = [p.device for p in ports if "USB" in p.device]
    priority = ["/dev/ttyUSB2", "/dev/ttyUSB3", "/dev/ttyUSB1", "/dev/ttyUSB0"]

    chosen = preferred if preferred in [p.device for p in ports] else None
    if not chosen:
        for c in priority:
            if c in candidates:
                chosen = c
                break
        if not chosen and candidates:
            chosen = candidates[0]

    if chosen:
        result(OK, f"Will use port:{chosen}")
    else:
        result(FAIL, "No /dev/ttyUSB* found.")
    return chosen


def test_basic_at(ser):
    header("TEST 2: Serial Connection & Basic AT Command")
    resp = send_at(ser, "AT")
    if "OK" in resp:
        result(OK, "AT command", "the module responds")
    else:
        result(FAIL, "AT command is not responding.", f"raw: {resp!r}")
        print("\n  Possible causes:")
        print("- Wrong port (try --port /dev/ttyUSB1 or ttyUSB3)")
        print("- Incorrect baudrate (default 115200)")
        print("- The module has not been turned on / power issue")
        return False

    resp = send_at(ser, "ATI")
    result(INFO, "Module info:", resp.replace("\r\n", " | "))
    resp = send_at(ser, "AT+CGSN")
    imei = re.search(r"\d{15}", resp)
    result(OK if imei else WARN, "IMEI:", imei.group() if imei else f"raw: {resp!r}")
    return True


def test_sim_card(ser):
    header("TEST 3: SIM Card")
    resp = send_at(ser, "AT+CIMI")
    imsi = re.search(r"\d{10,15}", resp)
    if imsi:
        result(OK, "SIM installed. IMSI:", imsi.group())
    else:
        result(FAIL, "SIM not detected or not unlocked.")
        return False

    resp = send_at(ser, "AT+CPIN?")
    if "READY" in resp:
        result(OK, "SIM PIN status: READY")
    elif "SIM PIN" in resp:
        result(FAIL, "SIM is still PIN locked!")
        return False
    else:
        result(WARN, "Status PIN:", resp)

    resp = send_at(ser, "AT+COPS?", wait=3)
    op = re.search(r'\+COPS: \d+,\d+,"([^"]+)"', resp)
    result(OK if op else WARN, "Operator:", op.group(1) if op else f"raw: {resp}")
    return True


def test_signal(ser):
    header("TEST 4: Signal Quality")
    resp = send_at(ser, "AT+CREG?")
    creg = re.search(r"\+CREG: \d+,(\d+)", resp)
    reg_status = {
        "0": "Not registered, not searching", "1": "Registered (home network)",
        "2": "Searching for network...", "3": "Registration denied", "5": "Registered (roaming)",
    }
    if creg:
        stat = creg.group(1)
        icon = OK if stat in ("1", "5") else WARN if stat == "2" else FAIL
        result(icon, "Network registration:", reg_status.get(stat, f"Status {stat}"))
    else:
        result(WARN, "Cannot read registration status")

    resp = send_at(ser, "AT+CSQ")
    csq = re.search(r"\+CSQ: (\d+),(\d+)", resp)
    if csq:
        rssi = int(csq.group(1))
        if rssi == 99:
            result(WARN, "Signal: unknown (99) - make sure antenna LTE is installed")
        else:
            dbm = -113 + (rssi * 2)
            level = "Weak" if rssi < 10 else "Currently" if rssi < 20 else "Strong"
            result(OK if rssi >= 10 else WARN, f"Signal: RSSI={rssi}/31, ~{dbm}dBm", level)
    else:
        result(FAIL, "Cannot read signal quality")
        return False
    return True


def test_gps(ser, timeout=90):
    header(f"TEST 5: GNSS/GPS (timeout {timeout}s, A7670E/SIM7670E command set)")
    print("Make sure the GNSS antenna is installed and there is open sky.")
    print("Cold start can take 15-60 seconds.\n")

    # A7670E/SIM7670E uses AT+CGNSSPWR=1 (old SIM7600 module uses AT+CGPS=1 — different!)
    resp = send_at(ser, "AT+CGNSSPWR=1", wait=2)
    if "OK" in resp or "READY" in resp:
        result(OK, "GNSS engine ON")
    else:
        result(FAIL, "GNSS engine failed to start:", repr(resp))
        return False

    elapsed, interval = 0, 3
    print(f"  Polling AT+CGPSINFO tiap {interval}s...")
    while elapsed < timeout:
        resp = send_at(ser, "AT+CGPSINFO", wait=1)
        match = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", resp)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]
            if len(parts) >= 9 and parts[0] != "":
                try:
                    def nmea_to_dd(nmea, direction):
                        dot = nmea.index(".")
                        dd = float(nmea[:dot - 2]) + float(nmea[dot - 2:]) / 60.0
                        return round(-dd if direction in ("S", "W") else dd, 6)

                    lat = nmea_to_dd(parts[0], parts[1])
                    lon = nmea_to_dd(parts[2], parts[3])
                    alt = float(parts[6]) if parts[6] else 0
                    print()
                    result(OK, "GPS FIX SUCCESSFUL!")
                    print(f"\n  {'Latitude':<15}: {lat}")
                    print(f"  {'Longitude':<15}: {lon}")
                    print(f"  {'Altitude':<15}: {alt} m")
                    print(f"\n  Google Maps: https://maps.google.com/?q={lat},{lon}")
                    return True
                except Exception as e:
                    result(WARN, f"Parse error: {e}")
        sys.stdout.write(f"\r  [{elapsed:3d}s/{timeout}s] Waiting for fix...")
        sys.stdout.flush()
        time.sleep(interval)
        elapsed += interval + 1
    print()
    result(FAIL, f"GPS timeout after{timeout}s.")
    print("\n Tip: move to an open place (near the window/outdoor), or add --gps-timeout 180")
    return False


def test_data_connection(ser, apn="internet"):
    header("TEST 6: Internet Data Connection Status")
    resp = send_at(ser, "AT+CGPADDR=1", wait=2)
    ip = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", resp)
    if ip:
        result(OK, "Active IP address:", ip.group(1))
    else:
        result(WARN, "There is no IP from the direct modem yet")
        result(INFO, "Internet usually works via ModemManager (check: mmcli -L, ip addr show)")

    resp = send_at(ser, "AT+CGDCONT?", wait=2)
    result(INFO, "APN config:", resp.replace("\r\n", " | ").strip())
    if apn not in resp:
        result(INFO, f"Set APN to '{apn}'...")
        send_at(ser, f'AT+CGDCONT=1,"IP","{apn}"')
    return True


def main():
    parser = argparse.ArgumentParser(description="A7670E/SIM7670E Diagnostic Test")
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", default=115200, type=int)
    parser.add_argument("--gps-timeout", default=90, type=int)
    parser.add_argument("--apn", default="internet")
    parser.add_argument("--skip-gps", action="store_true")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  A7670E / SIM7670E Diagnostic Test")
    print("=" * 60)

    port = test_find_port(args.port)
    if not port:
        sys.exit(1)

    try:
        ser = serial.Serial(port, args.baudrate, timeout=2)
        result(OK, f"Serial port open: {port} @ {args.baudrate} baud")
    except Exception as e:
        result(FAIL, f"Failed to open serial port:{e}")
        print(f"\n Try: sudo chmod 666{port}")
        sys.exit(1)

    passed, total = 0, 0
    try:
        for fn, args_ in [(test_basic_at, (ser,)), (test_sim_card, (ser,)), (test_signal, (ser,))]:
            total += 1
            if fn(*args_):
                passed += 1

        if not args.skip_gps:
            total += 1
            if test_gps(ser, timeout=args.gps_timeout):
                passed += 1
        else:
            print(f"\n{INFO}Test GPS skipped (--skip-gps)")

        total += 1
        if test_data_connection(ser, apn=args.apn):
            passed += 1
    finally:
        ser.close()

    header(f"SUMMARY:{passed}/{total}test passed")
    if passed == total:
        print("All tests PASS. Module ready to use.\n")
    elif passed >= total - 1:
        print("Almost all tests passed. Check the warning above.\n")
    else:
        print("There is a test that FAILED. Solve the above problem.\n")
        print("  Debug tambahan: ls -la /dev/ttyUSB* | dmesg | grep ttyUSB | "
              "sudo systemctl status ModemManager")


if __name__ == "__main__":
    main()
