"""
CHECK — GPS / GNSS (verifikasi data GPS BENAR-BENAR datang dari modul fisik
A7670E/SIM7670E atau SIM7600, bukan cache/fallback config lama)

Kenapa perlu script ini:
  main.py hanya memakai GPS secara pasif (poll tiap siklus). Script ini
  secara eksplisit:
    1. Deteksi modul yang terpasang (A7670E atau SIM7600) beserta port-nya.
    2. Cek modul benar-benar merespons AT command (bukan port mati/nyasar).
    3. Nyalakan GNSS & polling AT+CGPSINFO sampai dapat fix atau timeout.
    4. Tampilkan RAW NMEA response dari modul (+CGPSINFO: ...) sebagai bukti
       data itu benar-benar baru dibaca sekarang dari GNSS engine, bukan
       nilai lama/hasil hardcode.
    5. Cetak ringkasan PASS/FAIL, dan SEKALIGUS tulis hasilnya ke efws.log
       (logger yang sama dipakai main.py) supaya ada jejak permanen.

PENTING (kenapa file ini TIDAK bernama tests/test_gps.py):
  Ditaruh di tests/hardware_checks/ dengan prefix "check_" (bukan "test_")
  supaya TIDAK ikut ter-collect oleh pytest -- script ini mengakses hardware
  serial sungguhan (buka port /dev/ttyUSBx) yang akan crash/hang kalau
  pytest mencoba meng-import-nya di lingkungan tanpa modem (CI, laptop dev,
  dst). Jalankan manual, bukan lewat pytest.

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

# ─── Logger: pakai handler yang SAMA dengan main.py (console + efws.log) ────
# Supaya hasil check ini juga permanen tercatat di file log yang sama,
# bukan cuma tampil di layar lalu hilang.
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
    parser = argparse.ArgumentParser(description="Cek apakah GPS benar-benar mengambil data dari A7670E/SIM7600")
    parser.add_argument("--timeout", type=int, default=settings._int("EFWS_GPS_TIMEOUT", 90),
                         help="Detik menunggu GNSS fix (default: EFWS_GPS_TIMEOUT / 90s)")
    parser.add_argument("--force", action="store_true", help="Abaikan .sim_cache, scan ulang semua port")
    parser.add_argument("--port", default=None, help="Paksa port tertentu (skip auto-scan), butuh --module")
    parser.add_argument("--module", choices=["a7670e", "sim7600"], default=None,
                         help="Paksa modul tertentu (dipakai bersama --port)")
    args = parser.parse_args()

    header("CHECK GPS — Deteksi modul & ambil fix nyata")

    if settings.RUN_MODE == "mock":
        result(WARN, "RUN_MODE=mock", "GPS akan disimulasikan (MockSimInterface), BUKAN data hardware asli")
        print("  Set EFWS_RUN_MODE=hardware di .env untuk tes modul fisik sungguhan.")

    # ── 1) Deteksi / pilih modul ──────────────────────────────────
    from communication.sim_detector import detect_sim, SimInterface, scan_ports

    try:
        if args.port and args.module:
            header(f"Paksa modul: {args.module.upper()} @ {args.port}")
            sim = SimInterface(port=args.port, module=args.module)
        else:
            header("Auto-detect modul SIM (A7670E vs SIM7600)")
            sim = detect_sim(force_scan=args.force)
    except Exception as e:
        result(FAIL, "Deteksi modul", str(e))
        logger.error("GPS CHECK GAGAL total -- tidak ada modul SIM terdeteksi: %s", e)
        sys.exit(1)

    is_mock = getattr(sim, "module", "") == "mock"
    result(OK if not is_mock else WARN, "Modul terdeteksi", f"{sim.module.upper()} @ {sim.port}")

    # ── 2) Modul benar-benar merespons AT (bukan port mati) ────────
    header("Cek modul merespons AT command")
    try:
        alive = sim.check_module()
        result(OK if alive else FAIL, "AT ping", "OK" if alive else "TIDAK merespons")
        if not alive and not is_mock:
            logger.error("GPS CHECK: modul %s @ %s TIDAK merespons AT command.", sim.module.upper(), sim.port)
    except Exception as e:
        result(FAIL, "AT ping", str(e))

    try:
        csq = sim.signal_quality().strip()
        result(INFO, "Kualitas sinyal (AT+CSQ)", csq.replace("\r\n", " | "))
    except Exception as e:
        result(WARN, "Kualitas sinyal", f"gagal baca: {e}")

    # ── 3) Ambil GPS fix NYATA (polling AT+CGPSINFO) ──────────────
    header(f"Minta GPS fix (timeout {args.timeout}s) -- ini akan menunggu, pastikan antena GNSS di luar/langit terbuka")
    logger.info("GPS CHECK: mulai polling fix dari %s @ %s (timeout=%ds)",
                sim.module.upper(), sim.port, args.timeout)

    gps_result = sim.get_gps(timeout=args.timeout)

    if gps_result.get("fix"):
        result(OK, "GPS FIX diterima", f"lat={gps_result['lat']:.6f}, lon={gps_result['lon']:.6f}")
        result(INFO, "Altitude", f"{gps_result.get('altitude_m')} m")
        result(INFO, "Waktu fix (UTC)", f"{gps_result.get('date_utc')} {gps_result.get('time_utc')}")

        # Bukti langsung bahwa ini data LIVE dari modul, bukan nilai lama:
        # tampilkan raw NMEA response persis seperti yang dikirim modul.
        raw_nmea = gps_result.get("raw")
        if raw_nmea:
            result(INFO, "RAW +CGPSINFO dari modul", raw_nmea)
        if gps_result.get("_mock"):
            result(WARN, "PERHATIAN", "Ini data MOCK (RUN_MODE=mock) -- BUKAN dari hardware GPS sungguhan.")

        logger.info(
            "GPS CHECK SUKSES: fix nyata dari %s @ %s -> lat=%.6f lon=%.6f alt=%sm waktu=%s %s | raw=%s",
            sim.module.upper(), sim.port,
            gps_result["lat"], gps_result["lon"],
            gps_result.get("altitude_m"), gps_result.get("date_utc"), gps_result.get("time_utc"),
            raw_nmea,
        )
        exit_code = 0
    else:
        reason = gps_result.get("reason", "tidak diketahui")
        result(FAIL, "GPS TIDAK fix", reason)
        logger.warning(
            "GPS CHECK GAGAL fix: modul %s @ %s tidak mendapat fix dalam %ds. Alasan: %s",
            sim.module.upper(), sim.port, args.timeout, reason,
        )
        print("\n  Kemungkinan penyebab:")
        print("   - Antena GNSS belum terpasang / kabelnya lepas")
        print("   - Modul di dalam ruangan / langit tertutup (GNSS butuh line-of-sight ke satelit)")
        print("   - Cold start pertama kali bisa butuh 30-60+ detik, coba --timeout lebih besar")
        exit_code = 1

    sim.close()

    header("Ringkasan")
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
