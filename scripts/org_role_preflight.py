#!/usr/bin/env python3
"""Non-mutating preflight for org role runtimes.

This validates that a role daemon can boot against the durable org contracts
without opening a session, consuming directives, or executing work.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - exercised in minimal environments.
    yaml = None

try:
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover - exercised in minimal environments.
    jsonschema = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]
ORG_ROOT = Path(os.environ.get("ORG_ROOT") or REPO_ROOT / "org")
ROLE_SCHEMA_PATH = REPO_ROOT / "schemas" / "role.v1.schema.json"


def _coerce_scalar(value: str) -> Any:
    text = value.strip()
    if not text:
        return {}
    if text in {">", "|"}:
        return text
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """Small YAML subset parser for preflight in bare Python.

    This is intentionally conservative. It supports nested mappings and scalar
    leaves, which is enough for role mandate_path and research_taste axes. Full
    YAML remains handled by PyYAML when available.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.lstrip().startswith("- "):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        parsed = _coerce_scalar(value)
        parent[key.strip()] = parsed
        if isinstance(parsed, dict):
            stack.append((indent, parsed))
    return root


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        data = _minimal_yaml_load(text)
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} did not parse as a YAML mapping")
    return data


def _check_exists(report: dict[str, Any], key: str, path: Path) -> None:
    try:
        rel = str(path.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(path)
    if path.exists():
        report["checks"].append({"key": key, "ok": True, "path": rel})
    else:
        report["checks"].append({"key": key, "ok": False, "path": rel})
        report["errors"].append(f"missing {key}: {rel}")


def preflight(
    role_id: str,
    *,
    require_agent: bool = False,
    agent_cli: str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 1,
        "role_id": role_id,
        "ok": False,
        "checks": [],
        "warnings": [],
        "errors": [],
    }

    role_path = ORG_ROOT / "roles" / f"{role_id}.yaml"
    _check_exists(report, "repo_agent_instructions", REPO_ROOT / "AGENTS.md")
    _check_exists(report, "role_yaml", role_path)
    if not role_path.exists():
        return report

    try:
        role = _load_yaml(role_path)
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"role_yaml_parse_failed: {exc}")
        return report

    _check_exists(report, "role_schema", ROLE_SCHEMA_PATH)
    if ROLE_SCHEMA_PATH.exists():
        if jsonschema is None:
            report["warnings"].append(
                "jsonschema package not installed; skipping schema validation. "
                "Install with: pip install jsonschema"
            )
        else:
            try:
                schema = json.loads(ROLE_SCHEMA_PATH.read_text(encoding="utf-8"))
                jsonschema.validate(role, schema)
                report["checks"].append({"key": "role_schema_validate", "ok": True})
            except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
                report["checks"].append({"key": "role_schema_validate", "ok": False})
                loc = "/".join(str(p) for p in exc.absolute_path) or "(root)"
                report["errors"].append(
                    f"role_schema_validate failed at {loc}: {exc.message}"
                )
            except Exception as exc:  # noqa: BLE001
                report["checks"].append({"key": "role_schema_validate", "ok": False})
                report["errors"].append(f"role_schema_load_failed: {exc}")

    # mandate_path: null is an INTENTIONAL signal that the role is wrapper-invoked
    # or read-only and the role yaml itself is the only authorization contract
    # (see comments in engineer/reviewer/principal yamls). Respect it; do NOT
    # fall through to a guessed default path.
    if "mandate_path" in role and role["mandate_path"] is None:
        report["checks"].append(
            {"key": "mandate", "ok": True, "path": "<null — intentional, see role yaml comment>"}
        )
    else:
        mandate_raw = role.get("mandate_path") or f"org/mandates/{role_id}_mandate.md"
        mandate_path = (
            ORG_ROOT / str(mandate_raw).removeprefix("org/")
            if str(mandate_raw).startswith("org/")
            else REPO_ROOT / str(mandate_raw)
        )
        _check_exists(report, "mandate", mandate_path)
    _check_exists(report, "first_30_minutes", REPO_ROOT / "docs" / "first-30-minutes.md")
    _check_exists(report, "mandate_protocol", REPO_ROOT / "docs" / "protocols" / "mandate.md")
    _check_exists(report, "runtime_adapter_protocol", REPO_ROOT / "docs" / "protocols" / "runtime-adapters.md")

    prefs_path = ORG_ROOT / "preferences" / "principal.yaml"
    _check_exists(report, "principal_preferences", prefs_path)
    if prefs_path.exists():
        try:
            prefs = _load_yaml(prefs_path)
            taste = (prefs.get("research_taste") or {}).get("axes") or {}
            if taste:
                report["checks"].append(
                    {"key": "research_taste_axes", "ok": True, "count": len(taste)}
                )
            else:
                report["checks"].append({"key": "research_taste_axes", "ok": False})
                report["errors"].append("research_taste.axes missing from preferences")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"principal_preferences_parse_failed: {exc}")

    cli_name = (
        agent_cli
        or os.environ.get("COGNITIVE_FIRM_AGENT_CLI")
        or "claude"
    )
    agent_cli_path = shutil.which(cli_name)
    if agent_cli_path:
        report["checks"].append({"key": f"agent_cli:{cli_name}", "ok": True, "path": agent_cli_path})
    else:
        msg = f"agent CLI '{cli_name}' not found; daemon can preflight/dry-run but cannot execute tasks with that runtime"
        report["checks"].append({"key": f"agent_cli:{cli_name}", "ok": False})
        if require_agent:
            report["errors"].append(msg)
        else:
            report["warnings"].append(msg)

    report["ok"] = not report["errors"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight an org role runtime without mutation")
    parser.add_argument("--role", default="research_director")
    parser.add_argument("--require-agent", action="store_true")
    parser.add_argument(
        "--agent-cli",
        default=None,
        help="Agent runtime command to check; defaults to COGNITIVE_FIRM_AGENT_CLI or claude",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = preflight(args.role, require_agent=args.require_agent, agent_cli=args.agent_cli)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        status = "PASS" if report["ok"] else "FAIL"
        print(f"{status} role preflight: {args.role}")
        for check in report["checks"]:
            mark = "ok" if check.get("ok") else "FAIL"
            detail = check.get("path", check.get("count", ""))
            print(f"- {mark}: {check['key']} {detail}")
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
        for error in report["errors"]:
            print(f"ERROR: {error}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
