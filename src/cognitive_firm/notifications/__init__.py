"""Notification primitives.

``push_notification`` is the stable outbound API. The concrete provider is a
channel adapter, with Telegram as the default provider.
"""

from .push import push_notification, push_gate_escalation, NTFY_TOPIC
from .telegram import poll_inbound, reply, InboundMessage
from .channels import (
    NotificationIntent,
    build_notification_intent,
    get_notification_channel,
    send_notification,
)

__all__ = [
    "push_notification",
    "push_gate_escalation",
    "poll_inbound",
    "reply",
    "InboundMessage",
    "NotificationIntent",
    "build_notification_intent",
    "get_notification_channel",
    "send_notification",
    "NTFY_TOPIC",  # legacy; always None after GP-128b
]
