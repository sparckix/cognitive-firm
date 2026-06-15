from __future__ import annotations

from scripts.release_hygiene_check import (
    private_tracked_reason,
    untracked_sensitive_reason,
)


def test_release_hygiene_rejects_private_or_generated_tracked_paths():
    rejected = {
        ".env": "environment files",
        ".env.local": "environment files",
        "internal/handover.md": "internal strategy",
        ".cognitive-firm-runs/demo/report.json": "generated demo",
        "cognitive_firm_workspace/transitions.jsonl": "local runtime",
        "local_runtime_workspace/transitions.jsonl": "local runtime",
        "org/sessions/current.json": "session state",
        "org/preferences/principal.yaml": "principal preferences",
        "org/signals/damage/dsig_001.json": "damage signal",
        "org/tasks/active/task.json": "live objectives",
        "tenants/acme/preferences/principal.yaml": "tenants/example",
    }
    for path, expected_fragment in rejected.items():
        reason = private_tracked_reason(path)
        assert reason is not None, path
        assert expected_fragment in reason


def test_release_hygiene_allows_public_templates_and_examples():
    allowed = [
        ".env.example",
        "org/preferences/templates/principal.yaml",
        "org/roles/principal.yaml",
        "tenants/README.md",
        "tenants/example/preferences/principal.yaml",
        "tenants/example/projects/demo/project_charter.md",
    ]
    for path in allowed:
        assert private_tracked_reason(path) is None, path


def test_release_hygiene_flags_sensitive_unignored_paths():
    rejected = [
        "answer_key.json",
        "operator-only/workload-probes/IN-01.scorecard.json",
        "notes/API_TOKEN.txt",
        "tenant-secret.yaml",
        "local.env",
    ]
    for path in rejected:
        assert untracked_sensitive_reason(path) is not None, path

    assert untracked_sensitive_reason("docs/examples/self-evolving-org-demo.md") is None
