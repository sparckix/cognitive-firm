from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.notifications.channels import (  # noqa: E402
    NotificationIntent,
    build_notification_intent,
    get_notification_channel,
    send_notification,
)


def test_build_notification_intent_normalizes_buttons():
    intent = build_notification_intent(
        title="Gate",
        message="Approve?",
        tags=["gate"],
        inline_buttons=[("Approve", "approve:gate_1")],
    )

    assert intent.tags == ("gate",)
    assert intent.inline_buttons == (("Approve", "approve:gate_1"),)


def test_null_notification_channel_is_selectable():
    channel = get_notification_channel("null")

    assert channel.channel_id == "null"
    assert channel.send(NotificationIntent(title="t", message="m")) is False


def test_send_notification_routes_to_telegram_adapter():
    with patch("cognitive_firm.notifications.telegram.push_notification", return_value=True) as push:
        ok = send_notification(
            NotificationIntent(
                title="Decision",
                message="Test",
                priority="high",
                tags=("gate",),
                inline_buttons=(("Approve", "approve:gate_1"),),
            ),
            channel_id="telegram",
        )

    assert ok is True
    push.assert_called_once()
    assert push.call_args.kwargs["title"] == "Decision"
    assert push.call_args.kwargs["inline_buttons"] == [["Approve", "approve:gate_1"]]
