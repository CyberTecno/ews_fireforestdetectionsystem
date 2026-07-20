"""
HTTP REST API publisher untuk EFWS — 4 endpoint, satu mesin kirim generik.

Endpoint:
  telemetry_endpoint()   /sensors/telemetry      scheduled, response bawa 'config' (remote threshold)
  location_endpoint()    /sensors/location        scheduled
  heartbeat_endpoint()   /sensors/heartbeat       scheduled, response bawa 'commands'
  command_ack_endpoint() /sensors/commands/ack    event-driven (dipicu commands dari heartbeat)

Alur generik (send()):
  POST → sukses (2xx/3xx)         → return (True, response_json)
       → gagal JARINGAN           → masuk offline queue (kalau db diberikan) → return (False, None)
         (DNS gagal, connection refused, timeout, no route ke internet, dst)
       → gagal HTTP 5xx           → masuk offline queue juga (transient, server lagi bermasalah)
       → gagal HTTP 4xx           → TIDAK di-retry, TIDAK masuk queue (server sudah menolak
                                     secara sengaja -- device token salah, payload invalid, dst)
         → return (False, None), dan endpoint TIDAK online dianggap turun

Offline queue (SQLite api_queue, lihat database/db_manager.py) FIFO per baris,
retry dilakukan lewat flush_queue() yang dipanggil dari thread terpisah
(main.py: EFWS._flush_queue_loop) tiap EFWS_CONNECTIVITY_CHECK_SEC (2 menit),
independen dari siklus baca sensor (3 menit).
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

        # Threshold remote terakhir yang diketahui (dari config/telemetry response).
        # None selama belum pernah ada response valid -- threshold_resolver akan
        # fallback penuh ke hardcoded lokal selama ini None.
        self.remote_config = None
        self._remote_config_updated_at = 0.0

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
    # Internal: satu kali POST, dengan klasifikasi error eksplisit.
    # Return: (delivered: bool, status_code: int|None, response_json: dict|None,
    #          transient: bool)
    #   transient=True  -> layak masuk offline queue / retry (jaringan atau 5xx)
    #   transient=False -> server sengaja menolak (4xx), JANGAN di-retry/queue
    # ------------------------------------------------------------------
    def _post_once(self, endpoint: str, body: str):
        try:
            resp = self.session.post(
                endpoint,
                data=body,
                timeout=settings.API_TIMEOUT_SEC,
                verify=settings.API_VERIFY_SSL,
            )
        except requests.exceptions.Timeout as e:
            logger.debug("POST timeout ke %s: %s", endpoint, e)
            self.online = False
            return False, None, None, True  # transient -> queue
        except requests.exceptions.ConnectionError as e:
            # Mencakup: DNS gagal, internet mati, connection refused, host unreachable.
            logger.debug("POST connection error ke %s: %s", endpoint, e)
            self.online = False
            return False, None, None, True  # transient -> queue
        except requests.exceptions.RequestException as e:
            # Error requests lain yang tak terduga -- perlakukan sebagai transient
            # daripada berisiko membuang data karena error yang belum kita kenali.
            logger.debug("POST error tak terklasifikasi ke %s: %s", endpoint, e)
            self.online = False
            return False, None, None, True

        # Server benar-benar merespons -> koneksi jaringan sehat.
        self.online = True

        try:
            resp_json = resp.json() if resp.content else None
        except ValueError:
            resp_json = None

        if resp.status_code < 400:
            return True, resp.status_code, resp_json, False

        if resp.status_code >= 500:
            logger.warning("API HTTP %d (server error, transient) dari %s: %s",
                           resp.status_code, endpoint, resp.text[:150])
            return False, resp.status_code, resp_json, True  # transient -> queue

        # 4xx: server SENGAJA menolak. Jangan retry, jangan queue.
        logger.warning("API HTTP %d (ditolak server, TIDAK di-retry) dari %s: %s",
                       resp.status_code, endpoint, resp.text[:200])
        return False, resp.status_code, resp_json, False

    # ------------------------------------------------------------------
    # Public: kirim generik dengan retry singkat + fallback ke offline queue.
    # ------------------------------------------------------------------
    def send(self, endpoint: str, payload: dict, db=None, label: str = "") -> tuple:
        """
        Kirim satu payload ke satu endpoint.
        Return: (delivered: bool, response_json: dict|None)

        Kalau gagal karena jaringan/5xx (transient) dan `db` diberikan,
        payload otomatis masuk offline queue (FIFO, lihat db_manager.py).
        Kalau gagal karena 4xx, TIDAK masuk queue -- itu ditolak backend,
        bukan masalah konektivitas.
        """
        body = json.dumps(payload, default=str)
        last_transient = True

        for attempt in range(1, settings.API_MAX_RETRIES + 1):
            delivered, status, resp_json, transient = self._post_once(endpoint, body)
            last_transient = transient

            if delivered:
                logger.info("✅ %s terkirim (%s)", label or endpoint.split("/")[-1], endpoint)
                return True, resp_json

            if not transient:
                # Server menolak sengaja -- berhenti, jangan retry, jangan queue.
                logger.warning("🚫 %s ditolak server (HTTP %s) -- dibuang, tidak di-queue.",
                              label or endpoint, status)
                return False, resp_json

            if attempt < settings.API_MAX_RETRIES:
                time.sleep(settings.API_RETRY_DELAY)

        # Habis retry, masih transient (jaringan/5xx) -> masuk offline queue.
        if not self.online:
            logger.warning("🔴 %s: koneksi TERPUTUS setelah %d percobaan.",
                          label or endpoint, settings.API_MAX_RETRIES)
            self._last_connectivity_check = time.time()

        if db is not None and last_transient:
            db.queue_api(endpoint, payload)
            logger.warning("📦 %s disimpan ke offline queue (FIFO).", label or endpoint)

        return False, None

    # ------------------------------------------------------------------
    # Endpoint 1: /sensors/location
    # ------------------------------------------------------------------
    def send_location(self, payload: dict, db=None) -> bool:
        delivered, _ = self.send(settings.location_endpoint(), payload, db=db, label="Location")
        return delivered

    # ------------------------------------------------------------------
    # Endpoint 2: /sensors/telemetry -- response membawa 'config' (remote threshold)
    # ------------------------------------------------------------------
    def send_telemetry(self, payload: dict, db=None) -> bool:
        delivered, resp_json = self.send(settings.telemetry_endpoint(), payload, db=db, label="Telemetry")
        self._apply_remote_config(resp_json)
        return delivered

    def _apply_remote_config(self, resp_json):
        if not isinstance(resp_json, dict):
            return
        config = resp_json.get("config")
        if isinstance(config, dict):
            if config != self.remote_config:
                logger.info("⚙️  Threshold remote diperbarui dari backend: %s", config)
            self.remote_config = config
            self._remote_config_updated_at = time.time()

    # ------------------------------------------------------------------
    # Endpoint 3: /sensors/heartbeat -- response membawa 'commands'
    # Return: (delivered: bool, commands: list)
    # ------------------------------------------------------------------
    def send_heartbeat(self, payload: dict, db=None) -> tuple:
        delivered, resp_json = self.send(settings.heartbeat_endpoint(), payload, db=db, label="Heartbeat")
        commands = []
        if delivered and isinstance(resp_json, dict):
            commands = resp_json.get("commands") or []
            if not isinstance(commands, list):
                commands = []
        return delivered, commands

    # ------------------------------------------------------------------
    # Endpoint 4: /sensors/commands/ack -- event-driven, dipanggil langsung
    # setelah eksekusi command, TIDAK lewat scheduler.
    # ------------------------------------------------------------------
    def send_command_ack(self, payload: dict, db=None) -> bool:
        delivered, _ = self.send(settings.command_ack_endpoint(), payload, db=db, label="CommandAck")
        return delivered

    # ------------------------------------------------------------------
    # Offline Queue -- generik untuk keempat endpoint sekaligus, FIFO.
    # Endpoint aktual sudah tersimpan per-item (item["endpoint"]), jadi satu
    # antrian bisa berisi campuran location/telemetry/heartbeat/ack tanpa
    # tertukar urutannya.
    # ------------------------------------------------------------------
    def flush_queue(self, db, batch_size: int = 10):
        if not self.online:
            if not self._check_connectivity():
                return 0

        pending = db.get_pending_queue(limit=batch_size)
        if not pending:
            return 0

        logger.info("📤 Flush %d item dari offline queue (FIFO)...", len(pending))
        sent = 0

        for item in pending:
            try:
                payload = json.loads(item["payload"])
            except Exception as e:
                logger.error("Queue #%d payload rusak: %s", item["id"], e)
                db.mark_queue_failed(item["id"], f"invalid json: {e}")
                continue

            endpoint = item["endpoint"]  # endpoint yang tersimpan saat item di-queue

            delivered, status, resp_json, transient = self._post_once(endpoint, json.dumps(payload, default=str))

            if delivered:
                db.mark_queue_sent(item["id"])
                sent += 1
                logger.info("✅ Queue #%d (%s) terkirim", item["id"], endpoint.split("/")[-1])

                # Kalau kebetulan ini item telemetry, sekalian sinkronkan config.
                if endpoint == settings.telemetry_endpoint():
                    self._apply_remote_config(resp_json)

            elif transient:
                # Jaringan putus lagi di tengah flush -- berhenti, PERTAHANKAN
                # urutan FIFO (jangan skip ke item berikutnya).
                self._last_connectivity_check = time.time()
                logger.warning("⏸ Flush berhenti di #%d — koneksi putus (FIFO dipertahankan).", item["id"])
                break

            else:
                # 4xx -- server menolak permanen, buang dari queue (jangan blokir FIFO selamanya).
                db.mark_queue_failed(item["id"], f"server rejected (HTTP {status})")
                logger.warning("🚫 Queue #%d ditolak server (HTTP %s) -- dibuang.", item["id"], status)

        if sent:
            logger.info("📤 Flush selesai: %d terkirim, %d pending.", sent, db.count_pending_queue())

        return sent

    def close(self):
        self.session.close()
