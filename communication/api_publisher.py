"""
HTTP REST API publisher untuk EFWS — dengan offline queue yang robust.

Alur kerja:
  ┌─────────────┐   berhasil    ┌──────────────┐
  │  send_data  │ ─────────────▶│  Server API  │
  └─────────────┘               └──────────────┘
         │ gagal (no sinyal)
         ▼
  ┌─────────────┐   simpan      ┌──────────────┐
  │ api_queue   │ ◀─────────────│   SQLite DB  │
  │  (SQLite)   │               └──────────────┘
  └─────────────┘
         │ sinyal kembali → flush_queue() kirim ulang SEMUA pending
         ▼
  ┌─────────────┐   kirim ulang ┌──────────────┐
  │  Server API │ ◀─────────────│  flush loop  │
  └─────────────┘               └──────────────┘

Requires: pip install requests
"""
import json
import time
import logging
import requests
from config import settings

logger = logging.getLogger("efws.api")


class APIPublisher:
    """
    Kirim data sensor & alarm ke REST API endpoint.
    Jika tidak ada sinyal: simpan ke SQLite queue.
    Jika sinyal kembali: kirim ulang semua data yang belum terkirim secara berurutan.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": f"EFWS/{settings.DEVICE_ID}",
        })
        if settings.API_SECRET_KEY:
            self.session.headers["Authorization"] = f"Bearer {settings.API_SECRET_KEY}"

        # State koneksi: True = online, False = offline (tidak ada sinyal)
        self.online = False
        self._last_connectivity_check = 0.0
        self._connectivity_check_interval = 30   # cek koneksi tiap 30 detik saat offline

    # ─── Connectivity probe ──────────────────────────────────────
    def _is_reachable(self) -> bool:
        """
        Cek apakah endpoint API bisa dijangkau (lightweight HEAD/GET).
        Tidak mengirim data, hanya probe koneksi.
        """
        probe_url = settings.API_BASE_URL
        try:
            resp = self.session.get(
                probe_url,
                timeout=5,
                verify=settings.API_VERIFY_SSL,
            )
            # Status apapun yang dapat direspons = koneksi ada
            return True
        except requests.exceptions.RequestException:
            return False

    def _check_connectivity(self) -> bool:
        """
        Update self.online. Dipanggil berkala saat offline
        agar tidak probe setiap detik (hemat bandwidth & baterai).
        """
        now = time.time()
        if self.online:
            # Saat online: tidak perlu probe proaktif,
            # kegagalan send_data/send_alarm yang akan mengubah state ke offline
            return True

        # Saat offline: probe berkala
        if now - self._last_connectivity_check < self._connectivity_check_interval:
            return False   # masih dalam interval, anggap masih offline

        self._last_connectivity_check = now
        reachable = self._is_reachable()
        if reachable and not self.online:
            logger.info("🟢 Koneksi KEMBALI — akan flush offline queue.")
        elif not reachable and self.online:
            logger.warning("🔴 Koneksi TERPUTUS — data akan disimpan lokal.")
        self.online = reachable
        return self.online

    # ─── Internal POST (satu request, tanpa retry loop) ──────────
    def _post_once(self, endpoint: str, body: str) -> bool:
        """Kirim satu POST. Return True jika berhasil."""
        try:
            resp = self.session.post(
                endpoint,
                data=body,
                timeout=settings.API_TIMEOUT_SEC,
                verify=settings.API_VERIFY_SSL,
            )
            if resp.status_code < 400:
                return True
            else:
                logger.warning("API HTTP %d: %s", resp.status_code, resp.text[:150])
                return False
        except requests.exceptions.RequestException as e:
            logger.debug("POST error: %s", e)
            return False

    # ─── Internal POST dengan retry terbatas ─────────────────────
    def _post(self, endpoint: str, payload: dict) -> bool:
        """
        Kirim payload ke endpoint.
        - Berhasil  → return True, set online=True
        - Gagal     → coba retry API_MAX_RETRIES kali
        - Masih gagal → return False, set online=False
        """
        body = json.dumps(payload, default=str)
        for attempt in range(1, settings.API_MAX_RETRIES + 1):
            ok = self._post_once(endpoint, body)
            if ok:
                if not self.online:
                    logger.info("🟢 Koneksi OK (setelah %d attempt).", attempt)
                self.online = True
                logger.info("✅ API sent | %s | ts=%s",
                            endpoint.split("/")[-1], payload.get("timestamp", "")[:19])
                return True

            if attempt < settings.API_MAX_RETRIES:
                time.sleep(settings.API_RETRY_DELAY)

        # Semua attempt gagal
        if self.online:
            logger.warning("🔴 Koneksi TERPUTUS setelah %d attempts.", settings.API_MAX_RETRIES)
        self.online = False
        self._last_connectivity_check = time.time()
        return False

    # ─── Public send methods ──────────────────────────────────────
    def send_data(self, payload: dict, db=None) -> bool:
        """
        Kirim data sensor berkala.
        Jika gagal DAN db diberikan → otomatis masuk offline queue.
        """
        success = self._post(settings.API_DATA_ENDPOINT, payload)
        if not success and db is not None:
            db.queue_api(settings.API_DATA_ENDPOINT, payload)
            logger.warning("📦 Data disimpan ke offline queue (sinyal tidak ada).")
        return success

    def send_alarm(self, payload: dict, db=None) -> bool:
        """
        Kirim alarm event.
        Alarm diprioritaskan: jika gagal → masuk queue dengan flag priority.
        """
        success = self._post(settings.API_ALARM_ENDPOINT, payload)
        if not success and db is not None:
            db.queue_api(settings.API_ALARM_ENDPOINT, payload, priority=True)
            logger.warning("📦 ALARM disimpan ke offline queue (sinyal tidak ada).")
        return success

    # ─── Offline queue flush ──────────────────────────────────────
    def flush_queue(self, db, batch_size: int = 10) -> int:
        """
        Kirim ulang semua payload yang tersimpan di api_queue (belum terkirim).

        Dipanggil:
          1. Tiap interval publish (saat online — cepat habiskan queue lama)
          2. Saat probe deteksi koneksi kembali (saat baru online lagi)

        Return: jumlah item yang berhasil dikirim di batch ini.
        """
        # Cek konektivitas dulu jika sedang offline
        if not self.online:
            if not self._check_connectivity():
                return 0   # masih offline, tidak perlu coba

        pending = db.get_pending_queue(limit=batch_size)
        if not pending:
            return 0

        logger.info("📤 Memulai flush %d item dari offline queue...", len(pending))
        sent_count = 0

        for item in pending:
            # Parse payload
            try:
                payload = json.loads(item["payload"])
            except Exception as e:
                logger.error("Queue item #%d payload rusak, skip: %s", item["id"], e)
                db.mark_queue_failed(item["id"], f"invalid json: {e}")
                continue

            # Kirim (tanpa retry loop panjang — kalau gagal, stop flush untuk sesi ini)
            body = json.dumps(payload, default=str)
            ok = self._post_once(item["endpoint"], body)

            if ok:
                db.mark_queue_sent(item["id"])
                sent_count += 1
                logger.info("  ✅ Queue #%d terkirim (ts=%s)",
                            item["id"], payload.get("timestamp", "")[:19])
            else:
                # Koneksi putus lagi di tengah flush — stop, coba lagi nanti
                db.mark_queue_failed(item["id"], "flush interrupted — no signal")
                self.online = False
                self._last_connectivity_check = time.time()
                logger.warning("  ⏸  Flush berhenti di item #%d — koneksi putus lagi.", item["id"])
                break

        if sent_count:
            remaining = db.count_pending_queue()
            logger.info("📤 Flush selesai: %d terkirim, %d masih pending.", sent_count, remaining)

        return sent_count

    def close(self):
        self.session.close()
