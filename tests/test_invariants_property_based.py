"""Property-based tests for the M-Form core invariants.

These tests cover dispatch authorization edge cases where examples alone are
too narrow: forbidden path precedence, explicit unattended scopes, budget
caps, wildcard behavior, idempotency, and projection registration.

Invariants under test (the 5-7 named in the verdict file):

  I1. Forbidden-paths-take-precedence: if a path matches any
      forbidden_paths pattern, authorize_dispatch returns allowed=False
      regardless of authorized_paths.

  I2. Authorized-paths-required-for-unattended: if unattended=True and
      authorized_paths is non-empty without "*", a path that matches NO
      authorized pattern returns allowed=False.

  I3. Budget-caps-fail-closed: if estimated_cost_usd > single_action_cap_usd,
      authorize_dispatch returns allowed=False with required_approval="principal".

  I4. Wildcard-pattern-matches-all: pattern "*" in authorized_paths
      authorizes any path (this is the well-known kernel-bypass case
      principals must consciously enable).

  I5. Idempotency-of-decision: authorize_dispatch is a pure function of
      (role config, candidate args). Two calls with identical inputs
      produce identical outputs.

  I6. No-LLM-at-projection: project_response on an unregistered (server,
      tool) returns mcp_call_failed with a rejection reason, never an
      mcp_call_dispatched. (Confirms T2's no-learned-parameter invariant
      at the M-Form enforcement floor.)

  I7. Idempotency-key-determinism: same causality_id + same request
      payload always produces the same idempotency key.

Each property is asserted across ~100 randomized inputs by Hypothesis.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.task_authorization import (  # noqa: E402
    AuthorizationDecision,
    _path_matches,
    authorize_dispatch,
)
from cognitive_firm.role_extensions.mcp_bridge import (  # noqa: E402
    project_response,
    register_projection,
    ProjectionResult,
)
from cognitive_firm.role_extensions.mcp_bridge.outbox_relay import (  # noqa: E402
    _idempotency_key,
)


# ── strategies ─────────────────────────────────────────────────────────


# Filesystem-style path components: alphanumeric + underscore + slash.
# Avoid dot to keep it cleaner; avoid asterisk to not collide with patterns.
_path_segment = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_",
    min_size=1,
    max_size=8,
)


@st.composite
def fs_path(draw):
    """A relative path of 1-4 segments, e.g. 'foo/bar/baz'."""
    n = draw(st.integers(min_value=1, max_value=4))
    parts = [draw(_path_segment) for _ in range(n)]
    return "/".join(parts)


@st.composite
def role_with_paths(draw):
    """Role config with random authorized_paths + forbidden_paths."""
    auth = draw(st.lists(fs_path(), min_size=0, max_size=3))
    forb = draw(st.lists(fs_path(), min_size=0, max_size=2))
    return {
        "authorized_paths": [p + "/" for p in auth],
        "forbidden_paths": [p + "/" for p in forb],
        "budget": {"single_action_cap_usd": 5.0},
    }


# ── invariant tests ────────────────────────────────────────────────────


@given(role=role_with_paths(), path=fs_path())
@settings(max_examples=100, deadline=None)
def test_I1_forbidden_paths_take_precedence(role: dict, path: str):
    """I1: if a path matches forbidden_paths, allowed=False regardless of
    authorized_paths."""
    forb_patterns = role["forbidden_paths"]
    if not any(_path_matches(path, p) for p in forb_patterns):
        # path doesn't match any forbidden pattern; this property doesn't apply
        return

    with patch(
        "cognitive_firm.orchestration.task_authorization._load_role",
        return_value=role,
    ):
        decision = authorize_dispatch(
            role_id="x",
            candidate_source="principal-goal",
            candidate_text=f"work on {path}",
            metadata={"declared_paths": [path], "estimated_cost_usd": 0.10, "autonomous_scope_ok": True},
            unattended=True,
        )
    assert not decision.allowed, (
        f"I1 violated: path {path} matched forbidden pattern but was allowed"
    )
    assert "forbidden_paths" in decision.reason


@given(role=role_with_paths(), path=fs_path())
@settings(max_examples=100, deadline=None)
def test_I2_authorized_paths_required_for_unattended(role: dict, path: str):
    """I2: if unattended=True and authorized_paths is non-empty without "*",
    a path matching NO authorized pattern returns allowed=False."""
    auth_patterns = role["authorized_paths"]
    forb_patterns = role["forbidden_paths"]
    # Skip degenerate cases that don't exercise this invariant
    if not auth_patterns or "*" in auth_patterns:
        return
    # Skip if forbidden would catch it first (I1 covers that case)
    if any(_path_matches(path, p) for p in forb_patterns):
        return
    # Skip if path actually matches an authorized pattern
    if any(_path_matches(path, p) for p in auth_patterns):
        return

    with patch(
        "cognitive_firm.orchestration.task_authorization._load_role",
        return_value=role,
    ):
        decision = authorize_dispatch(
            role_id="x",
            candidate_source="principal-goal",
            candidate_text=f"work on {path}",
            metadata={"declared_paths": [path], "estimated_cost_usd": 0.10, "autonomous_scope_ok": True},
            unattended=True,
        )
    assert not decision.allowed, (
        f"I2 violated: path {path} outside authorized_paths but allowed"
    )
    assert "outside role authorized_paths" in decision.reason


@given(
    cap=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    cost=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_I3_budget_caps_fail_closed(cap: float, cost: float):
    """I3: if estimated_cost > single_action_cap, allowed=False with
    required_approval=principal."""
    role = {
        "authorized_paths": ["*"],  # avoid I1/I2 confounds
        "forbidden_paths": [],
        "budget": {"single_action_cap_usd": cap},
    }
    with patch(
        "cognitive_firm.orchestration.task_authorization._load_role",
        return_value=role,
    ):
        decision = authorize_dispatch(
            role_id="x",
            candidate_source="principal-goal",
            candidate_text="work",
            metadata={"declared_paths": ["src/cognitive_firm/x.py"], "estimated_cost_usd": cost, "autonomous_scope_ok": True},
            unattended=True,
        )
    if cost > cap:
        assert not decision.allowed, (
            f"I3 violated: cost {cost} > cap {cap} but allowed"
        )
        assert decision.required_approval == "principal"
        assert "exceeds role single_action_cap_usd" in decision.reason


@given(path=fs_path())
@settings(max_examples=50, deadline=None)
def test_I4_wildcard_pattern_matches_all(path: str):
    """I4: pattern '*' authorizes any path."""
    role = {
        "authorized_paths": ["*"],
        "forbidden_paths": [],
        "budget": {"single_action_cap_usd": 5.0},
    }
    with patch(
        "cognitive_firm.orchestration.task_authorization._load_role",
        return_value=role,
    ):
        decision = authorize_dispatch(
            role_id="x",
            candidate_source="principal-goal",
            candidate_text=f"work on {path}",
            metadata={"declared_paths": [path], "estimated_cost_usd": 0.10, "autonomous_scope_ok": True},
            unattended=True,
        )
    assert decision.allowed, (
        f"I4 violated: '*' should authorize {path} but did not"
    )


@given(role=role_with_paths(), path=fs_path())
@settings(max_examples=50, deadline=None)
def test_I5_decision_idempotency(role: dict, path: str):
    """I5: authorize_dispatch is a pure function. Two calls with identical
    inputs produce identical outputs."""
    args = dict(
        role_id="x",
        candidate_source="open-todo",
        candidate_text=f"work on {path}",
        metadata={"paths": [path], "estimated_cost_usd": 0.10},
        unattended=True,
    )
    with patch(
        "cognitive_firm.orchestration.task_authorization._load_role",
        return_value=role,
    ):
        d1 = authorize_dispatch(**args)
        d2 = authorize_dispatch(**args)
    assert d1.allowed == d2.allowed
    assert d1.reason == d2.reason
    assert d1.required_approval == d2.required_approval


def test_authorize_dispatch_uses_declared_paths_metadata_without_text_path():
    """Typed task frontmatter should drive authorization without prose parsing."""
    role = {
        "authorized_paths": ["org/mandates/"],
        "forbidden_paths": [".env"],
        "budget": {"single_action_cap_usd": 1.0},
    }
    with patch(
        "cognitive_firm.orchestration.task_authorization._load_role",
        return_value=role,
    ):
        decision = authorize_dispatch(
            role_id="org_evolver",
            candidate_source="principal-goal",
            candidate_text="Review the current mandate and report one bounded next improvement.",
            metadata={
                "declared_paths": ["org/mandates/org_evolver_mandate.md"],
                "estimated_cost_usd": 0.0,
                "autonomous_scope_ok": True,
            },
            unattended=True,
        )

    assert decision.allowed is True
    assert decision.matched_paths == ("org/mandates/org_evolver_mandate.md",)


@given(
    server=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12),
    tool=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12),
)
@settings(max_examples=50, deadline=None)
def test_I6_no_llm_at_projection_unregistered_rejects(server: str, tool: str):
    """I6: project_response on an unregistered (server, tool) returns
    mcp_call_failed, never mcp_call_dispatched. Confirms T2's invariant."""
    # Make sure this random pair is genuinely unregistered.
    if server == "linear":
        return  # known registered server name; skip
    proj = project_response(server, tool, {"some": "ambiguous", "data": True})
    assert proj.transition_class == "mcp_call_failed", (
        f"I6 violated: unregistered ({server}/{tool}) projected to "
        f"{proj.transition_class}, expected mcp_call_failed"
    )
    assert proj.rejection_reason and "no projection registered" in proj.rejection_reason


@given(
    causality=st.text(min_size=1, max_size=20),
    request=st.dictionaries(
        keys=st.text(alphabet="abcdef", min_size=1, max_size=4),
        values=st.integers(min_value=-100, max_value=100),
        max_size=5,
    ),
)
@settings(max_examples=100, deadline=None)
def test_I7_idempotency_key_determinism(causality: str, request: dict):
    """I7: same causality_id + same request payload → same idempotency key.
    This is what makes outbox-relay retry safe."""
    k1 = _idempotency_key(causality, request)
    k2 = _idempotency_key(causality, request)
    assert k1 == k2, (
        f"I7 violated: idempotency_key not deterministic; "
        f"{k1[:16]}… vs {k2[:16]}…"
    )
    # And keys should differ for different causality.
    if causality + "_alt" != causality:
        k3 = _idempotency_key(causality + "_alt", request)
        assert k1 != k3, "different causality should produce different key"


# ── meta-invariant: invariants are documented somewhere ────────────────


def test_meta_invariants_documented():
    """The public mandate protocol names the randomized invariant suite."""
    p = ROOT / "docs" / "protocols" / "mandate.md"
    text = p.read_text(encoding="utf-8")
    assert "property-based" in text.lower() or "property tests" in text.lower(), (
        "mandate protocol must name the property-based invariant tests"
    )
