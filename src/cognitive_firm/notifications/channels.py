"""Notification channel facade.

The kernel publishes notification intents through this module. Concrete
providers such as Telegram are adapters, not protocol definitions.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationIntent:
    title: str
    message: str
    priority: str = "default"
    tags: tuple[str, ...] = ()
    click_url: str | None = None
    inline_buttons: tuple[tuple[str, str], ...] = ()


class NotificationChannel(Protocol):
    channel_id: str

    def send(self, intent: NotificationIntent, *, timeout_seconds: float = 5.0) -> bool:
        """Send a notification intent. Failures return False."""


class NullNotificationChannel:
    channel_id = "null"

    def send(self, intent: NotificationIntent, *, timeout_seconds: float = 5.0) -> bool:
        _ = timeout_seconds
        log.info("notification dropped by null channel: %s", intent.title)
        return False


class TelegramNotificationChannel:
    channel_id = "telegram"

    def send(self, intent: NotificationIntent, *, timeout_seconds: float = 5.0) -> bool:
        from cognitive_firm.notifications import telegram

        return telegram.push_notification(
            title=intent.title,
            message=intent.message,
            priority=intent.priority,
            tags=intent.tags,
            click_url=intent.click_url,
            timeout_seconds=timeout_seconds,
            inline_buttons=[list(button) for button in intent.inline_buttons] or None,
        )


def build_notification_intent(
    *,
    title: str,
    message: str,
    priority: str = "default",
    tags: Optional[Iterable[str]] = None,
    click_url: Optional[str] = None,
    inline_buttons: Optional[Iterable[tuple[str, str] | list[str]]] = None,
) -> NotificationIntent:
    buttons: list[tuple[str, str]] = []
    for button in inline_buttons or []:
        if len(button) != 2:
            raise ValueError("inline button entries must be (label, callback_data)")
        buttons.append((str(button[0]), str(button[1])))
    return NotificationIntent(
        title=title,
        message=message,
        priority=priority,
        tags=tuple(str(tag) for tag in tags or ()),
        click_url=click_url,
        inline_buttons=tuple(buttons),
    )


def get_notification_channel(channel_id: str | None = None) -> NotificationChannel:
    selected = (channel_id or os.environ.get("COGNITIVE_FIRM_NOTIFICATION_CHANNEL") or "telegram").strip().lower()
    if selected in {"", "none", "null", "off"}:
        return NullNotificationChannel()
    if selected == "telegram":
        return TelegramNotificationChannel()
    raise ValueError(f"unknown notification channel: {selected}")


def send_notification(
    intent: NotificationIntent,
    *,
    channel_id: str | None = None,
    timeout_seconds: float = 5.0,
) -> bool:
    try:
        channel = get_notification_channel(channel_id)
    except ValueError as exc:
        log.warning("%s", exc)
        return False
    try:
        return channel.send(intent, timeout_seconds=timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        log.warning("notification channel %s failed: %s", channel.channel_id, exc)
        return False
