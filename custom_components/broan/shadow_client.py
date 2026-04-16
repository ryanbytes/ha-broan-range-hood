"""
AWS IoT Device Shadow REST client with SigV4 signing.

Uses plain HTTPS (aiohttp) to GET/POST the device shadow — no MQTT/WebSocket
required. All requests are signed with temporary Cognito Identity credentials.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
from typing import Any

import aiohttp

from .const import AWS_REGION, IOT_ENDPOINT

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SigV4 helpers (REST variant — Authorization header, not pre-signed URL)
# ---------------------------------------------------------------------------

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


def _make_auth_headers(
    method: str,
    path: str,
    body: bytes,
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str = AWS_REGION,
    service: str = "iotdata",
) -> dict[str, str]:
    """Return the minimal SigV4-signed headers for a request."""
    now = datetime.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()

    # Canonical headers — must be sorted alphabetically by name
    canonical_headers = (
        f"host:{IOT_ENDPOINT}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-security-token:{session_token}\n"
    )
    signed_headers = "host;x-amz-date;x-amz-security-token"

    canonical_request = "\n".join([
        method,
        path,
        "",  # no query string
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    sig_key = _signing_key(secret_key, date_stamp, region, service)
    signature = hmac.new(
        sig_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return {
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "x-amz-date": amz_date,
        "x-amz-security-token": session_token,
        "host": IOT_ENDPOINT,
    }


# ---------------------------------------------------------------------------
# Shadow operations
# ---------------------------------------------------------------------------

class ShadowError(Exception):
    """IoT shadow operation failure."""


async def get_shadow(
    session: aiohttp.ClientSession,
    access_key: str,
    secret_key: str,
    session_token: str,
    thing_name: str,
) -> dict[str, Any]:
    """Fetch the device shadow and return the *reported* state dict."""
    path = f"/things/{thing_name}/shadow"
    url = f"https://{IOT_ENDPOINT}{path}"
    headers = _make_auth_headers("GET", path, b"", access_key, secret_key, session_token)

    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            text = await resp.text()
            _LOGGER.debug("Shadow GET %s → %s: %s", path, resp.status, text)
            raise ShadowError(f"Shadow GET failed {resp.status}: {text}")
        data = await resp.json(content_type=None)

    return data.get("state", {}).get("reported", {})


async def update_shadow(
    session: aiohttp.ClientSession,
    access_key: str,
    secret_key: str,
    session_token: str,
    thing_name: str,
    desired: dict[str, Any],
) -> None:
    """POST desired state to the device shadow."""
    path = f"/things/{thing_name}/shadow"
    url = f"https://{IOT_ENDPOINT}{path}"
    body = json.dumps({"state": {"desired": desired}}).encode()
    headers = _make_auth_headers("POST", path, body, access_key, secret_key, session_token)
    headers["content-type"] = "application/json"

    async with session.post(url, data=body, headers=headers) as resp:
        if resp.status not in (200, 202):
            text = await resp.text()
            _LOGGER.debug("Shadow POST %s → %s: %s", path, resp.status, text)
            raise ShadowError(f"Shadow POST failed {resp.status}: {text}")
