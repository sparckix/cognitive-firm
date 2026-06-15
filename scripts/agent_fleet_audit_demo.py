#!/usr/bin/env python3
"""No-cost agent-fleet audit trail demo.

This fixture models the smallest useful adoption wedge: a local/subscription
agent CLI was invoked by a governed role, and the operator wants one packet
showing command shape, prompt/output digests, run identity, authority snapshot,
and provenance. It does not call a model, API, subscription runtime, network,
or external service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request
from cognitive_firm.orchestration.agent_runtime_invocation import (
    build_agent_invocation_receipt,
)
from cognitive_firm.orchestration.governed_run_recipes import (
    GovernedRunOperatorSummaryInput,
    build_governed_run_operator_summary,
    render_governed_run_operator_summary_markdown,
)


COGNITIVE_FIRM_DAEMON_RUNTIME = "cognitive_firm_daemon"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a no-cost agent-fleet audit trail demo.",
    )
    parser.add_argument(
        "--full-json",
        action="store_true",
        help="Print the full audit packet instead of the compact summary.",
    )
    parser.add_argument(
        "--output-dir",
        help=(
            "Optional directory for persistent runbook artifacts. "
            "Use a gitignored path such as .cognitive-firm-runs/agent-fleet-audit."
        ),
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="cf-agent-fleet-audit-") as raw:
        root = Path(raw)
        config = KernelServiceConfig(
            transition_log=root / "transitions.jsonl",
            action_attestation_log=root / "action_attestations.jsonl",
        )
        actor_context = {
            "actor_id": "role.manager",
            "actor_kind": "service",
            "role_id": "role.manager",
            "tenant_id": "tenant-demo",
            "project_id": "project-agent-fleet-audit",
            "surface": "agent_fleet_audit_demo",
        }

        prompt = (
            "You are role.manager. Inspect the launch checklist and report "
            "whether the outgoing update can be sent under the current mandate."
        )
        stdout = (
            '{"decision": "hold", "reason": "human receipt missing"}\n'
            "session id: claude-demo-session\n"
        )
        invocation_receipt = build_agent_invocation_receipt(
            command_argv=["claude", "--print", "--permission-mode", "acceptEdits", prompt],
            prompt=prompt,
            runtime="claude",
            adapter="claude_print",
            prompt_transport="argv",
            returncode=0,
            stdout=stdout,
            stderr="",
            prompt_mode="compact",
        )
        receipt_digest = _digest_text(json.dumps(invocation_receipt, sort_keys=True))
        receipt_ref = f"agent_invocation_receipt:{receipt_digest.split(':', 1)[1][:16]}"

        started = dispatch_kernel_request(
            "POST",
            "/kernel/runs",
            {
                "owner_role": "role.manager",
                "objective": "audit one local agent invocation under role authority",
                "tenant_id": "tenant-demo",
                "project_id": "project-agent-fleet-audit",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(started.status, 201, "agent-fleet run start")
        run_id = started.payload["run"]["run_id"]

        checkpoint = dispatch_kernel_request(
            "POST",
            f"/kernel/runs/{run_id}/checkpoints",
            {
                "actor": "role.manager",
                "step_id": "dispatch_agent_cli",
                "status": "completed",
                "summary": "spawned local agent CLI and captured invocation receipt",
                "payload_ref": receipt_ref,
                "side_effect_key": "agent_cli:claude:agent-fleet-audit-demo",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(checkpoint.status, 201, "agent-fleet checkpoint")
        attestation_response = dispatch_kernel_request(
            "POST",
            "/kernel/action-attestations",
            {
                "subject_kind": "runtime_event",
                "subject_ref": receipt_ref,
                "subject_digest": receipt_digest,
                "producer": "role.manager",
                "action_type": "agent_cli_dispatch",
                "runtime_ref": f"{COGNITIVE_FIRM_DAEMON_RUNTIME}:agent-fleet-audit-demo",
                "tool_ref": "agent_cli:claude",
                "policy_ref": "org/mandates/manager_mandate.md",
                "input_refs": [f"prompt:{invocation_receipt['prompt_digest']}"],
                "output_refs": [f"stdout:{invocation_receipt['stdout_digest']}"],
                "verification_status": "verified",
                "verification_summary": (
                    "fixture invocation receipt digest and command redaction checked"
                ),
                "tenant_id": "tenant-demo",
                "project_id": "project-agent-fleet-audit",
                "run_id": run_id,
                "metadata": {
                    "agent_invocation_receipt": invocation_receipt,
                    "receipt_ref": receipt_ref,
                },
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(attestation_response.status, 201, "agent-fleet action attestation")
        attestation = attestation_response.payload["action_attestation"]

        completed = dispatch_kernel_request(
            "POST",
            f"/kernel/runs/{run_id}/state",
            {
                "actor": "role.manager",
                "state": "completed",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(completed.status, 200, "agent-fleet run complete")

        bundle_response = dispatch_kernel_request(
            "POST",
            "/kernel/governed-run-bundles/build",
            {"run_id": run_id, "actor_context": actor_context},
            config=config,
        )
        _assert_status(bundle_response.status, 200, "agent-fleet bundle build")
        bundle = bundle_response.payload["bundle"]
        validation = bundle_response.payload["validation"]
        validation_errors = validation["errors"]
        summary = bundle_response.payload["summary"]
        runbook_paths = _write_operator_runbook(
            output_dir=Path(args.output_dir) if args.output_dir else None,
            run_id=run_id,
            summary=summary,
            bundle=bundle,
            invocation_receipt=invocation_receipt,
            receipt_ref=receipt_ref,
        )
        payload = (
            {
                "agent_invocation_receipt": invocation_receipt,
                "action_attestation": attestation,
                "governed_run_attestation": bundle,
                "bundle_validation": {
                    "ok": validation["ok"],
                    "errors": validation_errors,
                },
                "operator_runbook": runbook_paths,
            }
            if args.full_json
            else {
                "demo": "agent_fleet_audit_trail",
                "no_external_calls": True,
                "summary": summary,
                "bundle_validation": {
                    "ok": validation["ok"],
                    "errors": validation_errors,
                },
                "agent_invocation": {
                    "runtime": invocation_receipt["runtime"],
                    "adapter": invocation_receipt["adapter"],
                    "schema_version": invocation_receipt["schema_version"],
                    "prompt_transport": invocation_receipt["prompt_transport"],
                    "returncode": invocation_receipt["returncode"],
                    "agent_session_id": invocation_receipt.get("agent_session_id"),
                    "receipt_ref": receipt_ref,
                },
                "operator_runbook": runbook_paths,
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _assert_status(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label} returned {actual}, expected {expected}")


def _digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_operator_runbook(
    *,
    output_dir: Path | None,
    run_id: str,
    summary: dict,
    bundle: dict,
    invocation_receipt: dict,
    receipt_ref: str,
) -> dict:
    if output_dir is None:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    full_packet_path = output_dir / "agent-fleet-audit-packet.json"
    runbook_json_path = output_dir / "agent-fleet-audit-runbook.json"
    runbook_md_path = output_dir / "agent-fleet-audit-runbook.md"

    full_packet_path.write_text(
        json.dumps(
            {
                "agent_invocation_receipt": invocation_receipt,
                "governed_run_attestation": bundle,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    operator_summary = build_governed_run_operator_summary(
        GovernedRunOperatorSummaryInput(
            run_label="agent_fleet_audit",
            run_ref=f"run:{run_id}",
            summary={
                "verdict": summary.get("verdict"),
                "termination_reason": "completed",
                "run_state": summary.get("run_state"),
                "owner_role": summary.get("owner_role"),
                "budget_units_consumed": 1,
                "budget_units_remaining": 0,
            },
            artifacts=[
                {
                    "label": "agent invocation receipt",
                    "ref": receipt_ref,
                    "purpose": "Runtime, adapter, redacted command, prompt/output digests, and session id.",
                },
                {
                    "label": "audit packet",
                    "ref": str(full_packet_path),
                    "purpose": "Full receipt and governed-run attestation bundle for local inspection.",
                },
            ],
            commands=[
                {
                    "label": "rerun no-cost audit",
                    "command": "make agent-fleet-audit-demo",
                },
                {
                    "label": "write persistent runbook",
                    "command": (
                        "PYTHONPATH=src python scripts/agent_fleet_audit_demo.py "
                        "--output-dir .cognitive-firm-runs/agent-fleet-audit"
                    ),
                },
            ],
            inspection_order=[
                "agent invocation receipt",
                "audit packet",
                "governed-run attestation bundle",
            ],
            bundle_summaries=[summary],
            metadata={
                "demo": "agent_fleet_audit_trail",
                "no_external_calls": True,
                "runtime": invocation_receipt.get("runtime"),
                "adapter": invocation_receipt.get("adapter"),
                "receipt_ref": receipt_ref,
            },
        )
    )
    runbook_json_path.write_text(
        json.dumps(operator_summary, indent=2, sort_keys=True) + "\n"
    )
    runbook_md_path.write_text(
        render_governed_run_operator_summary_markdown(operator_summary) + "\n"
    )
    return {
        "json": str(runbook_json_path),
        "markdown": str(runbook_md_path),
        "packet": str(full_packet_path),
    }


if __name__ == "__main__":
    raise SystemExit(main())
