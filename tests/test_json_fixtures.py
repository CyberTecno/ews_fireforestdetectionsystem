"""
TEST — Kirim semua fixture JSON ke /sensors/telemetry untuk verifikasi.

Berguna untuk:
  - Konfirmasi format payload diterima API/backend dengan benar
  - Lihat tampilan tiap skenario di webhook.site sebelum hardware terpasang
  - Cek edge case smokeLevel tanpa perlu sensor asli

Usage:
  python3 tests/test_json_fixtures.py
  python3 tests/test_json_fixtures.py --file test_critical.json
  python3 tests/test_json_fixtures.py --delay 1.0
"""
import sys, os, json, time, argparse, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from communication.api_publisher import APIPublisher

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",  default=None, help="Nama file fixture spesifik")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    print("=" * 60)
    print("  TEST — POST Fixture JSON ke /sensors/telemetry")
    print("=" * 60)
    print(f"Target : {settings.telemetry_endpoint()}\n")

    if "webhook.site/xxxxxxxx" in settings.API_BASE_URL:
        print("[FAIL] EFWS_API_URL masih placeholder di .env")
        print("Isi dengan URL dari https://webhook.site atau jalankan tools/mock_api_server.py")
        sys.exit(1)

    if args.file:
        files = [os.path.join(FIXTURES_DIR, args.file)]
    else:
        files = sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json")))

    api = APIPublisher()
    total = ok_count = 0

    for filepath in files:
        filename = os.path.basename(filepath)
        with open(filepath) as f:
            data = json.load(f)

        items = data if isinstance(data, list) else [data]
        print(f"\n[{filename}] {len(items)} payload → /sensors/telemetry")

        for i, item in enumerate(items, 1):
            t     = item.get("telemetry", [{}])[0]
            sl    = t.get("smokeLevel", "?")
            wl    = t.get("waterLevel", "?")
            edge  = f"  [{t.get('_edgeCase','')}]" if "_edgeCase" in t else ""
            total += 1

            ok = api.send_telemetry(item)
            ok_count += ok
            print(f"  [{'OK  ' if ok else 'FAIL'}] #{i:02d}  smoke={sl}%  water={wl}m{edge}")
            time.sleep(args.delay)

    api.close()
    print(f"\n{'='*60}")
    print(f"Selesai: {ok_count}/{total} berhasil.")
    if ok_count == total:
        print("✅ Semua fixture terkirim — cek webhook.site/mock server.")
    else:
        print("❌ Ada yang gagal — cek koneksi dan EFWS_API_URL di .env.")

if __name__ == "__main__":
    main()
