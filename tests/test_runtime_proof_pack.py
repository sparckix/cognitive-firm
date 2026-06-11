from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_script(name: str):
    script_path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_compact_demo(script_name: str, capsys):
    module = _load_script(script_name)
    assert module.main([]) == 0
    return json.loads(capsys.readouterr().out)


def _assert_governed_run_summary(payload: dict):
    assert payload["bundle_validation"]["ok"] is True

    summary = payload["summary"]
    assert summary["verdict"] == "passed"
    assert summary["run_state"] == "completed"
    assert summary["run_id"].startswith("run_")
    assert summary["owner_role"].startswith("role.")
    assert summary["project_id"]

    counts = summary["counts"]
    assert counts["action_attestations"] >= 1
    assert counts["human_work_sessions"] >= 1
    assert counts["outcome_links"] >= 1
    assert counts["accountability_cases"] >= 1

    ids = summary["ids"]
    assert ids["action_attestations"]
    assert ids["human_work_sessions"]
    assert ids["outcome_links"]
    assert ids["accountability_cases"]
    assert summary["caveats"] == []


def test_runtime_proof_pack_native_and_langgraph_share_bundle_contract(capsys):
    native = _run_compact_demo("native_e2e_demo", capsys)
    langgraph = _run_compact_demo("langgraph_governance_demo", capsys)

    assert native["demo"] == "native_cognitive_firm_e2e"
    assert langgraph["demo"] == "langgraph_governance_projection"
    _assert_governed_run_summary(native)
    _assert_governed_run_summary(langgraph)

    native_summary_keys = set(native["summary"])
    langgraph_summary_keys = set(langgraph["summary"])
    assert native_summary_keys == langgraph_summary_keys
