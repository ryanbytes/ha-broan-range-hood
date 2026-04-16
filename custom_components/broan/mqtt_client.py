"""
AWS IoT MQTT client over WebSocket with SigV4 signing.

Uses paho-mqtt with a pre-signed WSS URL. Runs in a background thread
and bridges state updates back into the HA asyncio event loop.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import http.client
import json
import logging
import ssl
import threading
import urllib.parse
from collections.abc import Callable
from typing import Any

from .const import IOT_ENDPOINT, AWS_REGION

# Lazy import — paho-mqtt is bundled with HA; we handle both v1 and v2 APIs.
try:
    import paho.mqtt.client as mqtt
    # paho-mqtt 2.0 requires explicit CallbackAPIVersion
    _PAHO_V2 = hasattr(mqtt, "CallbackAPIVersion")
except ImportError as exc:  # pragma: no cover
    raise ImportError("paho-mqtt is required. Install it via pip.") from exc

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SigV4 WebSocket URL signing
# ---------------------------------------------------------------------------

def _uri_encode(value: str) -> str:
    return urllib.parse.quote(str(value), safe="-_.~")


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


def build_iot_wss_url(
    access_key_id: str,
    secret_access_key: str,
    session_token: str,
    region: str = AWS_REGION,
    endpoint: str = IOT_ENDPOINT,
) -> str:
    """Return a pre-signed WSS URL for the AWS IoT MQTT endpoint."""
    service = "iotdevicegateway"
    algorithm = "AWS4-HMAC-SHA256"

    now = datetime.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"

    # Build query params (sorted alphabetically per SigV4 spec).
    # IMPORTANT: X-Amz-Security-Token is intentionally excluded from the
    # signed params — the aws-iot-device-sdk appends it after the signature
    # and AWS IoT verifies the signature without it. Including it causes a
    # signature mismatch and a 403.
    params: dict[str, str] = {
        "X-Amz-Algorithm": algorithm,
        "X-Amz-Credential": f"{access_key_id}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-SignedHeaders": "host",
    }
    canonical_qs = "&".join(
        f"{_uri_encode(k)}={_uri_encode(v)}" for k, v in sorted(params.items())
    )

    canonical_request = "\n".join([
        "GET",
        "/mqtt",
        canonical_qs,
        f"host:{endpoint}\n",
        "host",
        hashlib.sha256(b"").hexdigest(),
    ])

    string_to_sign = "\n".join([
        algorithm,
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    sig_key = _signing_key(secret_access_key, date_stamp, region, service)
    signature = hmac.new(sig_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # Append security token unsigned, after the signature — matches sdk behaviour
    url = f"wss://{endpoint}/mqtt?{canonical_qs}&X-Amz-Signature={signature}"
    if session_token:
        url += f"&X-Amz-Security-Token={_uri_encode(session_token)}"
    return url


# ---------------------------------------------------------------------------
# MQTT shadow topic helpers
# ---------------------------------------------------------------------------

def _shadow_get(thing_name: str) -> str:
    return f"$aws/things/{thing_name}/shadow/get"

def _shadow_get_accepted(thing_name: str) -> str:
    return f"$aws/things/{thing_name}/shadow/get/accepted"

def _shadow_update(thing_name: str) -> str:
    return f"$aws/things/{thing_name}/shadow/update"

def _shadow_update_accepted(thing_name: str) -> str:
    return f"$aws/things/{thing_name}/shadow/update/accepted"

def _shadow_delete_accepted(thing_name: str) -> str:
    return f"$aws/things/{thing_name}/shadow/delete/accepted"


# ---------------------------------------------------------------------------
# BroanMqttClient
# ---------------------------------------------------------------------------

class BroanMqttClient:
    """
    Manages a paho-mqtt WebSocket connection to AWS IoT for one device.

    Callbacks fire on the paho thread; we forward them into the HA event
    loop via asyncio.run_coroutine_threadsafe.
    """

    def __init__(
        self,
        thing_name: str,
        loop: asyncio.AbstractEventLoop,
        on_state_update: Callable[[dict], None],
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        self._thing_name = thing_name
        self._loop = loop
        self._on_state_update = on_state_update
        self._on_disconnect = on_disconnect

        self._client: mqtt.Client | None = None
        self._connected = False
        self._lock = threading.Lock()
        self._suppress_disconnect_cb = False
        self._connect_event = threading.Event()
        self._connect_rc: int | None = None

    # ------------------------------------------------------------------
    def connect(
        self,
        access_key_id: str,
        secret_access_key: str,
        session_token: str,
        identity_id: str = "",
    ) -> None:
        """Connect (or reconnect) using fresh credentials. Blocking call — run in executor."""
        with self._lock:
            self._disconnect_internal()
            self._connect_event.clear()
            self._connect_rc = None

            url = build_iot_wss_url(access_key_id, secret_access_key, session_token)
            parsed = urllib.parse.urlparse(url)
            ws_path = parsed.path + "?" + parsed.query

            # Use the same clientId format as the Broan app:
            # "#::app::<epoch_ms>::<cognito_identity_id>"
            # The IoT policy likely conditions on the identity_id being present.
            import time as _time
            ts = int(_time.time() * 1000)
            client_id = f"#::app::{ts}::{identity_id}" if identity_id else f"ha-broan-{self._thing_name}-{ts}"
            # paho-mqtt 2.0 requires CallbackAPIVersion; v1 does not have it.
            if _PAHO_V2:
                client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id=client_id,
                    transport="websockets",
                    protocol=mqtt.MQTTv311,
                )
            else:
                client = mqtt.Client(client_id=client_id, transport="websockets", protocol=mqtt.MQTTv311)
            import ssl as _ssl
            client.tls_set_context(_ssl.create_default_context())
            # AWS IoT device SDK always sets username to this value — required for connection
            client.username_pw_set(username="?SDK=JavaScript&Version=2.2.11")
            # Explicitly set Host header to the bare hostname (no :443) so it
            # matches the value we signed in the SigV4 canonical request.
            # paho-mqtt's default is "host:443" which would cause a sig mismatch.
            client.ws_set_options(
                path=ws_path,
                headers={"Host": IOT_ENDPOINT},
            )

            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect_cb
            client.on_message = self._on_message

            # Pre-flight: make a raw HTTPS request with WebSocket upgrade headers
            # so we can see the actual HTTP response code AWS IoT returns.
            # paho swallows the response — this surfaces it for diagnosis.
            self._ws_preflight(ws_path)

            try:
                client.connect(IOT_ENDPOINT, port=443, keepalive=30)
            except Exception as exc:
                _LOGGER.error("MQTT connect failed: %s", exc)
                raise

            self._client = client
            client.loop_start()

        if not self._connect_event.wait(timeout=10):
            self.disconnect()
            raise TimeoutError(
                f"Timed out waiting for MQTT WebSocket connection for {self._thing_name}"
            )

        if self._connect_rc not in (0, None):
            self.disconnect()
            raise ConnectionError(
                f"MQTT connection was rejected with code {self._connect_rc}"
            )

    # ------------------------------------------------------------------
    def _ws_preflight(self, ws_path: str) -> None:
        """Make a raw HTTPS WebSocket-upgrade request and log the response.

        This is a diagnostic-only call — it doesn't affect the actual
        paho connection. It lets us see the real HTTP status code that
        AWS IoT returns (paho discards it on failure).
        """
        try:
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(IOT_ENDPOINT, port=443, context=ctx)
            conn.request(
                "GET",
                ws_path,
                headers={
                    "Host": IOT_ENDPOINT,
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Version": "13",
                    "Sec-WebSocket-Key": "aGEtYnJvYW4tdGVzdA==",
                    "Sec-WebSocket-Protocol": "mqtt",
                },
            )
            resp = conn.getresponse()
            body = resp.read(512).decode("utf-8", errors="replace")
            _LOGGER.warning(
                "IoT WS preflight: HTTP %s %s | body: %s",
                resp.status, resp.reason, body,
            )
            conn.close()
        except Exception as exc:
            _LOGGER.warning("IoT WS preflight exception: %s", exc)

    def disconnect(self) -> None:
        """Cleanly disconnect."""
        with self._lock:
            self._disconnect_internal()

    def _disconnect_internal(self) -> None:
        if self._client:
            self._suppress_disconnect_cb = True
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._connected = False
            self._suppress_disconnect_cb = False
        self._connect_event.clear()
        self._connect_rc = None

    # ------------------------------------------------------------------
    def _on_connect(self, client: mqtt.Client, userdata: Any, flags, rc, properties=None) -> None:
        # paho v2: rc is a ReasonCode object; v1: rc is int
        rc_val = rc.value if hasattr(rc, "value") else rc
        self._connect_rc = rc_val
        self._connect_event.set()
        _LOGGER.warning(
            "MQTT _on_connect called: rc=%s flags=%s thing=%s",
            rc_val,
            flags,
            self._thing_name,
        )
        if rc_val != 0:
            _LOGGER.error("MQTT connect failed with code %s", rc_val)
            return
        _LOGGER.warning("MQTT connected successfully for %s", self._thing_name)
        self._connected = True

        # Subscribe to shadow responses
        client.subscribe([
            (_shadow_get_accepted(self._thing_name), 0),
            (_shadow_update_accepted(self._thing_name), 0),
            (_shadow_delete_accepted(self._thing_name), 0),
        ])
        _LOGGER.warning("MQTT subscribed to shadow topics for %s", self._thing_name)

        # Request current shadow state
        client.publish(_shadow_get(self._thing_name), "")

    def _on_disconnect_cb(self, client: mqtt.Client, userdata: Any, disconnect_flags=None, rc=None, properties=None) -> None:
        # paho v2 passes (client, userdata, disconnect_flags, reason_code, properties)
        # paho v1 passes (client, userdata, rc)
        if rc is None:
            rc = disconnect_flags  # v1 compat: rc is 3rd arg
        rc_val = rc.value if hasattr(rc, "value") else rc
        if rc_val not in (0, None) and not self._connect_event.is_set():
            self._connect_rc = rc_val
            self._connect_event.set()
        _LOGGER.warning("MQTT disconnected (rc=%s) for %s", rc_val, self._thing_name)
        self._connected = False
        if self._on_disconnect and not self._suppress_disconnect_cb:
            try:
                asyncio.run_coroutine_threadsafe(
                    _run_callback(self._on_disconnect), self._loop
                )
            except RuntimeError:
                pass  # event loop already closed (HA shutdown)

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        reported = (
            payload.get("state", {}).get("reported")
            if isinstance(payload.get("state"), dict)
            else None
        )
        if reported:
            asyncio.run_coroutine_threadsafe(
                _run_callback(self._on_state_update, reported), self._loop
            )

    # ------------------------------------------------------------------
    def set_shadow_property(self, field: str, value: str) -> None:
        """Publish a desired-state update. Values are always strings."""
        if not self._client or not self._connected:
            _LOGGER.warning("Cannot publish — not connected")
            return
        payload = json.dumps({"state": {"desired": {field: value}}})
        self._client.publish(_shadow_update(self._thing_name), payload, qos=0)

    @property
    def is_connected(self) -> bool:
        return self._connected


async def _run_callback(fn: Callable, *args: Any) -> None:
    """Await a coroutine or call a plain function."""
    if asyncio.iscoroutinefunction(fn):
        await fn(*args)
    else:
        fn(*args)
