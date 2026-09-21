"""
TEST — Send all fixtures JSON to /sensors/telemetry for verification.

Useful for:
- Confirm payload format received API/backend correctly
- See what each scenario looks like on webhook.site before the hardware is installed
- Check edge case smokeLevel without needing the original sensor

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
    parser.add_argument("--files",  default=None, help="Specific fixture file name")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    print("=" * 60)
    print("TEST — POST Fixture JSON to /sensors/telemetry")
    print("=" * 60)
    print(f"Target : {settings.telemetry_endpoint()}\n")

    if "webhook.site/xxxxxxxx" in settings.API_BASE_URL:
        print("[FAIL] EFWS_API_URL is still a placeholder in .env")
        print("Fill in the URL from https://webhook.site or run tools/mock_api_server.py")
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
    print(f"Finished:{ok_count}/{total}succeed.")
    if ok_count == total:
        print("✅ All fixtures sent — check webhook.site/mock server.")
    else:
        print("❌ Something failed — check connection and EFWS_API_URL in .env.")

if __name__ == "__main__":
    main()
