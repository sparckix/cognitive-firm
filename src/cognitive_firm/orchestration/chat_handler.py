"""Per-role chat handler — read principal-sent messages, generate cheap-tier
LLM replies, append to per-role chat log.

Storage shape (one file per role per UTC date):
    org/sessions/<role_id>/chat/<YYYY-MM-DD>.jsonl

Each line is JSON:
    {
      "ts": "2026-05-07T17:30:00.000Z",
      "sender": "principal" | "agent_<role_id>",
      "text": "...",
      "id": "<uuid>"
    }

Called by:
    - scripts/agent_daemon.py at the top of each tick (process new principal
      messages → dispatch LLM reply → write back)
    - orbit/src/server/git-sync.ts via POST /api/chat/send (write principal
      message into the log; daemon picks it up next tick)

Design notes:
    - Replies use cheap-tier (per `model_economy` in principal.yaml) — chat
      is high-frequency low-stakes, never use mid/pro for casual exchanges
    - Reply prompt includes: role mandate excerpt + last N chat exchanges +
      principal preferences. NO full-context AGENTS.md — that's for tasks
    - If the message looks like a TASK ("@manager run X" or "do Y"), reply
      acknowledges + suggests the principal use the official task surface
      instead of chat (chat is for dialog, not work-dispatch)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
SESSIONS_ROOT = REPO_ROOT / "org" / "sessions"

# Cap chat history loaded into reply prompt — keep it fast + cheap.
MAX_HISTORY_FOR_REPLY = 20
# Cap reply length — chat shouldn't generate essays.
REPLY_MAX_TOKENS = 600


def _chat_log_path(role_id: str, day: Optional[str] = None) -> Path:
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return SESSIONS_ROOT / role_id / "chat" / f"{day}.jsonl"


def append_message(role_id: str, sender: str, text: str) -> dict:
    """Write a chat message to the role's per-day log. Returns the message dict."""
    path = _chat_log_path(role_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    msg = {
        "id": uuid.uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(),
        "sender": sender,
        "text": text,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(msg) + "\n")
    return msg


def read_messages(role_id: str, day: Optional[str] = None, limit: int = 100) -> list[dict]:
    """Return the last `limit` messages for this role+day in chronological order."""
    path = _chat_log_path(role_id, day)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out[-limit:]


def list_unanswered_principal_messages(role_id: str) -> list[dict]:
    """Return principal messages that have NO subsequent agent reply.

    Heuristic: walk messages in chrono order. Track last-seen sender. If the
    last message is from principal (no reply written after), it's pending.
    """
    msgs = read_messages(role_id, limit=500)
    if not msgs:
        return []
    # Pending = principal messages newer than the most recent agent reply
    last_agent_idx = -1
    for i, m in enumerate(msgs):
        if m.get("sender", "").startswith("agent_"):
            last_agent_idx = i
    pending = [m for m in msgs[last_agent_idx + 1:] if m.get("sender") == "principal"]
    return pending


def generate_and_store_reply(role_id: str, max_pending: int = 5) -> Optional[dict]:
    """If there are unanswered principal messages, generate a single combined
    reply and append it to the chat log. Returns the reply dict or None.

    Uses cheap-tier model per `model_economy` in principal.yaml. No-op if no
    LLM provider configured.
    """
    pending = list_unanswered_principal_messages(role_id)
    if not pending:
        return None
    pending = pending[-max_pending:]  # cap context

    # Build prompt
    history = read_messages(role_id, limit=MAX_HISTORY_FOR_REPLY)
    history_excerpt = "\n".join(
        f"  [{m.get('sender')}] {m.get('text', '')[:300]}"
        for m in history
    )
    pending_list = "\n".join(f"  - {m.get('text', '')[:500]}" for m in pending)

    # Try to load role mandate excerpt (first 1500 chars)
    mandate_excerpt = ""
    mandate_path = REPO_ROOT / "org" / "mandates" / f"{role_id}_mandate.md"
    if mandate_path.is_file():
        try:
            mandate_excerpt = mandate_path.read_text(encoding="utf-8")[:1500]
        except Exception:  # noqa: BLE001
            pass

    prompt = (
        f"You are the {role_id} role in an AI-native research org. "
        f"The principal sent you message(s) via the Orbit chat pane. "
        f"This is dialog — not a task dispatch. Reply concisely (≤200 words), "
        f"directly, conversational tone. If the message asks you to DO something "
        f"that requires real work (e.g. 'run a substrate', 'commit a charter "
        f"patch'), say so + point them at the official task/gate surface. "
        f"Don't pretend to have done work you haven't.\n\n"
        f"Your role mandate (excerpt):\n{mandate_excerpt}\n\n"
        f"Recent chat history (chronological):\n{history_excerpt}\n\n"
        f"Principal's pending message(s):\n{pending_list}\n\n"
        f"Reply (plain text, no markdown headers, ≤200 words):"
    )

    try:
        from src.cognitive_firm.common.llm_runtime import LLMRuntime, pick_model_for_tier
        model_id = pick_model_for_tier("cheap")
        if model_id is None:
            log.warning("chat_handler: no LLM provider available — cannot reply")
            return None
        runtime = LLMRuntime()
        resp = runtime.call_text(
            prompt, model_id=model_id, max_tokens=REPLY_MAX_TOKENS,
            request_label=f"chat_handler_reply:{role_id}",
        )
        reply_text = (resp.text or "").strip()
        if not reply_text:
            reply_text = "(empty reply — model returned no content)"
    except Exception as exc:  # noqa: BLE001
        log.warning("chat_handler reply failed: %s", exc)
        reply_text = f"(reply unavailable: {type(exc).__name__})"

    return append_message(role_id, sender=f"agent_{role_id}", text=reply_text)
