"""
HTTP REST API publisher for EFWS — 4 endpoints, one generic send machine.

Endpoint:
  telemetry_endpoint()   /sensors/telemetry      scheduled, response bawa 'config' (remote threshold)
  location_endpoint()    /sensors/location        scheduled
  heartbeat_endpoint()   /sensors/heartbeat       scheduled, response bawa 'commands'
command_ack_endpoint() /sensors/commands/ack event-driven (triggered by commands from heartbeat)

Alur generik (send()):
POST → success (2xx/3xx) → return (True, response_json)
→ failed NETWORK → entered offline queue (if db was given) → return (False, None)
(DNS failed, connection refused, timeout, no route to internet, etc.)
→ failed HTTP 5xx → entered offline queue too (transient, server is having problems)
→ failed HTTP 4xx → NOT was retried, NOT entered queue (server has rejected
intentionally -- wrong device token, invalid payload, etc.)
→ return (False, None), and the online endpoint NOT is considered down

Offline queue (SQLite api_queue, see database/db_manager.py) FIFO per row,
retry is done via flush_queue() which is called from a separate thread
(main.py: EFWS._flush_queue_loop) every EFWS_CONNECTIVITY_CHECK_SEC (2 minutes),
independent of the sensor read cycle (3 minutes).
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

        # Last known remote threshold (from config/telemetry response).
        # None as long as there has never been a valid response -- threshold_resolver will
        # full fallback to hardcoded locale as long as it is None.
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
            logger.info("🟢 Connection BACK — will flush offline queue.")

        self.online = reachable
        return self.online

    # ------------------------------------------------------------------
    # Internal: one time POST, with explicit error classification.
    # Return: (delivered: bool, status_code: int|None, response_json: dict|None,
    #          transient: bool)
    #   transient=True -> eligible to enter offline queue / retry (network or 5xx)
    #   transient=False -> server intentionally rejected (4xx), DO NOT retried/queue
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
            logger.debug("POST timeout to %s: %s", endpoint, e)
            self.online = False
            return False, None, None, True  # transient -> queue
        except requests.exceptions.ConnectionError as e:
            # Includes: DNS failed, internet down, connection refused, host unreachable.
            logger.debug("POST connection error to %s: %s", endpoint, e)
            self.online = False
            return False, None, None, True  # transient -> queue
        except requests.exceptions.RequestException as e:
            # Other unexpected requests errors -- treat them as transient
            # rather than risk throwing away data due to errors we don't yet recognize.
            logger.debug("POST unclassified error to %s: %s", endpoint, e)
            self.online = False
            return False, None, None, True

        # Server is actually responding -> network connection is healthy.
        self.online = True

        try:
            resp_json = resp.json() if resp.content else None
        except ValueError:
            resp_json = None

        if resp.status_code < 400:
            return True, resp.status_code, resp_json, False

        if resp.status_code >= 500:
            logger.warning("API HTTP %d (server error, transient) from %s: %s",
                           resp.status_code, endpoint, resp.text[:150])
            return False, resp.status_code, resp_json, True  # transient -> queue

        # 4xx: server ACCIDENTALLY refused. Don't retry, don't queue.
        logger.warning("API HTTP %d (server rejected, NOT retrieved) from %s: %s",
                       resp.status_code, endpoint, resp.text[:200])
        return False, resp.status_code, resp_json, False

    # ------------------------------------------------------------------
    # Public: send generic with short retry + fallback to offline queue.
    # ------------------------------------------------------------------
    def send(self, endpoint: str, payload: dict, db=None, label: str = "") -> tuple:
        """
Send one payload to one endpoint.
        Return: (delivered: bool, response_json: dict|None)

If it fails because the network/5xx (transient) and `db` are given,
payload automatically enters the offline queue (FIFO, see db_manager.py).
If it fails due to 4xx, DOES NOT go into queue -- it's rejected by the backend,
not a connectivity issue.
        """
        body = json.dumps(payload, default=str)
        last_transient = True

        logger.info("📤 SEND %s → %s | body=%s", label or endpoint.split("/")[-1], endpoint, body)

        for attempt in range(1, settings.API_MAX_RETRIES + 1):
            delivered, status, resp_json, transient = self._post_once(endpoint, body)
            last_transient = transient

            if delivered:
                logger.info("✅ %s sent (HTTP %s) → %s", label or endpoint.split("/")[-1], status, endpoint)
                return True, resp_json

            if not transient:
                # The server refused on purpose -- stop, don't retry, don't queue.
                logger.warning("🚫 %s server rejected (HTTP %s) -- discarded, not queued.",
                              label or endpoint, status)
                return False, resp_json

            if attempt < settings.API_MAX_RETRIES:
                time.sleep(settings.API_RETRY_DELAY)

        # After retry, still transient (network/5xx) -> enter offline queue.
        if not self.online:
            logger.warning("🔴 %s: connection LOST after %d attempts.",
                          label or endpoint, settings.API_MAX_RETRIES)
            self._last_connectivity_check = time.time()

        if db is not None and last_transient:
            db.queue_api(endpoint, payload)
            logger.warning("📦 %s is saved to offline queue (FIFO).", label or endpoint)

        return False, None

    # ------------------------------------------------------------------
    # Endpoint 1: /sensors/location
    # ------------------------------------------------------------------
    def send_location(self, payload: dict, db=None) -> bool:
        delivered, _ = self.send(settings.location_endpoint(), payload, db=db, label="Location")
        return delivered

    # ------------------------------------------------------------------
    # Endpoint 2: /sensors/telemetry -- response carries 'config' (remote thresholds)
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
                logger.info("⚙️ Remote threshold updated from backend: %s", config)
            self.remote_config = config
            self._remote_config_updated_at = time.time()

    # ------------------------------------------------------------------
    # Endpoint 3: /sensors/heartbeat -- response carries 'commands'
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
    # Endpoint 4: /sensors/commands/ack -- event-driven, called directly
    # after executing the command, DOES NOT go through the scheduler.
    # ------------------------------------------------------------------
    def send_command_ack(self, payload: dict, db=None) -> bool:
        delivered, _ = self.send(settings.command_ack_endpoint(), payload, db=db, label="CommandAck")
        return delivered

    # ------------------------------------------------------------------
    # Offline Queue -- generic for all four endpoints at once, FIFO.
    # The actual endpoints are stored per-item (item["endpoint"]), so one
    # queue can contain a mix of locations/telemetry/heartbeat/ack without
    # order is reversed.
    # ------------------------------------------------------------------
    def flush_queue(self, db, batch_size: int = 10):
        if not self.online:
            if not self._check_connectivity():
                return 0

        pending = db.get_pending_queue(limit=batch_size)
        if not pending:
            return 0

        logger.info("📤 Flush %d items from offline queue (FIFO)...", len(pending))
        sent = 0

        for item in pending:
            try:
                payload = json.loads(item["payload"])
            except Exception as e:
                logger.error("Queue #%d corrupted payload: %s", item["id"], e)
                db.mark_queue_failed(item["id"], f"invalid json: {e}")
                continue

            endpoint = item["endpoint"]  # the endpoint that is stored when the item is queued
            body = json.dumps(payload, default=str)
            logger.info("📤 SEND (from offline queue #%d) → %s | body=%s", item["id"], endpoint, body)

            delivered, status, resp_json, transient = self._post_once(endpoint, body)

            if delivered:
                db.mark_queue_sent(item["id"])
                sent += 1
                logger.info("✅ Queue #%d (%s) sent", item["id"], endpoint.split("/")[-1])

                # If by chance this is a telemetry item, synchronize the config.
                if endpoint == settings.telemetry_endpoint():
                    self._apply_remote_config(resp_json)

            elif transient:
                # The network dropped again in the middle of the flush -- stop and PRESERVE
                # sequence FIFO (do not skip to the next item).
                self._last_connectivity_check = time.time()
                logger.warning("⏸ Flush stops at #%d — connection dropped (FIFO maintained).", item["id"])
                break

            else:
                # 4xx -- server permanently rejected, remove from queue (do not block FIFO forever).
                db.mark_queue_failed(item["id"], f"server rejected (HTTP {status})")
                logger.warning("🚫 Queue #%d rejected by server (HTTP %s) -- discarded.", item["id"], status)

        if sent:
            logger.info("📤 Flush completed: %d sent, %d pending.", sent, db.count_pending_queue())

        return sent

    def close(self):
        self.session.close()
