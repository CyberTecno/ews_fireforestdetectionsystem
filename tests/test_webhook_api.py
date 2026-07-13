"""
TEST — Konektivitas API ke webhook.site (atau backend production).

Kirim satu contoh payload telemetry untuk verifikasi:
  - Pi bisa reach API endpoint
  - Format JSON diterima dengan benar
  - Header Authorization benar (jika EFWS_API_KEY diisi)

Usage: python3 tests/test_webhook_api.py
"""
import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from communication.api_publisher import APIPublisher

print("=" * 60)
print("  TEST Konektivitas API")
print("=" * 60)
print(f"deviceId    : {settings.DEVICE_ID}")
print(f"deviceToken : {settings.DEVICE_TOKEN}")
print(f"endpoint    : {settings.telemetry_endpoint()}\n")

if "webhook.site/xxxxxxxx" in settings.API_BASE_URL:
    print("[FAIL] EFWS_API_URL masih placeholder di .env")
    print("Buka https://webhook.site, copy 'Your unique URL', isi ke .env")
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
    print("✅ Berhasil! Cek halaman webhook.site — payload harus muncul di sana.")
else:
    print("❌ Gagal. Cek koneksi internet Pi dan EFWS_API_URL di .env")
