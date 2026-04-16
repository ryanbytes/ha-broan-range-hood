"""REST API client for the Broan production API Gateway."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import API_BASE_URL, APP_BRAND

_LOGGER = logging.getLogger(__name__)


class BroanApiClient:
    """Thin wrapper around the Broan REST API."""

    def __init__(self, session: aiohttp.ClientSession, id_token: str) -> None:
        self._session = session
        self._id_token = id_token

    def update_token(self, id_token: str) -> None:
        self._id_token = id_token

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._id_token,
            "custom-app-brand": APP_BRAND,
        }

    async def _post(self, path: str, body: dict) -> dict[str, Any]:
        url = f"{API_BASE_URL}/{path}"
        async with self._session.post(url, json=body, headers=self._headers()) as resp:
            data: dict = await resp.json(content_type=None)
            data["_ok"] = resp.ok
            data["_status"] = resp.status
            return data

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{API_BASE_URL}/{path}"
        async with self._session.get(url, headers=self._headers()) as resp:
            data: dict = await resp.json(content_type=None)
            data["_ok"] = resp.ok
            data["_status"] = resp.status
            return data

    # ------------------------------------------------------------------
    # Device management

    async def link_device(
        self,
        brand: str,
        model_name: str,
        serial_number: str,
        friendly_name: str,
    ) -> bool:
        """Register device to the authenticated user account."""
        result = await self._post(
            "device/link",
            {
                "brand": brand,
                "modelName": model_name,
                "serialNumber": serial_number,
                "deviceFriendlyName": friendly_name,
            },
        )
        return bool(result.get("_ok"))

    async def unlink_device(self, serial_number: str) -> bool:
        result = await self._post("device/unlink", {"serialNumber": serial_number})
        return bool(result.get("_ok"))

    async def check_provisioned(self, serial_number: str) -> bool:
        """Returns True if the device has been connected to Wi-Fi."""
        result = await self._post(
            "device/check-if-provisioned", {"serialNumber": serial_number}
        )
        return bool(result.get("_ok") and result.get("isProvisioned", result.get("provisioned")))

    async def change_friendly_name(self, serial_number: str, new_name: str) -> bool:
        result = await self._post(
            "device/change-friendly-name",
            {"serialNumber": serial_number, "newName": new_name},
        )
        return bool(result.get("_ok"))

    # ------------------------------------------------------------------
    # OTA / firmware

    async def get_latest_versions(self, serial_number: str) -> dict[str, Any]:
        """Returns esp/ui/main/fs latest versions and newUpdateAvailable flag."""
        return await self._post(
            "device-updater/get-latest-versions", {"serialNumber": serial_number}
        )

    async def get_ota_status(self, serial_number: str) -> dict[str, Any]:
        return await self._post(
            "device-updater/get-device-ota-status-to-handle",
            {"serialNumber": serial_number},
        )

    async def start_ota_update(self, serial_number: str) -> bool:
        result = await self._post(
            "device-updater/start-ota-update", {"serialNumber": serial_number}
        )
        return bool(result.get("done"))

    async def acknowledge_ota_status(self, serial_number: str) -> None:
        await self._post(
            "device-updater/acknowledge-device-ota-status",
            {"serialNumber": serial_number},
        )
