"""
TEST — Integritas antrian offline (queue) saat sinyal terputus.

Tujuan: memastikan payload yang disimpan ke SQLite api_queue saat API tidak
terjangkau (sinyal 4G hilang / EFWS_API_URL tidak reachable) TIDAK berubah
sedikit pun dari payload asli — baik saat disimpan maupun saat dikirim ulang
(flush) setelah sinyal kembali. Ini penting karena data sensor pada saat
kejadian (mis. level kritis) harus sampai ke server APA ADANYA, bukan
direkonstruksi/dihitung ulang dari nilai sensor yang sudah berubah.

Cara kerja test:
  1. Set EFWS_API_URL ke alamat yang dijamin tidak terjangkau.
  2. Kirim satu payload contoh lewat APIPublisher.send_telemetry() (harus gagal
     dan otomatis masuk antrian).
  3. Ambil kembali item antrian dari DB, bandingkan byte-demi-byte (deep equality)
     dengan payload asli.
  4. Simulasikan sinyal kembali (online=True paksa) lalu flush_queue() dan
     pastikan payload yang di-POST ulang (lewat monkeypatch _post_once) sama
     persis dengan payload asli.

Usage: python3 tests/test_offline_queue_integrity.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("EFWS_API_URL", "http://127.0.0.1:1/unreachable-for-test")

from database.db_manager import DBManager
from communication.api_publisher import APIPublisher

SAMPLE_PAYLOAD = {
    "deviceId":    "DEV-TEST-QUEUE",
    "deviceToken": "test",
    "telemetry": [{
        "timestamp":            "2026-07-07T00:00:00.000Z",
        "waterLevel":           2.1,
        "waterLevelCurrentMa":  12.4,
        "smokeLevel":           43.2,
        "temp":                 42.5,
        "humidity":             67.1,
        "soilMoisture":         12.7,
        "batteryLevel":         85.0,
        "flameDetected":        False,
        "windSpeed":            3.4,
    }]
}


def main():
    print("=" * 60)
    print("  TEST — Integritas Offline Queue")
    print("=" * 60)

    tmp_db = os.path.join(tempfile.gettempdir(), "efws_queue_integrity_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)

    db  = DBManager(db_path=tmp_db)
    api = APIPublisher()

    failures = []

    # 1) Simulasikan offline: kirim harus gagal & otomatis masuk queue
    ok = api.send_telemetry(SAMPLE_PAYLOAD, db=db)
    if ok:
        failures.append("send_telemetry() harusnya gagal (endpoint sengaja unreachable)")
    else:
        print("  ✅ send_telemetry() gagal seperti diharapkan (sinyal terputus)")

    pending = db.get_pending_queue()
    if len(pending) != 1:
        failures.append(f"Jumlah item queue harus 1, dapat {len(pending)}")
    else:
        queued = json.loads(pending[0]["payload"])
        if queued == SAMPLE_PAYLOAD:
            print("  ✅ Payload di queue IDENTIK dengan payload asli (deep equality)")
        else:
            failures.append(f"Payload di queue BERUBAH dari aslinya!\n  asli : {SAMPLE_PAYLOAD}\n  queue: {queued}")

    # 2) Simulasikan sinyal kembali → flush_queue() harus kirim ulang payload
    #    yang SAMA PERSIS (bukan payload baru/dihitung ulang)
    sent_payloads = []
    original_post_once = api._post_once

    def fake_post_once(endpoint, body):
        sent_payloads.append(json.loads(body))
        return True  # simulasikan sukses terkirim

    api._post_once = fake_post_once
    api.online = True  # paksa anggap sinyal sudah kembali
    api.flush_queue(db)
    api._post_once = original_post_once

    if len(sent_payloads) != 1:
        failures.append(f"flush_queue() harus mengirim 1 payload, terkirim {len(sent_payloads)}")
    elif sent_payloads[0] != SAMPLE_PAYLOAD:
        failures.append("Payload yang di-flush ULANG tidak sama dengan payload asli!")
    else:
        print("  ✅ Payload yang di-flush ulang setelah sinyal kembali IDENTIK dengan aslinya")

    remaining = db.count_pending_queue()
    if remaining != 0:
        failures.append(f"Queue harus kosong setelah flush sukses, sisa {remaining}")
    else:
        print("  ✅ Queue kosong setelah berhasil di-flush")

    db.close()
    api.close()
    os.remove(tmp_db)

    print("\n" + "=" * 60)
    if failures:
        print("  ❌ GAGAL")
        for f in failures:
            print(f"   - {f}")
        sys.exit(1)
    else:
        print("  ✅ Semua pengecekan integritas queue LULUS.")


if __name__ == "__main__":
    main()
