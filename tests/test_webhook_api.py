"""
TEST 9 — Prototyping ke API (webhook.site)

Mengirim contoh payload JSON sensor + alarm ke EFWS_API_URL yang ada di
.env. Untuk prototyping cepat, isi EFWS_API_URL dengan URL unik dari
https://webhook.site (buka webhook.site, copy "Your unique URL", paste
ke .env) - setiap request yang dikirim akan langsung muncul live di
halaman webhook.site tersebut, tanpa perlu setup backend apapun dulu.

Usage: python3 tests/test_webhook_api.py
"""
import sys
import json
import os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from communication.api_publisher import APIPublisher

print("=" * 60)
print("  TEST Prototyping API (webhook.site / backend)")
print("=" * 60)
print(f"Target EFWS_API_URL : {settings.API_BASE_URL}")
print(f"  -> data endpoint  : {settings.API_DATA_ENDPOINT}")
print(f"  -> alarm endpoint : {settings.API_ALARM_ENDPOINT}\n")

if "webhook.site/xxxxxxxx" in settings.API_BASE_URL:
    print("[FAIL] EFWS_API_URL masih nilai placeholder dari .env.example!")
    print("Buka https://webhook.site, copy 'Your unique URL', lalu:")
    print("  EFWS_API_URL=https://webhook.site/<url-unik-anda>  (di file .env)")
    sys.exit(1)

api = APIPublisher()

sample_data = {
    "device_id": settings.DEVICE_ID,
    "location": {"lat": settings.DEVICE_LOCATION["lat"], "lon": settings.DEVICE_LOCATION["lon"],
                 "source": "test", "fix": False},
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "mode": "test",
    "sensors": {
        "mq2": {"voltage": 0.55, "ppm": 95.0},
        "mq135": {"voltage": 0.42, "ppm": 130.0},
        "flame": {"raw": 1, "flame_detected": False},
        "bme280": {"temperature_c": 29.5, "humidity_percent": 62.0, "pressure_hpa": 1012.5},
        "soil": {"raw": 650, "moisture_percent": 55.0},
        "wind": {"speed_ms": 2.1},
    },
    "statuses": {"mq2": "normal", "mq135": "normal", "flame": "normal",
                 "temperature": "normal", "humidity_low": "normal",
                 "soil_dry": "normal", "wind": "normal"},
    "alarm": {"active": False, "level": "none", "triggered_by": []},
}

sample_alarm = json.loads(json.dumps(sample_data))  # deep copy
sample_alarm["alarm"] = {"active": True, "level": "critical", "triggered_by": ["flame", "mq2"]}
sample_alarm["sensors"]["flame"]["flame_detected"] = True

print("1) Mengirim contoh DATA SENSOR ke API...")
ok1 = api.send_data(sample_data)
print("   -> BERHASIL terkirim.\n" if ok1 else "   -> GAGAL terkirim (cek pesan error di atas).\n")

print("2) Mengirim contoh ALARM CRITICAL ke API...")
ok2 = api.send_alarm(sample_alarm)
print("   -> BERHASIL terkirim.\n" if ok2 else "   -> GAGAL terkirim (cek pesan error di atas).\n")

api.close()

if ok1 and ok2:
    print("[SELESAI] Buka halaman webhook.site Anda - 2 request POST JSON harus muncul di sana,")
    print("satu ke /data dan satu lagi ke /alarm.")
else:
    print("[GAGAL SEBAGIAN] Cek koneksi internet Raspberry Pi (ping 8.8.8.8) dan EFWS_API_URL di .env.")
