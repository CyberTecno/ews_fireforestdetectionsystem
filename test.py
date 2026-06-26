# from gpiozero import Buzzer
# from time import sleep

# BUZZER_PIN = 16

# buzzer = Buzzer(BUZZER_PIN)

# try:
#     while True:
#         print("Buzzer ON")
#         buzzer.on()
#         sleep(1)

#         print("Buzzer OFF")
#         buzzer.off()
#         sleep(1)

# except KeyboardInterrupt:
#     buzzer.off()
#     print("Program dihentikan")


# from gpiozero import DigitalInputDevice
# from time import sleep

# MQ135_PIN = 17

# sensor = DigitalInputDevice(MQ135_PIN)

# print("Menunggu sensor pemanasan...")

# sleep(30)

# try:
#     while True:
#         if sensor.value == 0:
#             print("⚠️ Gas/asap terdeteksi!")
#         else:
#             print("Udara normal")

#         sleep(1)

# except KeyboardInterrupt:
#     print("Program dihentikan")


"""
SIM7600E-H Diagnostic Test Script
===================================
Jalankan langsung di Raspberry Pi untuk cek semua fungsi modul:
  1. Koneksi serial & AT command dasar
  2. SIM card & registrasi jaringan
  3. Kualitas sinyal
  4. GPS fix (koordinat real)
  5. Koneksi data (ping ke internet)

Cara pakai:
  python test_sim7600.py
  python test_sim7600.py --port /dev/ttyUSB2
  python test_sim7600.py --port /dev/ttyUSB2 --gps-timeout 120
"""
import sys
import re
import time
import argparse
import serial
import serial.tools.list_ports

# ─── Warna terminal (ASCII safe, no emoji) ───────────────────────
OK   = "[OK]  "
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"
SEP  = "-" * 60


def header(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def result(status: str, label: str, value: str = ""):
    val = f"  -> {value}" if value else ""
    print(f"  {status} {label}{val}")


# ─── Serial helper ───────────────────────────────────────────────
def send_at(ser: serial.Serial, cmd: str, wait: float = 1.5) -> str:
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)
    raw = ser.read(ser.in_waiting or 1)
    return raw.decode(errors="ignore").strip()


# ─── Test 1: Deteksi port serial ─────────────────────────────────
def test_find_port(preferred: str = None) -> str | None:
    header("TEST 1: Deteksi Port Serial")

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        result(FAIL, "Tidak ada port serial terdeteksi.")
        print("\n  Pastikan SIM7600E HAT terpasang dan driver terinstall.")
        print("  Coba: ls /dev/ttyUSB*")
        return None

    print(f"  Port yang terdeteksi ({len(ports)}):")
    for p in ports:
        print(f"    {p.device:20s} | {p.description}")

    # Prioritas port yang dipakai SIM7600E
    candidates = [p.device for p in ports if "USB" in p.device]
    sim_candidates = ["/dev/ttyUSB2", "/dev/ttyUSB1", "/dev/ttyUSB0"]

    chosen = None
    if preferred and preferred in [p.device for p in ports]:
        chosen = preferred
    else:
        for c in sim_candidates:
            if c in candidates:
                chosen = c
                break
        if not chosen and candidates:
            chosen = candidates[0]

    if chosen:
        result(OK, f"Akan gunakan port: {chosen}")
    else:
        result(FAIL, "Tidak ada port /dev/ttyUSB* ditemukan.")
    return chosen


# ─── Test 2: Koneksi serial & AT dasar ───────────────────────────
def test_basic_at(ser: serial.Serial) -> bool:
    header("TEST 2: Koneksi Serial & AT Command Dasar")

    # AT - ping modul
    resp = send_at(ser, "AT")
    if "OK" in resp:
        result(OK, "AT command", "modul merespons")
    else:
        result(FAIL, "AT command tidak merespons.", f"raw: {repr(resp)}")
        print("\n  Kemungkinan penyebab:")
        print("  - Port salah (coba --port /dev/ttyUSB1 atau ttyUSB2)")
        print("  - Baudrate salah (default 115200)")
        print("  - Modul belum dinyalakan / power issue")
        return False

    # ATI - info modul
    resp = send_at(ser, "ATI")
    result(INFO, "Info modul:", resp.replace("\r\n", " | "))

    # AT+CGSN - IMEI
    resp = send_at(ser, "AT+CGSN")
    imei = re.search(r"\d{15}", resp)
    if imei:
        result(OK, "IMEI:", imei.group())
    else:
        result(WARN, "IMEI tidak terbaca", f"raw: {repr(resp)}")

    # AT+CGMR - versi firmware
    resp = send_at(ser, "AT+CGMR")
    result(INFO, "Firmware:", resp.replace("\r\n", " "))

    return True


# ─── Test 3: SIM card ────────────────────────────────────────────
def test_sim_card(ser: serial.Serial) -> bool:
    header("TEST 3: SIM Card")

    # Cek SIM terpasang
    resp = send_at(ser, "AT+CIMI")
    imsi = re.search(r"\d{10,15}", resp)
    if imsi:
        result(OK, "SIM terpasang. IMSI:", imsi.group())
    else:
        result(FAIL, "SIM tidak terdeteksi atau belum unlock.")
        print("  Pastikan SIM card terpasang dengan benar.")
        return False

    # Cek PIN
    resp = send_at(ser, "AT+CPIN?")
    if "READY" in resp:
        result(OK, "SIM PIN status: READY (tidak butuh PIN)")
    elif "SIM PIN" in resp:
        result(FAIL, "SIM masih terkunci PIN! Masukkan PIN dulu.")
        return False
    else:
        result(WARN, "Status PIN:", resp)

    # Operator
    resp = send_at(ser, "AT+COPS?", wait=3)
    op = re.search(r'\+COPS: \d+,\d+,"([^"]+)"', resp)
    if op:
        result(OK, "Operator:", op.group(1))
    else:
        result(WARN, "Operator belum terbaca (mungkin masih registrasi)", f"raw: {resp}")

    return True


# ─── Test 4: Kualitas sinyal ─────────────────────────────────────
def test_signal(ser: serial.Serial) -> bool:
    header("TEST 4: Kualitas Sinyal")

    # Registrasi jaringan
    resp = send_at(ser, "AT+CREG?")
    creg = re.search(r"\+CREG: \d+,(\d+)", resp)
    reg_status = {
        "0": "Tidak terdaftar, tidak mencari",
        "1": "Terdaftar (home network)",
        "2": "Mencari jaringan...",
        "3": "Registrasi ditolak",
        "5": "Terdaftar (roaming)",
    }
    if creg:
        stat = creg.group(1)
        desc = reg_status.get(stat, f"Status {stat}")
        icon = OK if stat in ("1", "5") else WARN if stat == "2" else FAIL
        result(icon, "Registrasi jaringan:", desc)
        if stat not in ("1", "5"):
            print("  Tunggu beberapa detik dan coba lagi.")
    else:
        result(WARN, "Tidak bisa baca status registrasi")

    # CSQ - signal strength
    resp = send_at(ser, "AT+CSQ")
    csq = re.search(r"\+CSQ: (\d+),(\d+)", resp)
    if csq:
        rssi = int(csq.group(1))
        if rssi == 99:
            result(WARN, "Sinyal: tidak diketahui (99) -- pastikan antena terpasang")
        else:
            dbm   = -113 + (rssi * 2)
            level = "Lemah" if rssi < 10 else "Sedang" if rssi < 20 else "Kuat"
            result(OK if rssi >= 10 else WARN,
                   f"Sinyal: RSSI={rssi}/31, ~{dbm}dBm", level)
    else:
        result(FAIL, "Tidak bisa baca kualitas sinyal")
        return False

    # Tipe jaringan (4G/3G/2G)
    resp = send_at(ser, "AT+CPSI?", wait=2)
    if "+CPSI:" in resp:
        parts = resp.split(":")[1].strip().split(",")
        net_type = parts[0].strip() if parts else "?"
        result(INFO, "Tipe jaringan:", net_type)

    return True


# ─── Test 5: GPS ─────────────────────────────────────────────────
def test_gps(ser: serial.Serial, timeout: int = 90) -> bool:
    header(f"TEST 5: GPS (timeout {timeout} detik)")
    print("  Pastikan antena GPS terpasang dan ada langit terbuka.")
    print("  Cold start bisa butuh 30-90 detik.\n")

    # Nyalakan GPS engine
    resp = send_at(ser, "AT+CGPS=1", wait=2)
    if "OK" in resp or "already" in resp.lower():
        result(OK, "GPS engine ON")
    else:
        result(FAIL, "GPS engine gagal dinyalakan:", repr(resp))
        return False

    # Polling AT+CGPSINFO sampai fix atau timeout
    elapsed = 0
    interval = 3
    last_raw = ""

    print(f"  Polling setiap {interval}s...")
    while elapsed < timeout:
        resp = send_at(ser, "AT+CGPSINFO", wait=1)
        last_raw = resp

        match = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", resp)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]

            if len(parts) >= 9 and parts[0] != "":
                # Ada fix - parse
                try:
                    def nmea_to_dd(nmea, direction):
                        dot = nmea.index(".")
                        deg = float(nmea[:dot - 2])
                        minutes = float(nmea[dot - 2:])
                        dd = deg + minutes / 60.0
                        if direction in ("S", "W"):
                            dd = -dd
                        return round(dd, 6)

                    lat  = nmea_to_dd(parts[0], parts[1])
                    lon  = nmea_to_dd(parts[2], parts[3])
                    alt  = float(parts[6]) if parts[6] else 0
                    spd  = round(float(parts[7]) * 1.852, 2) if parts[7] else 0
                    date = parts[4]
                    utc  = parts[5]

                    date_fmt = f"{date[:2]}/{date[2:4]}/20{date[4:]}" if len(date) == 6 else date
                    utc_fmt  = f"{utc[:2]}:{utc[2:4]}:{utc[4:]}" if len(utc) >= 6 else utc

                    print()
                    result(OK, "GPS FIX BERHASIL!")
                    print(f"\n  {'Latitude':<20}: {lat}")
                    print(f"  {'Longitude':<20}: {lon}")
                    print(f"  {'Altitude':<20}: {alt} m")
                    print(f"  {'Kecepatan':<20}: {spd} km/h")
                    print(f"  {'Tanggal (UTC)':<20}: {date_fmt}")
                    print(f"  {'Waktu (UTC)':<20}: {utc_fmt}")
                    print(f"\n  Google Maps: https://maps.google.com/?q={lat},{lon}")

                    return True
                except Exception as e:
                    result(WARN, f"Parse error: {e}")
            else:
                sys.stdout.write(f"\r  [{elapsed:3d}s/{timeout}s] Menunggu fix... (belum ada sinyal GPS)")
                sys.stdout.flush()
        else:
            sys.stdout.write(f"\r  [{elapsed:3d}s/{timeout}s] Tidak ada respons AT+CGPSINFO")
            sys.stdout.flush()

        time.sleep(interval)
        elapsed += interval + 1

    print()
    result(FAIL, f"GPS timeout setelah {timeout} detik.")
    result(INFO, "Raw terakhir:", repr(last_raw[:100]))
    print("\n  Tips:")
    print("  - Pindah ke tempat lebih terbuka (dekat jendela / outdoor)")
    print("  - Tunggu lebih lama: tambah --gps-timeout 180")
    print("  - Cek koneksi antena GPS ke modul")
    return False


# ─── Test 6: Koneksi data internet ───────────────────────────────
def test_data_connection(ser: serial.Serial, apn: str = "internet") -> bool:
    header("TEST 6: Koneksi Data Internet")

    # Cek apakah sudah dapat IP (via NetworkManager/ModemManager)
    resp = send_at(ser, "AT+CGPADDR=1", wait=2)
    ip = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', resp)
    if ip:
        result(OK, "IP address aktif:", ip.group(1))
    else:
        result(WARN, "Belum ada IP dari modem langsung")
        result(INFO, "Cek dengan: ip addr show  atau  ping 8.8.8.8")

    # Cek APN yang terkonfigurasi
    resp = send_at(ser, "AT+CGDCONT?", wait=2)
    result(INFO, "APN config:", resp.replace("\r\n", " | ").strip())

    # Set APN jika belum
    if apn not in resp:
        result(INFO, f"Setting APN ke '{apn}'...")
        send_at(ser, f'AT+CGDCONT=1,"IP","{apn}"')
        result(INFO, "APN diset. Restart modem jika perlu.")

    return True


# ─── Main ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SIM7600E Diagnostic Test")
    parser.add_argument("--port",        default=None,    help="Port serial, contoh: /dev/ttyUSB2")
    parser.add_argument("--baudrate",    default=115200,  type=int)
    parser.add_argument("--gps-timeout", default=90,      type=int, help="Timeout GPS fix (detik)")
    parser.add_argument("--apn",         default="internet")
    parser.add_argument("--skip-gps",   action="store_true", help="Skip test GPS")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  SIM7600E-H Diagnostic Test")
    print("=" * 60)

    # Test 1: Temukan port
    port = test_find_port(args.port)
    if not port:
        sys.exit(1)

    # Buka koneksi serial
    try:
        ser = serial.Serial(port, args.baudrate, timeout=2)
        result(OK, f"Serial terbuka: {port} @ {args.baudrate} baud")
    except Exception as e:
        result(FAIL, f"Gagal buka serial port: {e}")
        print(f"\n  Coba: sudo chmod 666 {port}")
        sys.exit(1)

    passed = 0
    total  = 0

    try:
        # Test 2: AT dasar
        total += 1
        if test_basic_at(ser):
            passed += 1

        # Test 3: SIM card
        total += 1
        if test_sim_card(ser):
            passed += 1

        # Test 4: Sinyal
        total += 1
        if test_signal(ser):
            passed += 1

        # Test 5: GPS
        if not args.skip_gps:
            total += 1
            if test_gps(ser, timeout=args.gps_timeout):
                passed += 1
        else:
            print(f"\n{INFO} Test GPS dilewati (--skip-gps)")

        # Test 6: Data
        total += 1
        if test_data_connection(ser, apn=args.apn):
            passed += 1

    finally:
        ser.close()

    # ─── Ringkasan ───────────────────────────────────────────────
    header(f"RINGKASAN: {passed}/{total} test lulus")
    if passed == total:
        print("  Semua test LULUS. Modul siap digunakan.\n")
    elif passed >= total - 1:
        print("  Hampir semua test lulus. Cek warning di atas.\n")
    else:
        print("  Ada test yang GAGAL. Selesaikan masalah di atas.\n")
        print("  Perintah debug tambahan:")
        print("    ls -la /dev/ttyUSB*")
        print("    dmesg | grep ttyUSB")
        print("    sudo systemctl status ModemManager")


if __name__ == "__main__":
    main()