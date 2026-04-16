"""
Cognito SRP authentication + AWS Identity Pool credential exchange.

Implements USER_SRP_AUTH flow against AWS Cognito using pure Python
(no boto3/botocore dependency), then exchanges the ID token for temporary
AWS credentials via the Cognito Identity Pool.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import struct
import time
from typing import Any

import aiohttp

from .const import (
    AWS_REGION,
    COGNITO_CLIENT_ID,
    COGNITO_IDENTITY_POOL_ID,
    COGNITO_USER_POOL_ID,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SRP constants — Cognito uses the 3072-bit group
# ---------------------------------------------------------------------------
_N_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AAAC42DAD33170D04507A33A85521ABDF1CBA64"
    "ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6B"
    "F12FFA06D98A0864D87602733EC86A64521F2B18177B200C"
    "BBE117577A615D6C770988C0BAD946E208E24FA074E5AB31"
    "43DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF"
)

_N = int(_N_HEX, 16)
_G = 2
_INFO_BITS = b"Caldera Derived Key"


def _pad_hex(n: int) -> str:
    """Pad a big integer to even-length hex with leading zero if MSB >= 0x80."""
    h = format(n, "x")
    if len(h) % 2:
        h = "0" + h
    if int(h[0], 16) >= 8:
        h = "00" + h
    return h


def _sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def _hkdf(ikm: bytes, salt: bytes, length: int = 16) -> bytes:
    """HMAC-based Key Derivation Function (RFC 5869), SHA-256."""
    prk = _hmac_sha256(salt, ikm)
    t = b""
    okm = b""
    for i in range(1, -(-length // 32) + 1):
        t = _hmac_sha256(prk, t + _INFO_BITS + bytes([i]))
        okm += t
    return okm[:length]


def _compute_k() -> int:
    """k = H(N, g) — each value padded independently via _pad_hex (not to a common length)."""
    n_bytes = bytes.fromhex(_pad_hex(_N))   # 385 bytes (leading 0x00 because MSB >= 0x80)
    g_bytes = bytes.fromhex(_pad_hex(_G))   # 1 byte: 0x02
    return int(_sha256(n_bytes, g_bytes).hex(), 16)


_K = _compute_k()


class SRPHelper:
    """Generates SRP-A and computes the password claim."""

    def __init__(self) -> None:
        self._a = int.from_bytes(os.urandom(128), "big") % _N
        self._A = pow(_G, self._a, _N)

    @property
    def A_hex(self) -> str:
        return _pad_hex(self._A)

    def get_password_claim(
        self,
        username: str,
        password: str,
        salt_hex: str,
        srp_b_hex: str,
        secret_block_b64: str,
        timestamp: str,
        pool_name: str,
    ) -> str:
        """Compute PASSWORD_CLAIM_SIGNATURE."""
        B = int(srp_b_hex, 16)

        # u = H(A, B)
        u = int(
            _sha256(
                bytes.fromhex(self.A_hex),
                bytes.fromhex(_pad_hex(B)),
            ).hex(),
            16,
        )

        # x = H(salt || H(poolName || userId || ":" || password))
        user_id_hash = _sha256(
            f"{pool_name}{username}:{password}".encode("utf-8")
        )
        x = int(
            _sha256(
                bytes.fromhex(_pad_hex(int(salt_hex, 16))),
                user_id_hash,
            ).hex(),
            16,
        )

        # S = (B - k * g^x)^(a + u*x) mod N
        g_mod_pow_xn = pow(_G, x, _N)
        int_val2 = (_K * g_mod_pow_xn) % _N
        int_val3 = (B - int_val2) % _N
        S = pow(int_val3, self._a + u * x, _N)

        # HKDF over S
        s_bytes = bytes.fromhex(_pad_hex(S))
        u_bytes = bytes.fromhex(_pad_hex(u))
        key = _hkdf(s_bytes, u_bytes)

        # HMAC-SHA256 of pool_name + username + secret_block + timestamp
        msg = (
            pool_name.encode("utf-8")
            + username.encode("utf-8")
            + base64.b64decode(secret_block_b64)
            + timestamp.encode("utf-8")
        )
        sig = _hmac_sha256(key, msg)
        return base64.b64encode(sig).decode("utf-8")


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

class BroanTokens:
    """Holds Cognito tokens + Identity Pool credentials."""

    def __init__(self) -> None:
        self.id_token: str = ""
        self.access_token: str = ""
        self.refresh_token: str = ""
        self.token_expiry: float = 0.0

        self.aws_access_key_id: str = ""
        self.aws_secret_access_key: str = ""
        self.aws_session_token: str = ""
        self.aws_identity_id: str = ""
        self.creds_expiry: float = 0.0

    def tokens_valid(self) -> bool:
        return bool(self.id_token) and time.time() < self.token_expiry - 60

    def creds_valid(self) -> bool:
        return bool(self.aws_access_key_id) and time.time() < self.creds_expiry - 60


# ---------------------------------------------------------------------------
# Cognito helpers
# ---------------------------------------------------------------------------

_COGNITO_IDP_URL = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/"
_COGNITO_IDENTITY_URL = f"https://cognito-identity.{AWS_REGION}.amazonaws.com/"
_POOL_NAME = COGNITO_USER_POOL_ID.split("_")[1]  # e.g. "trauPt3X3"


async def _cognito_post(session: aiohttp.ClientSession, target: str, body: dict) -> dict:
    headers = {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": target,
    }
    async with session.post(_COGNITO_IDP_URL, json=body, headers=headers) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200:
            err_type = data.get("__type", "")
            err_msg = data.get("message", str(data))
            _LOGGER.debug("Cognito error [%s] %s: %s", resp.status, err_type, err_msg)
            raise AuthError(f"{err_type}: {err_msg}" if err_type else err_msg)
        return data


async def _identity_post(session: aiohttp.ClientSession, target: str, body: dict) -> dict:
    headers = {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": target,
    }
    async with session.post(_COGNITO_IDENTITY_URL, json=body, headers=headers) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200:
            raise AuthError(data.get("message") or data.get("__type") or str(data))
        return data


class AuthError(Exception):
    """Authentication failure."""


async def cognito_login(
    session: aiohttp.ClientSession,
    email: str,
    password: str,
) -> BroanTokens:
    """Full SRP auth flow. Returns a populated BroanTokens."""
    srp = SRPHelper()

    # Step 1 — InitiateAuth
    resp1 = await _cognito_post(
        session,
        "AWSCognitoIdentityProviderService.InitiateAuth",
        {
            "AuthFlow": "USER_SRP_AUTH",
            "ClientId": COGNITO_CLIENT_ID,
            "AuthParameters": {
                "USERNAME": email,
                "SRP_A": srp.A_hex,
            },
        },
    )

    challenge = resp1["ChallengeParameters"]
    user_id = challenge["USERNAME"]
    salt_hex = challenge["SALT"]
    srp_b_hex = challenge["SRP_B"]
    secret_block = challenge["SECRET_BLOCK"]
    pool_name = challenge.get("USER_ID_FOR_SRP", user_id)

    # Timestamp must be in the format: "Tue Mar 4 00:00:00 UTC 2014"
    # Use explicit English names — strftime %a/%b are locale-dependent.
    _DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    _MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    now = datetime.datetime.utcnow()
    timestamp = (
        f"{_DAYS[now.weekday()]} {_MONTHS[now.month - 1]} {now.day} "
        f"{now.strftime('%H:%M:%S')} UTC {now.year}"
    )

    claim = srp.get_password_claim(
        username=pool_name,
        password=password,
        salt_hex=salt_hex,
        srp_b_hex=srp_b_hex,
        secret_block_b64=secret_block,
        timestamp=timestamp,
        pool_name=_POOL_NAME,
    )

    # Step 2 — RespondToAuthChallenge
    resp2 = await _cognito_post(
        session,
        "AWSCognitoIdentityProviderService.RespondToAuthChallenge",
        {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ClientId": COGNITO_CLIENT_ID,
            "ChallengeResponses": {
                "USERNAME": user_id,
                "PASSWORD_CLAIM_SIGNATURE": claim,
                "PASSWORD_CLAIM_SECRET_BLOCK": secret_block,
                "TIMESTAMP": timestamp,
            },
        },
    )

    result = resp2["AuthenticationResult"]
    tokens = BroanTokens()
    tokens.id_token = result["IdToken"]
    tokens.access_token = result["AccessToken"]
    tokens.refresh_token = result["RefreshToken"]
    tokens.token_expiry = time.time() + result.get("ExpiresIn", 3600)

    await _refresh_aws_credentials(session, tokens)
    return tokens


async def cognito_refresh(
    session: aiohttp.ClientSession,
    tokens: BroanTokens,
) -> None:
    """Refresh the Cognito ID token using the refresh token (in place)."""
    resp = await _cognito_post(
        session,
        "AWSCognitoIdentityProviderService.InitiateAuth",
        {
            "AuthFlow": "REFRESH_TOKEN_AUTH",
            "ClientId": COGNITO_CLIENT_ID,
            "AuthParameters": {"REFRESH_TOKEN": tokens.refresh_token},
        },
    )
    result = resp["AuthenticationResult"]
    tokens.id_token = result["IdToken"]
    tokens.access_token = result["AccessToken"]
    tokens.token_expiry = time.time() + result.get("ExpiresIn", 3600)
    await _refresh_aws_credentials(session, tokens)


async def _refresh_aws_credentials(
    session: aiohttp.ClientSession,
    tokens: BroanTokens,
) -> None:
    """Exchange Cognito ID token for temporary AWS credentials via Identity Pool."""
    login_key = (
        f"cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
    )

    # GetId
    id_resp = await _identity_post(
        session,
        "AWSCognitoIdentityService.GetId",
        {
            "IdentityPoolId": COGNITO_IDENTITY_POOL_ID,
            "Logins": {login_key: tokens.id_token},
        },
    )
    identity_id = id_resp["IdentityId"]
    tokens.aws_identity_id = identity_id

    # GetCredentialsForIdentity
    creds_resp = await _identity_post(
        session,
        "AWSCognitoIdentityService.GetCredentialsForIdentity",
        {
            "IdentityId": identity_id,
            "Logins": {login_key: tokens.id_token},
        },
    )
    creds = creds_resp["Credentials"]
    tokens.aws_access_key_id = creds["AccessKeyId"]
    tokens.aws_secret_access_key = creds["SecretKey"]
    tokens.aws_session_token = creds["SessionToken"]
    # Expiration is an epoch timestamp (float)
    tokens.creds_expiry = float(creds.get("Expiration", time.time() + 3600))
