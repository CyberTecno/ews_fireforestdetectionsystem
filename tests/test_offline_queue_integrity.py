"""
TEST — Integrity of the offline queue (queue) when the signal is lost.

Purpose: ensure payload is saved to SQLite api_queue when API is not
reachable (4G signal lost / EFWS_API_URL not reachable) DOES NOT change
bit of the original payload — both when saved and when retransmitted
(flush) after the signal returns. This is important because the sensor data is at the moment
events (e.g. critical levels) should reach the server AS IS, right
reconstructed/recalculated from changed sensor values.

Cara kerja test:
1. Set EFWS_API_URL to an address that is guaranteed to be unreachable.
2. Send one example payload via APIPublisher.send_telemetry() (should fail
and automatically enter the queue).
3. Retrieve queue items from DB, compare byte-by-byte (deep equality)
with the original payload.
4. Simulate the return signal (online=forced True) then flush_queue() and
Make sure the re-POSTed payload (via monkeypatch _post_once) is the same
exactly the same as the original payload.

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

    # 1) Simulate offline: send must fail & automatically enter queue
    ok = api.send_telemetry(SAMPLE_PAYLOAD, db=db)
    if ok:
        failures.append("send_telemetry() should fail (endpoint intentionally unreachable)")
    else:
        print("✅ send_telemetry() failed as expected (signal dropped)")

    pending = db.get_pending_queue()
    if len(pending) != 1:
        failures.append(f"The number of queue items must be 1, yes{len(pending)}")
    else:
        queued = json.loads(pending[0]["payload"])
        if queued == SAMPLE_PAYLOAD:
            print("✅ Payload in the queue is IDENTICAL to the original payload (deep equality)")
        else:
            failures.append(f"Payload in queue CHANGED from original!Original \n :{SAMPLE_PAYLOAD}\n  queue: {queued}")

    # 2) Simulate return signal → flush_queue() should resend payload
    #    EXACTLY THE SAME (not a new/recalculated payload)
    sent_payloads = []
    original_post_once = api._post_once

    def fake_post_once(endpoint, body):
        sent_payloads.append(json.loads(body))
        # _post_once now returns a 4-tuple: (delivered, status_code, response_json, transient)
        return True, 200, {"success": True}, False

    api._post_once = fake_post_once
    api.online = True  # force it to assume the signal has returned
    api.flush_queue(db)
    api._post_once = original_post_once

    if len(sent_payloads) != 1:
        failures.append(f"flush_queue() should send 1 payload, delivered{len(sent_payloads)}")
    elif sent_payloads[0] != SAMPLE_PAYLOAD:
        failures.append("The REFlushed payload is not the same as the original payload!")
    else:
        print("✅ The reflushed payload after the signal returns is IDENTICAL to the original")

    remaining = db.count_pending_queue()
    if remaining != 0:
        failures.append(f"The queue should be empty after a successful flush, remaining{remaining}")
    else:
        print("✅ Queue is empty after successful flushing")

    db.close()
    api.close()
    os.remove(tmp_db)

    print("\n" + "=" * 60)
    if failures:
        print("❌ FAILED")
        for f in failures:
            print(f"   - {f}")
        sys.exit(1)
    else:
        print("✅ All queue integrity checks PASS.")


if __name__ == "__main__":
    main()
