"""Shared connector-family names for integration and state-boundary modules."""

from __future__ import annotations

from typing import Literal


ConnectorFamily = Literal[
    "app_surface",
    "enterprise_system",
    "runtime",
    "state_backend",
    "inbound_event",
    "notification",
    "identity_provider",
    "tenant_adapter",
]

CONNECTOR_FAMILIES: tuple[str, ...] = (
    "app_surface",
    "enterprise_system",
    "runtime",
    "state_backend",
    "inbound_event",
    "notification",
    "identity_provider",
    "tenant_adapter",
)


def validate_connector_family(value: str) -> str:
    text = value.strip().lower()
    if text not in CONNECTOR_FAMILIES:
        raise ValueError(f"unknown connector family: {value!r}")
    return text
