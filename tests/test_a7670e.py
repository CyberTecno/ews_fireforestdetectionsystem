"""
TEST 8 — A7670E / SIM7670E (LTE Cat-1 4G + GNSS) Diagnostic Test

Cek lengkap: koneksi serial, AT dasar, SIM card, kualitas sinyal, GPS fix,
dan status koneksi data internet (dibawa naik via ModemManager/NetworkManager,
bukan langsung lewat AT - lihat docs/DEPLOYMENT.md).

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
        result(FAIL, "Tidak ada port serial terdeteksi.")
        print("  Pastikan A7670E/SIM7670E terpasang dan driver terinstall.")
        print("  Coba: ls /dev/ttyUSB*")
        return None

    print(f"  Port terdeteksi ({len(ports)}):")
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
        result(OK, f"Akan gunakan port: {chosen}")
    else:
        result(FAIL, "Tidak ada /dev/ttyUSB* ditemukan.")
    return chosen


def test_basic_at(ser):
    header("TEST 2: Koneksi Serial & AT Command Dasar")
    resp = send_at(ser, "AT")
    if "OK" in resp:
        result(OK, "AT command", "modul merespons")
    else:
        result(FAIL, "AT command tidak merespons.", f"raw: {resp!r}")
        print("\n  Kemungkinan penyebab:")
        print("  - Port salah (coba --port /dev/ttyUSB1 atau ttyUSB3)")
        print("  - Baudrate salah (default 115200)")
        print("  - Modul belum dinyalakan / power issue")
        return False

    resp = send_at(ser, "ATI")
    result(INFO, "Info modul:", resp.replace("\r\n", " | "))
    resp = send_at(ser, "AT+CGSN")
    imei = re.search(r"\d{15}", resp)
    result(OK if imei else WARN, "IMEI:", imei.group() if imei else f"raw: {resp!r}")
    return True


def test_sim_card(ser):
    header("TEST 3: SIM Card")
    resp = send_at(ser, "AT+CIMI")
    imsi = re.search(r"\d{10,15}", resp)
    if imsi:
        result(OK, "SIM terpasang. IMSI:", imsi.group())
    else:
        result(FAIL, "SIM tidak terdeteksi atau belum unlock.")
        return False

    resp = send_at(ser, "AT+CPIN?")
    if "READY" in resp:
        result(OK, "SIM PIN status: READY")
    elif "SIM PIN" in resp:
        result(FAIL, "SIM masih terkunci PIN!")
        return False
    else:
        result(WARN, "Status PIN:", resp)

    resp = send_at(ser, "AT+COPS?", wait=3)
    op = re.search(r'\+COPS: \d+,\d+,"([^"]+)"', resp)
    result(OK if op else WARN, "Operator:", op.group(1) if op else f"raw: {resp}")
    return True


def test_signal(ser):
    header("TEST 4: Kualitas Sinyal")
    resp = send_at(ser, "AT+CREG?")
    creg = re.search(r"\+CREG: \d+,(\d+)", resp)
    reg_status = {
        "0": "Tidak terdaftar, tidak mencari", "1": "Terdaftar (home network)",
        "2": "Mencari jaringan...", "3": "Registrasi ditolak", "5": "Terdaftar (roaming)",
    }
    if creg:
        stat = creg.group(1)
        icon = OK if stat in ("1", "5") else WARN if stat == "2" else FAIL
        result(icon, "Registrasi jaringan:", reg_status.get(stat, f"Status {stat}"))
    else:
        result(WARN, "Tidak bisa baca status registrasi")

    resp = send_at(ser, "AT+CSQ")
    csq = re.search(r"\+CSQ: (\d+),(\d+)", resp)
    if csq:
        rssi = int(csq.group(1))
        if rssi == 99:
            result(WARN, "Sinyal: tidak diketahui (99) - pastikan antena LTE terpasang")
        else:
            dbm = -113 + (rssi * 2)
            level = "Lemah" if rssi < 10 else "Sedang" if rssi < 20 else "Kuat"
            result(OK if rssi >= 10 else WARN, f"Sinyal: RSSI={rssi}/31, ~{dbm}dBm", level)
    else:
        result(FAIL, "Tidak bisa baca kualitas sinyal")
        return False
    return True


def test_gps(ser, timeout=90):
    header(f"TEST 5: GNSS/GPS (timeout {timeout}s, A7670E/SIM7670E command set)")
    print("  Pastikan antena GNSS terpasang dan ada langit terbuka.")
    print("  Cold start bisa butuh 15-60 detik.\n")

    # A7670E/SIM7670E pakai AT+CGNSSPWR=1 (modul SIM7600 lama pakai AT+CGPS=1 — berbeda!)
    resp = send_at(ser, "AT+CGNSSPWR=1", wait=2)
    if "OK" in resp or "READY" in resp:
        result(OK, "GNSS engine ON")
    else:
        result(FAIL, "GNSS engine gagal dinyalakan:", repr(resp))
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
                    result(OK, "GPS FIX BERHASIL!")
                    print(f"\n  {'Latitude':<15}: {lat}")
                    print(f"  {'Longitude':<15}: {lon}")
                    print(f"  {'Altitude':<15}: {alt} m")
                    print(f"\n  Google Maps: https://maps.google.com/?q={lat},{lon}")
                    return True
                except Exception as e:
                    result(WARN, f"Parse error: {e}")
        sys.stdout.write(f"\r  [{elapsed:3d}s/{timeout}s] Menunggu fix...")
        sys.stdout.flush()
        time.sleep(interval)
        elapsed += interval + 1
    print()
    result(FAIL, f"GPS timeout setelah {timeout}s.")
    print("\n  Tips: pindah ke tempat terbuka (dekat jendela/outdoor), atau tambah --gps-timeout 180")
    return False


def test_data_connection(ser, apn="internet"):
    header("TEST 6: Status Koneksi Data Internet")
    resp = send_at(ser, "AT+CGPADDR=1", wait=2)
    ip = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", resp)
    if ip:
        result(OK, "IP address aktif:", ip.group(1))
    else:
        result(WARN, "Belum ada IP dari modem langsung")
        result(INFO, "Internet biasanya jalan via ModemManager (cek: mmcli -L, ip addr show)")

    resp = send_at(ser, "AT+CGDCONT?", wait=2)
    result(INFO, "APN config:", resp.replace("\r\n", " | ").strip())
    if apn not in resp:
        result(INFO, f"Set APN ke '{apn}'...")
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
        result(OK, f"Serial terbuka: {port} @ {args.baudrate} baud")
    except Exception as e:
        result(FAIL, f"Gagal buka serial port: {e}")
        print(f"\n  Coba: sudo chmod 666 {port}")
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
            print(f"\n{INFO} Test GPS dilewati (--skip-gps)")

        total += 1
        if test_data_connection(ser, apn=args.apn):
            passed += 1
    finally:
        ser.close()

    header(f"RINGKASAN: {passed}/{total} test lulus")
    if passed == total:
        print("  Semua test LULUS. Modul siap digunakan.\n")
    elif passed >= total - 1:
        print("  Hampir semua test lulus. Cek warning di atas.\n")
    else:
        print("  Ada test yang GAGAL. Selesaikan masalah di atas.\n")
        print("  Debug tambahan: ls -la /dev/ttyUSB* | dmesg | grep ttyUSB | "
              "sudo systemctl status ModemManager")


if __name__ == "__main__":
    main()
