"""Helpers for parsing Broan factory settings."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BroanFactorySettings:
    """Subset of parsed factory settings used by the integration."""

    model: str | None = None
    printed_serial: str | None = None
    light_levels: int | None = None
    fan_speeds: int | None = None


def parse_factory_settings(raw: str | None) -> BroanFactorySettings:
    """Parse the pipe-delimited factory settings payload from the hood."""
    if not raw:
        return BroanFactorySettings()

    try:
        parts = raw.split("|")
        return BroanFactorySettings(
            model=parts[0] or None if len(parts) > 0 else None,
            printed_serial=parts[1] or None if len(parts) > 1 else None,
            light_levels=_safe_int(parts[3]) if len(parts) > 3 else None,
            fan_speeds=_safe_int(parts[5]) if len(parts) > 5 else None,
        )
    except Exception:
        return BroanFactorySettings()


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
