"""Tests for the userland kernel-service routes: L1 attention, L4 vocabulary."""

from __future__ import annotations

from cognitive_firm.kernel_service import (
    KernelServiceConfig,
    dispatch_kernel_request,
)
from cognitive_firm.orchestration.human_work import create_human_work_session


def test_vocabulary_route_serves_the_glossary():
    resp = dispatch_kernel_request("GET", "/kernel/vocabulary")
    assert resp.status == 200
    assert resp.payload["schema_version"] == 1
    assert any(term["key"] == "gate" for term in resp.payload["terms"])


def test_attention_route_is_empty_for_a_quiet_org(tmp_path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "hw.jsonl",
        gates_dir=tmp_path / "gates",
        org_dir=tmp_path,
        actor_membership_log=tmp_path / "m.jsonl",
    )
    resp = dispatch_kernel_request(
        "GET", "/kernel/attention/alice", config=config
    )
    assert resp.status == 200
    assert resp.payload["actor_id"] == "alice"
    assert resp.payload["signals"] == []


def test_attention_route_routes_a2h_work_to_the_member_human(tmp_path):
    human_work = tmp_path / "hw.jsonl"
    create_human_work_session(
        requested_by="research_office",
        human_actor="alice",
        objective="review the draft",
        work_mode="edit",
        bottleneck_class="taste",
        agent_followup_required=True,
        log_path=human_work,
    )
    config = KernelServiceConfig(
        human_work_log=human_work,
        gates_dir=tmp_path / "gates",
        org_dir=tmp_path,
        actor_membership_log=tmp_path / "m.jsonl",
    )
    resp = dispatch_kernel_request(
        "GET", "/kernel/attention/alice", config=config
    )
    assert resp.status == 200
    signals = resp.payload["signals"]
    assert len(signals) == 1
    assert signals[0]["signal_class"] == "work_interrupt"
    assert signals[0]["target_actor_id"] == "alice"

    # a different participant's feed does not see Alice's work
    other = dispatch_kernel_request(
        "GET", "/kernel/attention/bob", config=config
    )
    assert other.payload["signals"] == []


def test_work_inbox_route_lists_a_member_humans_tasks(tmp_path):
    human_work = tmp_path / "hw.jsonl"
    create_human_work_session(
        requested_by="research_office",
        human_actor="alice",
        objective="review the draft",
        work_mode="edit",
        bottleneck_class="taste",
        log_path=human_work,
    )
    config = KernelServiceConfig(human_work_log=human_work)
    resp = dispatch_kernel_request(
        "GET", "/kernel/work-inbox/alice", config=config
    )
    assert resp.status == 200
    assert resp.payload["actor_id"] == "alice"
    assert len(resp.payload["items"]) == 1
    assert resp.payload["items"][0]["objective"] == "review the draft"


def test_surface_policy_blocks_a_projection_only_surface(tmp_path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "hw.jsonl",
        surface_write_modes={"orbit": "projection_only"},
    )
    resp = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        body={"actor_context": {"surface": "orbit"}},
        config=config,
    )
    assert resp.status == 409


def test_surface_policy_allows_an_unrestricted_surface(tmp_path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "hw.jsonl",
        surface_write_modes={"orbit": "projection_only"},
    )
    # 'cli' is not projection-only; the guard lets it through (the request may
    # still fail downstream for an unrelated reason, but not with a 409).
    resp = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        body={"actor_context": {"surface": "cli"}},
        config=config,
    )
    assert resp.status != 409
