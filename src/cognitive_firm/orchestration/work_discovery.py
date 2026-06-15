"""GP-131 Work-Discovery Loop — two-source prototype.

The Level 2 daemon (GP-128 § Future Work) needs to identify work
worth doing without being told. This module implements the two
cheapest + highest-signal-density discovery sources from GP-131:

1. TODO-scan   — open TODO boxes in seam files (self-authored, pre-filtered)
2. Damage-scan — unresolved signals from cognitive_firm.signals.damage
3. Agent-channel — durable messages sent from one persistent role office
   to another
4. Evidence gaps + human work sessions — typed learning carriers that need
   collection, review, human execution, or integration
5. Approved learning events — active behavior changes future role work should
   encounter before repeating old failure modes

Each source produces Candidate objects with a scarcity signal and an
"intent" field (not "procedure" — GP-129 Godfrey-Smith pull-forward).
Candidates are NOT executed; they are returned to a ranker that picks
one for inbox escalation, human-in-loop.

This is the prototype. The full ranker + proposal-envelope writer
live in a separate module once the first 30 proposals have calibrated
the source weights.
"""

from __future__ import annotations

import os
import re
import time
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from cognitive_firm.common.paths import ORG_ROOT_DIR, REPO_ROOT, WORKSPACE_DIR
from cognitive_firm.orchestration.execution_routing import infer_execution_route
from cognitive_firm.signals import damage


SEAMS_ROOT = WORKSPACE_DIR / "seams" / "mission"
TODO_PATTERN = re.compile(r"^\s*-\s*\[\s*\]\s+(.+)$", re.MULTILINE)


@dataclass
class Candidate:
    """A discovered work item, not yet proposed to the principal."""
    source: str                     # TODO-scan | damage-scan | closure-map | ...
    intent: str                     # one-sentence, what-for (not how)
    origin_path: Optional[Path]     # seam file, signal file, etc.
    scarcity_signal: str            # why this surfaced now
    raw_text: str                   # verbatim excerpt for triage
    age_days: Optional[float] = None
    severity: str = "info"          # info | warn | critical
    metadata: dict = field(default_factory=dict)


def candidate_as_dict(candidate: Candidate) -> dict[str, Any]:
    """Serialize a discovery candidate for service/userland read models."""
    return {
        "source": candidate.source,
        "intent": candidate.intent,
        "origin_path": str(candidate.origin_path) if candidate.origin_path else None,
        "scarcity_signal": candidate.scarcity_signal,
        "raw_text": candidate.raw_text,
        "age_days": candidate.age_days,
        "severity": candidate.severity,
        "metadata": dict(candidate.metadata),
    }


def discover_open_todos(
    *,
    root: Path = SEAMS_ROOT,
    max_per_source: int = 10,
) -> list[Candidate]:
    """Scan seam files for open `- [ ]` TODO boxes.

    Returns candidates ranked by file-mtime-desc then position-in-file.
    Stale seams (mtime > 60 days) are skipped — the GP-131 trail-lock-in
    defense says stale TODOs are a separate signal class and should not
    crowd out fresh items.
    """
    if not root.exists():
        return []

    now = time.time()
    stale_cutoff = now - 60 * 24 * 3600  # 60 days

    candidates: list[Candidate] = []
    seam_files = sorted(
        (p for p in root.glob("*.md") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for seam in seam_files:
        mtime = seam.stat().st_mtime
        if mtime < stale_cutoff:
            continue
        age_days = (now - mtime) / 86400.0
        try:
            text = seam.read_text(encoding="utf-8")
        except Exception:
            continue

        for match in TODO_PATTERN.finditer(text):
            todo = match.group(1).strip()
            if not todo or len(todo) < 10:
                continue
            candidates.append(Candidate(
                source="TODO-scan",
                intent=todo[:200],
                origin_path=seam,
                scarcity_signal=(
                    f"open TODO in seam last touched {age_days:.1f} days ago; "
                    "self-authored commitment not yet closed"
                ),
                raw_text=todo,
                age_days=age_days,
                severity="info",
                metadata={"seam": seam.name},
            ))

    # Cap + stable ordering: freshest seams first, then order of TODOs
    # within file preserved.
    return candidates[:max_per_source]


def discover_damage_signals(
    *,
    max_per_source: int = 10,
) -> list[Candidate]:
    """Scan unresolved damage signals.

    Every damage signal is already a scarcity-filtered event — someone
    or something wrote it because an invariant was violated. Critical
    signals jump to the top regardless of age.
    """
    signals = damage.list_recent(limit=max_per_source * 3)
    now = datetime.now(timezone.utc)

    candidates: list[Candidate] = []
    for s in signals:
        try:
            ts = datetime.fromisoformat(s.timestamp_utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (now - ts).total_seconds() / 86400.0
        except ValueError:
            age = None

        intent = (
            f"resolve {s.kind} signal from {s.source}"
            if s.severity != "critical"
            else f"HARD STOP: critical {s.kind} signal from {s.source}"
        )
        candidates.append(Candidate(
            source="damage-scan",
            intent=intent,
            origin_path=None,
            scarcity_signal=(
                f"{s.severity}-severity signal, age {age:.2f} days"
                if age is not None else f"{s.severity}-severity signal"
            ),
            raw_text=s.detail,
            age_days=age,
            severity=s.severity,
            metadata={
                "source": s.source,
                "kind": s.kind,
                "timestamp_utc": s.timestamp_utc,
                "session_id": s.session_id,
            },
        ))

    # Critical first, then by age ascending (newer first).
    def sort_key(c: Candidate) -> tuple:
        sev_rank = {"critical": 0, "warn": 1, "info": 2}.get(c.severity, 3)
        return (sev_rank, c.age_days if c.age_days is not None else 1e9)

    candidates.sort(key=sort_key)
    return candidates[:max_per_source]


def discover_principal_goals(
    *,
    assigned_to: Optional[str] = None,
    max_per_source: int = 10,
) -> list[Candidate]:
    """GP-132 source: pending tasks the principal wrote to org/tasks/pending/.

    These are the HIGHEST-priority discovery source because they carry
    explicit principal intent — not inferred from artifacts, but stated.
    """
    from cognitive_firm.orchestration.goals_inbox import list_pending_goals
    goals = list_pending_goals(assigned_to=assigned_to)
    out: list[Candidate] = []
    for g in goals[:max_per_source]:
        route = infer_execution_route(
            frontmatter=g.raw_frontmatter,
            body=g.body,
            role_id=(assigned_to or g.assigned_to).replace("role.", "", 1),
        )
        severity = (
            "critical" if g.priority.lower() == "urgent" else
            "warn" if g.priority.lower() == "high" else
            "info"
        )
        out.append(Candidate(
            source="principal-goal",
            intent=(
                f"[{g.priority}] execute principal goal: {g.goal_id}"
                + (f" (deadline {g.deadline})" if g.deadline else "")
            ),
            origin_path=g.path,
            scarcity_signal=(
                "explicit principal directive in org/tasks/pending/ — "
                f"autonomous_scope_ok={g.autonomous_scope_ok}, "
                f"estimated_cost=${g.estimated_cost_usd:.2f}"
            ),
            raw_text=g.body[:500],
            age_days=None,
            severity=severity,
            metadata={
                "goal_id": g.goal_id,
                "priority": g.priority,
                "deadline": g.deadline,
                "estimated_cost_usd": g.estimated_cost_usd,
                "assigned_to": g.assigned_to,
                "autonomous_scope_ok": g.autonomous_scope_ok,
                "declared_paths": g.raw_frontmatter.get("declared_paths") or (),
                "execution_route": route.as_dict(),
                "frontmatter": g.raw_frontmatter,
            },
        ))
    return out


def discover_agent_channel_messages(
    *,
    assigned_to: Optional[str] = None,
    max_per_source: int = 10,
) -> list[Candidate]:
    """Surface open messages in a persistent role's A2A inbox."""
    if not assigned_to or not assigned_to.startswith("role."):
        return []
    role_id = assigned_to.split(".", 1)[1]
    from cognitive_firm.orchestration.agent_channels import list_agent_messages

    out: list[Candidate] = []
    for msg in list_agent_messages(role_id=role_id, status="open", limit=max_per_source):
        severity = "warn" if msg.expects_response or msg.kind in {"request", "handoff"} else "info"
        out.append(Candidate(
            source="agent-channel",
            intent=f"respond to {msg.kind} from {msg.from_role}: {msg.subject}",
            origin_path=None,
            scarcity_signal=(
                "open persistent-agent message"
                + (" requiring response" if msg.expects_response else "")
            ),
            raw_text=msg.body[:1000],
            age_days=None,
            severity=severity,
            metadata={
                "message_id": msg.message_id,
                "thread_id": msg.thread_id,
                "from_role": msg.from_role,
                "to_role": msg.to_role,
                "kind": msg.kind,
                "expects_response": msg.expects_response,
                "references": msg.references,
                "artifacts": msg.artifacts,
            },
        ))
    return out


def discover_evidence_gaps(
    *,
    assigned_to: Optional[str] = None,
    max_per_source: int = 10,
) -> list[Candidate]:
    """Surface open evidence gaps as work candidates.

    Evidence gaps are not passive notes. Blocking gaps should interrupt normal
    work; useful gaps become collection/review work when assigned to a role or
    when discovery runs without a role filter.
    """
    from cognitive_firm.orchestration.evidence_gaps import list_evidence_gaps

    role_match = (
        assigned_to.split(".", 1)[1]
        if assigned_to and assigned_to.startswith("role.")
        else assigned_to
    )
    out: list[Candidate] = []
    for gap in list_evidence_gaps()[: max_per_source * 3]:
        if gap.status == "closed":
            continue
        if role_match and gap.owner_role and gap.owner_role not in {assigned_to, role_match}:
            continue
        if role_match and not gap.owner_role and gap.severity != "blocking":
            continue
        severity = "critical" if gap.severity == "blocking" else "warn"
        out.append(Candidate(
            source="evidence-gap",
            intent=f"resolve evidence gap for {gap.target}",
            origin_path=None,
            scarcity_signal=(
                f"{gap.severity} evidence gap is {gap.status}"
                + (f"; owner_role={gap.owner_role}" if gap.owner_role else "")
            ),
            raw_text=gap.description,
            age_days=None,
            severity=severity,
            metadata={
                "gap_id": gap.gap_id,
                "gap_type": gap.gap_type,
                "target": gap.target,
                "status": gap.status,
                "severity": gap.severity,
                "fetch_query": gap.fetch_query,
                "owner_role": gap.owner_role,
                "tenant_id": gap.tenant_id,
                "project_id": gap.project_id,
                "adversarial_direction": gap.adversarial_direction,
            },
        ))
        if len(out) >= max_per_source:
            break
    return out


def discover_human_work_sessions(
    *,
    assigned_to: Optional[str] = None,
    max_per_source: int = 10,
) -> list[Candidate]:
    """Surface human work sessions that need coordination or integration."""
    from cognitive_firm.orchestration.human_work import list_human_work_sessions

    role_match = (
        assigned_to.split(".", 1)[1]
        if assigned_to and assigned_to.startswith("role.")
        else assigned_to
    )
    actionable_states = {"requested", "blocked", "handed_off", "completed"}
    out: list[Candidate] = []
    for session in list_human_work_sessions()[: max_per_source * 3]:
        if session.state not in actionable_states:
            continue
        is_a2h = (
            session.metadata.get("coordination_pattern") == "a2h_work_request"
            or bool(session.agent_counterparty_role and session.agent_followup_required)
        )
        if is_a2h and session.state == "requested":
            continue
        if role_match:
            role_names = set(session.collaborating_roles)
            role_names.update(
                role.split(".", 1)[1]
                for role in session.collaborating_roles
                if role.startswith("role.")
            )
            if session.agent_counterparty_role:
                role_names.add(session.agent_counterparty_role)
                if session.agent_counterparty_role.startswith("role."):
                    role_names.add(session.agent_counterparty_role.split(".", 1)[1])
            if (
                assigned_to not in role_names
                and role_match not in role_names
                and session.requested_by not in {assigned_to, role_match}
            ):
                continue
        receipt_missing = session.receipt_required and not (session.receipt or "").strip()
        severity = (
            "critical"
            if session.state == "completed" and session.agent_followup_required
            else "warn"
            if session.state in {"blocked", "completed"} or receipt_missing
            else "info"
        )
        action = (
            "integrate completed human work"
            if session.state == "completed"
            else "coordinate human work"
        )
        if (
            session.agent_followup_required
            and session.agent_counterparty_role
            and session.state in {"handed_off", "completed"}
        ):
            action = f"A2H follow-up for {session.agent_counterparty_role}"
        out.append(Candidate(
            source="human-work",
            intent=f"{action}: {session.objective}",
            origin_path=None,
            scarcity_signal=(
                f"human work session is {session.state}; "
                f"mode={session.work_mode}; bottleneck={session.bottleneck_class}"
                + ("; receipt missing" if receipt_missing else "")
                + ("; agent follow-up required" if session.agent_followup_required else "")
            ),
            raw_text=session.completion_summary or session.objective,
            age_days=None,
            severity=severity,
            metadata={
                "session_id": session.session_id,
                "state": session.state,
                "requested_by": session.requested_by,
                "human_actor": session.human_actor,
                "agent_counterparty_role": session.agent_counterparty_role,
                "human_deliverable": session.human_deliverable,
                "agent_followup_required": session.agent_followup_required,
                "coordination_pattern": session.metadata.get("coordination_pattern"),
                "work_mode": session.work_mode,
                "bottleneck_class": session.bottleneck_class,
                "observability": session.observability,
                "receipt_required": session.receipt_required,
                "receipt_type": session.receipt_type,
                "receipt": session.receipt,
                "confidence": session.confidence,
                "sample_for_review": session.sample_for_review,
                "tenant_id": session.tenant_id,
                "project_id": session.project_id,
            },
        ))
        if len(out) >= max_per_source:
            break
    return out


def discover_resolved_pending_execution(
    *,
    assigned_to: Optional[str] = None,
    max_per_source: int = 10,
) -> list[Candidate]:
    """Pick up gates that were resolved (approve) but never executed.

    Use case: a nested gate (claude wrote a gate during dispatch and exited)
    OR an orbit-side resolve via /api/gate/resolve. The daemon's normal
    `_wait_for_gate_resolution` flow only watches for resolution of gates
    IT opened in the same tick. Out-of-band resolutions need rediscovery.

    Returns Candidate objects whose intent describes the action to dispatch
    (typically a `make` command extracted from the gate's summary). The
    daemon's main flow will then dispatch claude/codex to run it.

    Idempotency: once dispatched, the daemon writes a sibling `.dispatched`
    file next to the resolved gate so it's not re-discovered.
    """
    out: list[Candidate] = []
    if assigned_to and assigned_to.startswith("role."):
        owner_match = assigned_to.split(".", 1)[1]
    else:
        owner_match = None

    resolved_dir = WORKSPACE_DIR / "gates" / "resolved"
    if not resolved_dir.exists():
        return out

    import json as _json
    for path in sorted(resolved_dir.glob("proposal_*.json"), key=lambda p: -p.stat().st_mtime)[:max_per_source]:
        # Skip if dispatched already
        if path.with_suffix(".dispatched").exists():
            continue
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if data.get("status") != "resolved":
            continue
        chosen = data.get("resolution", {}).get("chosen_option")
        if chosen != "approve":
            # mark non-approve as "dispatched" so we don't re-scan
            try:
                path.with_suffix(".dispatched").write_text("non-approve\n")
            except Exception:  # noqa: BLE001
                pass
            continue
        owner = data.get("owner")
        if owner_match and owner != owner_match:
            continue
        # Build a Candidate the daemon will dispatch
        intent = data.get("candidate", {}).get("intent") or data.get("subject", "")
        out.append(Candidate(
            source="resolved-pending-execution",
            intent=f"execute resolved gate: {intent[:140]}",
            origin_path=path,
            scarcity_signal=(
                f"gate {data.get('gate_id', '?')} approved at "
                f"{data.get('resolution', {}).get('resolved_utc', '?')[:19]}; "
                f"awaiting dispatch"
            ),
            raw_text=data.get("summary", ""),
            severity="warn",  # approved + pending execution should rank above TODO scans
            metadata={
                "resolved_gate_id": data.get("gate_id"),
                "resolved_gate_path": str(path),
                "owner": owner,
                "kind": "execute-resolved-gate",
                # Preserve original candidate metadata for downstream auth
                **{k: v for k, v in (data.get("candidate", {}).get("metadata") or {}).items()
                   if k in ("assigned_to", "estimated_cost_usd", "execution_route", "frontmatter", "priority")},
            },
        ))
    return out


def discover_open_debates(
    *,
    assigned_to: Optional[str] = "debate_runner",
    idle_threshold_hours: float = 6.0,
    max_per_source: int = 5,
) -> list[Candidate]:
    """Surface stale seam-debate work for the debate-runner role.

    Scans the configured debate carrier root for Markdown files that are
    tagged as active debates, have not had a turn appended in the last
    `idle_threshold_hours`, and have not reached CONVERGED or ESCALATED_CAP
    in an embedded debate-state marker.

    Returns a list of Candidate objects with kind="debate_turn". The
    daemon dispatches these as resolved-pending-execution candidates;
    the actual debate-turn machinery lives in the tenant/app layer.

    Discovery heuristic:
      - File contains a `<!-- debate_state:` comment OR the file ends
        with a turn marker (e.g., "## Turn N — <speaker>") AND
      - Last modification time exceeds idle_threshold_hours AND
      - File path is under the configured debate carrier root.

    This is intentionally shallow. Rich debate parsing belongs in a tenant
    adapter; the kernel only detects stale open debate carriers.
    """
    import time
    from datetime import datetime, timedelta, timezone

    out: list[Candidate] = []
    seams_root = SEAMS_ROOT
    if not seams_root.exists():
        return out

    cutoff = datetime.now(timezone.utc) - timedelta(hours=idle_threshold_hours)

    for seam_path in seams_root.rglob("*.md"):
        try:
            mtime = datetime.fromtimestamp(seam_path.stat().st_mtime, tz=timezone.utc)
            if mtime > cutoff:
                continue
            text = seam_path.read_text(encoding="utf-8", errors="ignore")
            if "debate_state:" not in text and "## Turn " not in text:
                continue
            verdict = _extract_debate_verdict(text)
            if verdict in ("CONVERGED", "ESCALATED_CAP"):
                continue
            try:
                seam_ref = str(seam_path.relative_to(REPO_ROOT))
            except ValueError:
                seam_ref = str(seam_path)
            out.append(Candidate(
                source="open_debate",
                intent=f"Append turn to stagnant debate: {seam_path.name}",
                origin_path=seam_path,
                scarcity_signal="stagnant_open_debate",
                raw_text=seam_ref,
                metadata={
                    "assigned_to": assigned_to or "debate_runner",
                    "kind": "debate_turn",
                    "ref": seam_ref,
                    "idle_hours": (datetime.now(timezone.utc) - mtime).total_seconds() / 3600,
                    "execution_route": "tenant_debate_runner",
                    "priority": "P1",
                },
            ))
            if len(out) >= max_per_source:
                break
        except Exception:  # noqa: BLE001
            continue

    return out


def _extract_debate_verdict(text: str) -> str | None:
    marker = "debate_state:"
    if marker not in text:
        return None
    after = text.split(marker, 1)[1][:500]
    for token in ("CONVERGED", "ESCALATED_CAP", "OPEN", "ACTIVE", "PENDING"):
        if token in after:
            return token
    return None


def discover_substrate_portfolio_opportunities(
    *,
    assigned_to: Optional[str] = None,
    max_per_source: int = 10,
) -> list[Candidate]:
    """GP-228 — surface portfolio-level work for the research_director role.

    Scans `org/runtime/substrate_portfolio.yaml` and proposes:
      (a) scaffold any registry member with `scaffolded: false`
      (b) rotate-eigenquestion for members where the cross-substrate
          ledger shows the substrate's recent runs anchored in one class
      (c) run-portfolio when no member has run in the active window

    Fires for the self_recursive_orchestrator (primary consumer; per
    GP-228 + the SRO mandate's 5 triggers), the research_director
    (cross-substrate findings consumer), and the principal (override).
    """
    if assigned_to:
        if not (
            assigned_to.endswith("self_recursive_orchestrator")
            or assigned_to.endswith("research_director")
            or assigned_to.endswith("principal")
        ):
            return []

    registry_path = ORG_ROOT_DIR / "runtime" / "substrate_portfolio.yaml"
    if not registry_path.exists():
        return []

    try:
        import yaml
        members = (yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}).get("members") or []
    except Exception:  # noqa: BLE001
        return []

    out: list[Candidate] = []
    for m in members[:max_per_source]:
        if not m.get("scaffolded"):
            out.append(Candidate(
                source="substrate-portfolio",
                intent=(
                    f"scaffold portfolio member '{m['slug']}' (charter stub + "
                    f"rubric authoring) per GP-228 portfolio registry"
                ),
                origin_path=registry_path,
                scarcity_signal="portfolio member registered but not authored",
                raw_text=f"slug={m['slug']} eigenquestion={m.get('eigenquestion_summary')}",
                severity="info",
                metadata={
                    "slug": m["slug"],
                    "kind": "scaffold",
                    "command": "python -m src.cognitive_firm.research_director.substrate_portfolio scaffold",
                },
            ))

    # Eigenquestion-rotation candidate: any scaffolded substrate whose
    # cross-substrate ledger shows ≥3 recent runs in the same class.
    ledger_path = REPO_ROOT / "analytics" / "queries" / "cross_substrate_explored_classes.jsonl"
    if ledger_path.exists():
        try:
            anchored: dict[str, dict[str, int]] = {}
            for line in ledger_path.read_text(encoding="utf-8").splitlines()[-200:]:
                line = line.strip()
                if not line:
                    continue
                import json as _json
                try:
                    rec = _json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                slug = rec.get("substrate_slug")
                cls = rec.get("class_name")
                if not slug or not cls:
                    continue
                anchored.setdefault(slug, {}).setdefault(cls, 0)
                anchored[slug][cls] += 1
            for slug, by_class in anchored.items():
                top_cls, top_count = max(by_class.items(), key=lambda kv: kv[1])
                if top_count >= 3:
                    out.append(Candidate(
                        source="substrate-portfolio",
                        intent=(
                            f"rotate eigenquestion for '{slug}' — "
                            f"anchored on class '{top_cls}' across {top_count} runs"
                        ),
                        origin_path=ledger_path,
                        scarcity_signal=f"family-attractor: {top_count}× '{top_cls}'",
                        raw_text=f"slug={slug} top_class={top_cls} count={top_count}",
                        severity="warn",
                        metadata={
                            "slug": slug,
                            "kind": "rotate-eigenquestion",
                            "command": (
                                f"python -m src.cognitive_firm.research_director."
                                f"eigenquestion_generator --project {slug}"
                            ),
                        },
                    ))
        except Exception:  # noqa: BLE001
            pass

    return out


def discover_relevant_learning_events(
    *,
    assigned_to: Optional[str] = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    cue: str | None = None,
    max_per_source: int = 5,
    log_path: Path | None = None,
) -> list[Candidate]:
    """Surface active approved learning events for a future work surface.

    Learning events are not tasks by themselves. They are decision context that
    future work must encounter before repeating a known failure mode or routing
    pattern.
    """
    if not assigned_to:
        return []

    try:
        from cognitive_firm.orchestration.learning_events import replay_learning_events

        events = replay_learning_events(
            role=assigned_to,
            tenant_id=tenant_id,
            project_id=project_id,
            cue=cue,
            log_path=log_path,
        )
    except Exception:  # noqa: BLE001
        return []

    out: list[Candidate] = []
    for event in events[:max_per_source]:
        out.append(Candidate(
            source="learning-event-replay",
            intent=(
                f"apply approved learning before future work: "
                f"{event.future_application_cue}"
            )[:240],
            origin_path=None,
            scarcity_signal="active approved learning event matched this role/context",
            raw_text=event.decision_use,
            severity="info",
            metadata={
                "learning_event_id": event.learning_event_id,
                "learning_unit_kind": event.learning_unit_kind,
                "owner_role": event.owner_role,
                "tenant_id": event.tenant_id,
                "project_id": event.project_id,
                "approval_ref": event.approval_ref,
                "source_carrier_refs": event.source_carrier_refs,
                "kind": "learning-event-replay",
            },
        ))
    return out


def attach_learning_context(
    candidate: Candidate,
    *,
    assigned_to: Optional[str],
    tenant_id: str | None = None,
    project_id: str | None = None,
    record_encounter: bool = False,
    learning_events_log_path: Path | None = None,
) -> Candidate:
    """Attach approved learning events that match a discovered work item."""
    if not assigned_to or candidate.source == "learning-event-replay":
        return candidate
    candidate_tenant_id = tenant_id or candidate.metadata.get("tenant_id")
    candidate_project_id = project_id or candidate.metadata.get("project_id")
    cue = " ".join(
        part
        for part in [
            candidate.intent,
            candidate.raw_text,
            candidate.scarcity_signal,
        ]
        if part
    ).strip()
    if not cue:
        return candidate
    try:
        from cognitive_firm.orchestration.learning_events import (
            record_learning_event_encounter,
            replay_learning_events,
        )

        events = replay_learning_events(
            role=assigned_to,
            tenant_id=candidate_tenant_id,
            project_id=candidate_project_id,
            cue=cue,
            log_path=learning_events_log_path,
        )
    except Exception:  # noqa: BLE001
        return candidate
    if not events:
        return candidate
    refs = [event.learning_event_id for event in events]
    if record_encounter:
        work_ref = _candidate_work_ref(candidate)
        for event in events:
            try:
                record_learning_event_encounter(
                    learning_event_id=event.learning_event_id,
                    role=assigned_to,
                    cue=cue[:500],
                    outcome="encountered",
                    work_ref=work_ref,
                    tenant_id=candidate_tenant_id,
                    project_id=candidate_project_id,
                    evidence_refs=[candidate.source],
                    metadata={"candidate_source": candidate.source},
                )
            except Exception:  # noqa: BLE001
                continue
    next_metadata = dict(candidate.metadata)
    next_metadata["learning_event_refs"] = refs
    next_metadata["learning_event_context"] = [
        {
            "learning_event_id": event.learning_event_id,
            "decision_use": event.decision_use,
            "future_application_cue": event.future_application_cue,
            "approval_ref": event.approval_ref,
        }
        for event in events
    ]
    return Candidate(
        source=candidate.source,
        intent=candidate.intent,
        origin_path=candidate.origin_path,
        scarcity_signal=candidate.scarcity_signal,
        raw_text=candidate.raw_text,
        age_days=candidate.age_days,
        severity=candidate.severity,
        metadata=next_metadata,
    )


def _candidate_work_ref(candidate: Candidate) -> str:
    if candidate.origin_path:
        return str(candidate.origin_path)
    for key, prefix in [
        ("gap_id", "evidence-gap"),
        ("session_id", "human-work"),
        ("goal_id", "principal-goal"),
        ("message_id", "agent-channel"),
        ("resolved_gate_id", "resolved-gate"),
        ("learning_event_id", "learning-event"),
    ]:
        value = candidate.metadata.get(key)
        if value:
            return f"{prefix}:{value}"
    return candidate.source


def _is_in_role_scope(candidate: Candidate, assigned_to: Optional[str]) -> bool:
    """GP-228 / SRO scope filter — keep candidates that match the role's mandate.

    For self_recursive_orchestrator, only recursive-organization-review work passes. For
    other roles, falls through (no filtering — the role's existing logic owns
    its scope). Role-scope mandates live in tenants/<id>/mandates/; this
    function encodes the predicate for the SRO mandate's "OUT-OF-SCOPE
    EXAMPLES" section without requiring the daemon to load the mandate text.
    """
    if not assigned_to or not assigned_to.endswith("self_recursive_orchestrator"):
        return True

    # SRO scope predicates (any one passes):
    # 1. GP-228 portfolio source — scoped by construction
    if candidate.source == "substrate-portfolio":
        return True
    # 2. Principal goals explicitly assigned to this role — explicit
    #    assignment beats text-match heuristic
    if candidate.source == "principal-goal":
        return True
    # 3. Agent-channel messages addressed to this role
    if candidate.source == "agent-channel":
        return True
    # 4. Resolved-pending-execution gates — owner field is checked at source
    if candidate.source == "resolved-pending-execution":
        return True
    # 4. Damage signals emitted by SRO-related components
    if candidate.source == "damage-scan":
        text = (candidate.intent or "").lower() + " " + (candidate.raw_text or "").lower()
        if "recursive org" in text or "self_recursive_orchestrator" in text or "sro" in text:
            return True
    # 5. Text corpus mentions recursive organization review (TODO-scan + others)
    text_corpus = " ".join((
        candidate.intent or "",
        candidate.scarcity_signal or "",
        str(candidate.origin_path or ""),
        candidate.raw_text or "",
    )).lower()
    if "recursive org" in text_corpus or "recursive organization" in text_corpus:
        return True
    return False


def discover_all(
    *,
    max_per_source: int = 10,
    assigned_to: Optional[str] = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    cue: str | None = None,
    record_learning_encounters: bool = False,
    learning_events_log_path: Path | None = None,
) -> list[Candidate]:
    """Run all implemented discovery sources and return combined list.

    Ordering: critical damage/evidence signals first, then approved gates,
    explicit principal goals, agent-channel obligations, human work, ordinary
    gaps, non-critical damage, TODO-scan, and portfolio work. The ranker
    downstream decides which to propose; this function keeps host damage and
    blocking learning carriers ahead of routine work.

    Role-scope filtering: candidates outside the calling role's mandate
    are dropped via `_is_in_role_scope`. For self_recursive_orchestrator,
    only recursive-organization-review work passes; for other roles, no filter applied.
    """
    out: list[Candidate] = []
    damage_candidates = discover_damage_signals(max_per_source=max_per_source)
    out.extend([c for c in damage_candidates if c.severity == "critical"])
    evidence_candidates = discover_evidence_gaps(
        assigned_to=assigned_to, max_per_source=max_per_source)
    out.extend([c for c in evidence_candidates if c.severity == "critical"])
    # Resolved-but-unexecuted approved gates rank ABOVE most other sources
    # because the principal already approved them.
    out.extend(discover_resolved_pending_execution(
        assigned_to=assigned_to, max_per_source=max_per_source))
    out.extend(discover_principal_goals(
        assigned_to=assigned_to, max_per_source=max_per_source))
    out.extend(discover_agent_channel_messages(
        assigned_to=assigned_to, max_per_source=max_per_source))
    if cue:
        out.extend(discover_relevant_learning_events(
            assigned_to=assigned_to,
            tenant_id=tenant_id,
            project_id=project_id,
            cue=cue,
            max_per_source=max_per_source,
            log_path=learning_events_log_path,
        ))
    out.extend(discover_human_work_sessions(
        assigned_to=assigned_to, max_per_source=max_per_source))
    out.extend([c for c in evidence_candidates if c.severity != "critical"])
    out.extend([c for c in damage_candidates if c.severity != "critical"])
    out.extend(discover_open_todos(max_per_source=max_per_source))
    out.extend(discover_substrate_portfolio_opportunities(
        assigned_to=assigned_to, max_per_source=max_per_source))
    # GP-195 — debate-runner role surfaces stagnant seams as work
    if assigned_to in (None, "debate_runner"):
        out.extend(discover_open_debates(
            assigned_to=assigned_to or "debate_runner", max_per_source=max_per_source))

    # Apply per-role scope filter (SRO is the only role with a tight scope today)
    scoped = [c for c in out if _is_in_role_scope(c, assigned_to)]
    return [
        attach_learning_context(
            c,
            assigned_to=assigned_to,
            tenant_id=tenant_id,
            project_id=project_id,
            record_encounter=record_learning_encounters,
            learning_events_log_path=learning_events_log_path,
        )
        for c in scoped
    ]


def build_role_learning_context(
    *,
    assigned_to: str | None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    cue: str | None = None,
    max_per_source: int = 5,
    include_work_candidates: bool = True,
    learning_events_log_path: Path | None = None,
    outcome_links_log_path: Path | None = None,
    routine_reviews_log_path: Path | None = None,
) -> dict[str, Any]:
    """Build a read-only pre-work context projection for one role surface.

    This composes existing primitives. It does not create memory, mutate
    learning-event state, or record encounter telemetry.
    """
    from cognitive_firm.orchestration.learning_events import replay_learning_events
    from cognitive_firm.orchestration.outcome_links import list_outcome_links
    from cognitive_firm.orchestration.routine_reviews import list_routine_reviews

    events = (
        replay_learning_events(
            role=assigned_to,
            tenant_id=tenant_id,
            project_id=project_id,
            cue=cue,
            log_path=learning_events_log_path,
        )
        if assigned_to
        else []
    )
    learning_context: list[dict[str, Any]] = []
    for event in events[:max_per_source]:
        links = list_outcome_links(
            learning_event_id=event.learning_event_id,
            tenant_id=tenant_id,
            project_id=project_id,
            log_path=outcome_links_log_path,
        )
        reviews = list_routine_reviews(
            learning_event_id=event.learning_event_id,
            tenant_id=tenant_id,
            project_id=project_id,
            log_path=routine_reviews_log_path,
        )
        learning_context.append({
            "learning_event": event.as_dict(),
            "outcome_links": [link.as_dict() for link in links],
            "routine_reviews": [review.as_dict() for review in reviews],
            "overdue_review_ids": [
                review.review_id for review in reviews if review.is_overdue()
            ],
            "source_carrier_refs": list(event.source_carrier_refs),
            "approval_ref": event.approval_ref,
        })

    work_candidates = (
        discover_all(
            assigned_to=assigned_to,
            tenant_id=tenant_id,
            project_id=project_id,
            cue=cue,
            max_per_source=max_per_source,
            record_learning_encounters=False,
            learning_events_log_path=learning_events_log_path,
        )
        if include_work_candidates
        else []
    )
    packet_basis = {
        "assigned_to": assigned_to,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "cue": cue,
        "learning_event_ids": [
            row["learning_event"]["learning_event_id"] for row in learning_context
        ],
        "outcome_link_ids": [
            link["outcome_link_id"]
            for row in learning_context
            for link in row["outcome_links"]
        ],
        "routine_review_ids": [
            review["review_id"]
            for row in learning_context
            for review in row["routine_reviews"]
        ],
        "overdue_review_ids": [
            review_id
            for row in learning_context
            for review_id in row["overdue_review_ids"]
        ],
        "work_candidate_refs": [_candidate_work_ref(candidate) for candidate in work_candidates],
    }
    packet_digest = hashlib.sha256(
        json.dumps(packet_basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "assigned_to": assigned_to,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "cue": cue,
        "read_only": True,
        "context_packet": {
            "context_packet_id": f"ctx_{packet_digest[:16]}",
            "digest": packet_digest,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "basis": packet_basis,
            "write_policy": "projection_only",
            "canonical_store": None,
        },
        "learning_context": learning_context,
        "work_candidates": [candidate_as_dict(candidate) for candidate in work_candidates],
        "consumer_contract": {
            "read_only": True,
            "encounter_route": "POST /kernel/learning-event-encounters",
            "encounter_when": (
                "Record an encounter only after this context influenced a concrete "
                "work surface or role decision."
            ),
            "no_auto_application": True,
        },
    }


def format_candidate_for_inbox(c: Candidate) -> str:
    """Render a candidate as the GP-131 proposal envelope."""
    origin = str(c.origin_path.relative_to(REPO_ROOT)) if c.origin_path else "n/a"
    meta_str = ", ".join(f"{k}={v}" for k, v in c.metadata.items() if v)
    return (
        f"Source:           {c.source}\n"
        f"Intent:           {c.intent}\n"
        f"Candidate action: <propose a bounded next move to the principal>\n"
        f"Origin:           {origin}\n"
        f"Scarcity signal:  {c.scarcity_signal}\n"
        f"Age:              {c.age_days:.2f} days" if c.age_days is not None
        else f"Age:              unknown"
    ) + (f"\nSeverity:         {c.severity}\n"
         f"Metadata:         {meta_str}\n"
         f"Raw excerpt:      {c.raw_text[:300]}")
