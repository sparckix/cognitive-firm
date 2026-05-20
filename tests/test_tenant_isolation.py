from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.actor_identity import ActorContext  # noqa: E402
from cognitive_firm.orchestration.tenant_isolation import (  # noqa: E402
    tenant_overlay_root,
    validate_tenant_ref,
)


def test_tenant_isolation_rejects_cross_tenant_actor_and_path_escape(tmp_path: Path):
    boundary = tenant_overlay_root(tmp_path, "tenant-a")
    boundary.root.mkdir(parents=True)
    inside = boundary.root / "roles" / "manager.yaml"
    inside.parent.mkdir()
    inside.write_text("role_id: manager\n", encoding="utf-8")
    outside = tmp_path / "tenant-b" / "roles" / "manager.yaml"

    actor = ActorContext(actor_id="human.alice", actor_kind="human", tenant_id="tenant-a")
    validate_tenant_ref(actor=actor, tenant_id="tenant-a", path=inside, boundary=boundary)

    with pytest.raises(PermissionError, match="cannot access tenant"):
        validate_tenant_ref(actor=actor, tenant_id="tenant-b", path=inside, boundary=boundary)

    with pytest.raises(PermissionError, match="escapes tenant boundary"):
        validate_tenant_ref(actor=actor, tenant_id="tenant-a", path=outside, boundary=boundary)


def test_tenant_overlay_root_requires_simple_identifier(tmp_path: Path):
    with pytest.raises(ValueError, match="simple relative identifier"):
        tenant_overlay_root(tmp_path, "../tenant-a")
