from __future__ import annotations

from scripts.release_diff_audit import classify


def test_release_diff_audit_classifies_known_release_surfaces() -> None:
    expected = {
        "src/cognitive_firm/kernel_service.py": "kernel_code",
        "src/cognitive_firm/orchestration/outcome_links.py": "kernel_code",
        "demos/self_evolving_org/run.py": "demo_and_examples",
        "docs/examples/self-evolving-org-demo.md": "demo_and_examples",
        "tests/test_self_evolving_org_demo.py": "demo_and_examples",
        "scripts/release_hygiene_check.py": "release_gates",
        "tests/test_public_claims_check.py": "release_gates",
        "docs/protocols/outcome-links.md": "protocol_docs",
        "README.md": "protocol_docs",
        "org/roles/product_manager.yaml": "org_examples",
        "scripts/kernel_service_smoke.py": "operator_scripts",
        "tests/test_outcome_links.py": "tests",
        "schemas/role.v1.schema.json": "public_schemas",
        "orbit/index.html": "orbit_surface",
        "Makefile": "repo_config",
        ".env.example": "repo_config",
        "docs/protocols/README.md": "generated_indexes",
    }

    for path, bucket in expected.items():
        assert classify(path) == bucket


def test_release_diff_audit_leaves_unknown_paths_visible() -> None:
    assert classify("notebooks/release-sketch.ipynb") == "unclassified"
