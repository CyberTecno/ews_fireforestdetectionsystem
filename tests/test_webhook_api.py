"""
TEST — API connectivity to webhook.site (or production backend).

Send one example telemetry payload for verification:
- Pi can reach API endpoint
- Format JSON is received correctly
- Authorization header is correct (if EFWS_API_KEY is filled in)

Usage: python3 tests/test_webhook_api.py
"""
import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from communication.api_publisher import APIPublisher

print("=" * 60)
print("API Connectivity TEST")
print("=" * 60)
print(f"deviceId    : {settings.DEVICE_ID}")
print(f"deviceToken : {settings.DEVICE_TOKEN}")
print(f"endpoint    : {settings.telemetry_endpoint()}\n")

if "webhook.site/xxxxxxxx" in settings.API_BASE_URL:
    print("[FAIL] EFWS_API_URL is still a placeholder in .env")
    print("Open https://webhook.site, copy 'Your unique URL', fill it into .env")
    sys.exit(1)

sample = {
    "deviceId":    settings.DEVICE_ID,
    "deviceToken": settings.DEVICE_TOKEN,
    "telemetry": [{
        "timestamp":            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "waterLevel":           3.3,
        "waterLevelCurrentMa":  14.6,
        "smokeLevel":           9.8,
        "temp":                 29.5,
        "humidity":             63.0,
        "soilMoisture":         60.0,
        "batteryLevel":         85.0,
        "flameDetected":        False,
        "windSpeed":            2.5,
    }]
}

api = APIPublisher()
ok = api.send_telemetry(sample)
api.close()

if ok:
    print("✅ Success! Check the webhook.site page — the payload should appear there.")
else:
    print("❌ Failed. Check the Pi and EFWS_API_URL's internet connection in .env")
