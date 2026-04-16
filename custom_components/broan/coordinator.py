"""
DataUpdateCoordinator for the Broan integration.

Manages:
  - Cognito token refresh cycle
  - AWS Identity Pool credential refresh cycle
  - MQTT WebSocket connection lifecycle
  - Distributing shadow state to all platform entities
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .auth import BroanTokens, cognito_login, cognito_refresh
from .const import (
    API_BASE_URL,
    CREDENTIALS_REFRESH_SECONDS,
    DOMAIN,
    TOKEN_REFRESH_SECONDS,
)
from .mqtt_client import BroanMqttClient
from .shadow_client import get_shadow, update_shadow

_LOGGER = logging.getLogger(__name__)
_THING_NAME_RE = re.compile(r"^[0-9a-f]{24}$", re.IGNORECASE)


class BroanCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages auth, MQTT, and state for one Broan device."""

    def __init__(
        self,
        hass: HomeAssistant,
        email: str,
        password: str,
        serial_number: str,
        device_name: str,
        device_uid: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{serial_number}",
            update_interval=None,
        )
        self._email = email
        self._password = password
        self.serial_number = serial_number
        self.device_name = device_name
        self.device_uid = device_uid
        self.thing_name = serial_number

        self._tokens: BroanTokens | None = None
        self._session: aiohttp.ClientSession | None = None
        self._mqtt: BroanMqttClient | None = None
        self._shadow_state: dict[str, Any] = {}

        self._token_refresh_task: asyncio.Task | None = None
        self._creds_refresh_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public helpers

    @property
    def id_token(self) -> str:
        return self._tokens.id_token if self._tokens else ""

    @property
    def shadow_state(self) -> dict[str, Any]:
        return self._shadow_state

    def get_shadow_value(self, field: str, as_int: bool = False) -> Any:
        val = self._shadow_state.get(field)
        if val is not None and as_int:
            try:
                return int(val)
            except (ValueError, TypeError):
                return None
        return val

    def set_property(self, field: str, value: Any) -> None:
        """Send a desired-state update to the device shadow."""
        self.hass.async_create_task(self._async_set_property(field, value))

    # ------------------------------------------------------------------
    # Lifecycle

    async def async_setup(self) -> None:
        """Authenticate and connect MQTT. Called once during integration setup."""
        self._session = aiohttp.ClientSession()
        await self._do_login()
        await self._connect_mqtt()
        await self._async_prime_shadow()
        self._schedule_token_refresh()
        self._schedule_creds_refresh()

    async def async_shutdown(self) -> None:
        if self._token_refresh_task:
            self._token_refresh_task.cancel()
        if self._creds_refresh_task:
            self._creds_refresh_task.cancel()
        if self._reconnect_task:
            self._reconnect_task.cancel()
        if self._mqtt:
            await self.hass.async_add_executor_job(self._mqtt.disconnect)
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------
    # Auth

    async def _do_login(self) -> None:
        assert self._session
        _LOGGER.debug("Authenticating with Cognito for %s", self._email)
        self._tokens = await cognito_login(self._session, self._email, self._password)
        _LOGGER.debug("Authentication successful")
        await self._discover_thing_name()

    async def _discover_thing_name(self) -> None:
        """Best-effort lookup for the AWS IoT thing name used by the mobile app."""
        assert self._session and self._tokens
        try:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": self._tokens.id_token,
                "custom-app-brand": "broan",
            }
            async with self._session.post(
                f"{API_BASE_URL}/device/check-if-provisioned",
                json={"serialNumber": self.serial_number},
                headers=headers,
            ) as resp:
                data = await resp.json(content_type=None)
                thing_name = self._extract_thing_name(data)
                if thing_name and self._should_use_thing_name(thing_name):
                    self.thing_name = thing_name
                    _LOGGER.debug(
                        "Resolved Broan thing name %s for serial %s",
                        self.thing_name,
                        self.serial_number,
                    )
        except Exception as exc:
            _LOGGER.debug("Could not resolve thing name for %s: %s", self.serial_number, exc)

    async def _do_token_refresh(self) -> None:
        assert self._session and self._tokens
        _LOGGER.debug("Refreshing Cognito tokens")
        try:
            await cognito_refresh(self._session, self._tokens)
            _LOGGER.debug("Token refresh successful")
        except Exception as exc:
            _LOGGER.error("Token refresh failed: %s — re-authenticating", exc)
            await self._do_login()

    async def _do_creds_refresh(self) -> None:
        """Reconnect MQTT with fresh AWS credentials."""
        assert self._tokens
        _LOGGER.debug("Refreshing AWS IoT credentials")
        await self._connect_mqtt()

    # ------------------------------------------------------------------
    # MQTT

    async def _connect_mqtt(self) -> None:
        assert self._tokens

        if self._mqtt:
            await self.hass.async_add_executor_job(self._mqtt.disconnect)

        self._mqtt = BroanMqttClient(
            thing_name=self.thing_name,
            loop=self.hass.loop,
            on_state_update=self._handle_shadow_update,
            on_disconnect=self._handle_mqtt_disconnect,
        )

        await self.hass.async_add_executor_job(
            self._mqtt.connect,
            self._tokens.aws_access_key_id,
            self._tokens.aws_secret_access_key,
            self._tokens.aws_session_token,
            self._tokens.aws_identity_id,   # pass identity_id for clientId
        )

    async def _async_prime_shadow(self) -> None:
        """Fetch current state once so entities have initial data immediately."""
        assert self._session and self._tokens
        try:
            reported = await get_shadow(
                self._session,
                self._tokens.aws_access_key_id,
                self._tokens.aws_secret_access_key,
                self._tokens.aws_session_token,
                self.thing_name,
            )
        except Exception as exc:
            _LOGGER.debug("Initial shadow fetch failed for %s: %s", self.thing_name, exc)
            return
        self._handle_shadow_update(reported)

    async def _async_set_property(self, field: str, value: Any) -> None:
        """Update the device shadow via MQTT when available, otherwise via REST."""
        if self._mqtt and self._mqtt.is_connected:
            self._mqtt.set_shadow_property(field, str(value))
            return

        if not self._session or not self._tokens:
            _LOGGER.warning("Cannot set property %s because auth is not ready", field)
            return

        try:
            await update_shadow(
                self._session,
                self._tokens.aws_access_key_id,
                self._tokens.aws_secret_access_key,
                self._tokens.aws_session_token,
                self.thing_name,
                {field: str(value)},
            )
        except Exception as exc:
            _LOGGER.warning("REST shadow update failed for %s: %s", field, exc)
            return

        self._shadow_state[field] = str(value)
        self.async_set_updated_data(dict(self._shadow_state))

    @staticmethod
    def _extract_thing_name(payload: Any) -> str | None:
        """Pull a likely thing-name field out of a Broan API response."""
        if isinstance(payload, dict):
            for key in (
                "thingName",
                "thing_name",
                "awsThingName",
                "awsIotThingName",
                "iotThingName",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            for key in ("device", "data", "result"):
                nested = payload.get(key)
                thing_name = BroanCoordinator._extract_thing_name(nested)
                if thing_name:
                    return thing_name

        if isinstance(payload, list):
            for item in payload:
                thing_name = BroanCoordinator._extract_thing_name(item)
                if thing_name:
                    return thing_name

        return None

    def _should_use_thing_name(self, candidate: str) -> bool:
        """Only switch to candidates that look like the AWS IoT thing name."""
        if _THING_NAME_RE.fullmatch(candidate):
            return True
        return not _THING_NAME_RE.fullmatch(self.thing_name) and candidate == self.thing_name

    def _handle_shadow_update(self, reported: dict[str, Any]) -> None:
        """Called from MQTT thread (via run_coroutine_threadsafe)."""
        self._shadow_state.update(reported)
        self.async_set_updated_data(dict(self._shadow_state))

    async def _handle_mqtt_disconnect(self) -> None:
        if self._reconnect_task and not self._reconnect_task.done():
            return  # reconnect already in progress
        self._reconnect_task = self.hass.loop.create_task(self._do_reconnect())

    async def _do_reconnect(self) -> None:
        _LOGGER.warning("MQTT disconnected — will attempt reconnect with backoff")
        delays = [5, 15, 30, 60, 120]
        for delay in delays:
            await asyncio.sleep(delay)
            try:
                await self._connect_mqtt()
                _LOGGER.info("MQTT reconnected successfully")
                return
            except Exception as exc:
                _LOGGER.warning("MQTT reconnect failed: %s — retrying", exc)
        _LOGGER.error("MQTT reconnect failed after all retries — will retry on next credential refresh")

    # ------------------------------------------------------------------
    # DataUpdateCoordinator override

    async def _async_update_data(self) -> dict[str, Any]:
        """Called on manual refresh — return current cached state."""
        return dict(self._shadow_state)

    # ------------------------------------------------------------------
    # Refresh scheduling

    def _schedule_token_refresh(self) -> None:
        async def _task() -> None:
            while True:
                await asyncio.sleep(TOKEN_REFRESH_SECONDS)
                try:
                    await self._do_token_refresh()
                except Exception as exc:
                    _LOGGER.error("Token refresh task error: %s", exc)

        self._token_refresh_task = self.hass.loop.create_task(_task())

    def _schedule_creds_refresh(self) -> None:
        async def _task() -> None:
            while True:
                await asyncio.sleep(CREDENTIALS_REFRESH_SECONDS)
                try:
                    await self._do_creds_refresh()
                except Exception as exc:
                    _LOGGER.error("Credential refresh task error: %s", exc)

        self._creds_refresh_task = self.hass.loop.create_task(_task())
