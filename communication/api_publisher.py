"""
HTTP REST API publisher untuk EFWS — satu endpoint, dengan offline queue.

Alur:
  send_telemetry(payload)
      ↓ berhasil → ✅
      ↓ gagal    → simpan ke SQLite api_queue
                       ↓ saat online kembali → flush_queue() kirim ulang
                         (endpoint di-resolve ulang dari env saat flush,
                          sehingga perubahan EFWS_API_URL langsung berlaku)

Endpoint tunggal: EFWS_API_URL/sensors/telemetry
"""
import json
import time
import logging
import requests
from config import settings

logger = logging.getLogger("efws.api")


class APIPublisher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": f"EFWS/{settings.DEVICE_ID}",
        })

        if settings.API_SECRET_KEY:
            self.session.headers["Authorization"] = f"Bearer {settings.API_SECRET_KEY}"

        self.online = False
        self._last_connectivity_check = 0.0
        self._connectivity_check_interval = settings.EFWS_CONNECTIVITY_CHECK_SEC

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------
    def _is_reachable(self) -> bool:
        try:
            self.session.get(
                settings.API_BASE_URL,
                timeout=5,
                verify=settings.API_VERIFY_SSL,
            )
            return True
        except requests.exceptions.RequestException:
            return False

    def _check_connectivity(self) -> bool:
        if self.online:
            return True

        now = time.time()

        if now - self._last_connectivity_check < self._connectivity_check_interval:
            return False

        self._last_connectivity_check = now

        reachable = self._is_reachable()

        if reachable and not self.online:
            logger.info("🟢 Koneksi KEMBALI — akan flush offline queue.")

        self.online = reachable
        return self.online

    # ------------------------------------------------------------------
    # Internal POST
    # ------------------------------------------------------------------
    def _post_once(self, endpoint: str, body: str) -> bool:
        try:
            resp = self.session.post(
                endpoint,
                data=body,
                timeout=settings.API_TIMEOUT_SEC,
                verify=settings.API_VERIFY_SSL,
            )

            # Server berhasil dihubungi.
            self.online = True

            if resp.status_code < 400:
                return True

            logger.warning(
                "API HTTP %d: %s",
                resp.status_code,
                resp.text[:150],
            )
            return False

        except requests.exceptions.RequestException as e:
            logger.debug("POST error: %s", e)

            # Benar-benar kehilangan koneksi.
            self.online = False
            return False

    def _post(self, endpoint: str, payload: dict) -> bool:
        body = json.dumps(payload, default=str)

        for attempt in range(1, settings.API_MAX_RETRIES + 1):

            if self._post_once(endpoint, body):

                logger.info(
                    "✅ Terkirim ke %s (ts=%s)",
                    endpoint.split("/")[-1],
                    payload.get("telemetry", [{}])[0].get("timestamp", "")[:19],
                )
                return True

            if attempt < settings.API_MAX_RETRIES:
                time.sleep(settings.API_RETRY_DELAY)

        if not self.online:
            logger.warning(
                "🔴 Koneksi TERPUTUS setelah %d attempts.",
                settings.API_MAX_RETRIES,
            )
            self._last_connectivity_check = time.time()

        return False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def send_telemetry(self, payload: dict, db=None) -> bool:
        endpoint = settings.telemetry_endpoint()

        success = self._post(endpoint, payload)

        if not success and db is not None:
            db.queue_api(endpoint, payload)
            logger.warning(
                "📦 Telemetry disimpan ke offline queue (pengiriman gagal)."
            )

        return success

    # ------------------------------------------------------------------
    # Offline Queue
    # ------------------------------------------------------------------
    def flush_queue(self, db, batch_size: int = 10):

        if not self.online:
            if not self._check_connectivity():
                return 0

        pending = db.get_pending_queue(limit=batch_size)

        if not pending:
            return 0

        logger.info("📤 Flush %d item dari offline queue...", len(pending))

        sent = 0

        for item in pending:

            try:
                payload = json.loads(item["payload"])

            except Exception as e:
                logger.error(
                    "Queue #%d payload rusak: %s",
                    item["id"],
                    e,
                )

                db.mark_queue_failed(
                    item["id"],
                    f"invalid json: {e}",
                )
                continue

            endpoint = settings.telemetry_endpoint()

            if endpoint != item["endpoint"]:
                logger.info(
                    "🔀 Queue #%d: endpoint remapped → %s",
                    item["id"],
                    endpoint,
                )

            if self._post_once(endpoint, json.dumps(payload, default=str)):

                db.mark_queue_sent(item["id"])
                sent += 1

                logger.info(
                    "✅ Queue #%d terkirim",
                    item["id"],
                )

            else:

                if not self.online:
                    db.mark_queue_failed(item["id"], "connection lost")
                    self._last_connectivity_check = time.time()

                    logger.warning(
                        "⏸ Flush berhenti di #%d — koneksi putus.",
                        item["id"],
                    )
                    break

                # HTTP error (429,500,dll)
                db.mark_queue_failed(
                    item["id"],
                    "server rejected request",
                )

                logger.warning(
                    "⏸ Queue #%d ditolak server.",
                    item["id"],
                )

        if sent:
            logger.info(
                "📤 Flush selesai: %d terkirim, %d pending.",
                sent,
                db.count_pending_queue(),
            )

        return sent

    def close(self):
        self.session.close()