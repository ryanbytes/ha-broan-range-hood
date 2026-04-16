"""Config flow for Broan Range Hood."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .auth import AuthError, cognito_login
from .const import CONF_DEVICE_NAME, CONF_SERIAL_NUMBER, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SERIAL_NUMBER): str,
        vol.Optional(CONF_DEVICE_NAME, default="Range Hood"): str,
    }
)


class BroanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Broan config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input[CONF_SERIAL_NUMBER].strip().upper()

            # Prevent duplicate entries for the same serial
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()

            # Validate credentials
            try:
                async with aiohttp.ClientSession() as session:
                    await cognito_login(
                        session,
                        user_input[CONF_EMAIL],
                        user_input[CONF_PASSWORD],
                    )
            except AuthError as exc:
                _LOGGER.warning("Broan auth error: %s", exc)
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_DEVICE_NAME, "Range Hood"),
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SERIAL_NUMBER: serial,
                        CONF_DEVICE_NAME: user_input.get(CONF_DEVICE_NAME, "Range Hood"),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "serial_help": (
                    "The serial number is printed on the label inside your range hood. "
                    "The integration will resolve the separate AWS IoT Thing Name automatically."
                )
            },
        )
