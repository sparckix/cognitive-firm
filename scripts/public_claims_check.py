#!/usr/bin/env python3
"""Check public docs for release-claim discipline.

This is not a style linter. It protects a narrow trust boundary: public docs
should not imply production certification, enterprise readiness, legal
non-repudiation, or guaranteed security beyond the shipped T1/T2 seams.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DOC_ROOTS = ("README.md", "docs")

FORBIDDEN_PHRASES = {
    "production-ready": "do not claim production readiness without deployment evidence",
    "production ready": "do not claim production readiness without deployment evidence",
    "enterprise-ready": "do not claim enterprise readiness without deployment evidence",
    "enterprise ready": "do not claim enterprise readiness without deployment evidence",
    "compliance-certified": "do not claim certification",
    "compliance certified": "do not claim certification",
    "legally non-repudiable": "do not claim legal non-repudiation",
    "secure by default": "do not claim a complete security posture",
    "fully secure": "do not claim a complete security posture",
    "guaranteed": "avoid guarantee language in public kernel claims",
}

REQUIRED_CAVEATS = {
    "README.md": (
        "Full enterprise IAM administration",
        "production compliance certification",
    ),
    "docs/ROADMAP.md": (
        "legal non-repudiation",
        "production compliance certification",
        "multi-tenant isolation across separate authority domains",
    ),
    "docs/protocols/audit-integrity.md": (
        "does not provide key",
        "legal non-repudiation",
    ),
    "docs/t1_t2_upgrade_matrix.md": (
        "This is not a complete regulated-enterprise deployment",
    ),
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    phrase: str
    reason: str
    text: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "phrase": self.phrase,
            "reason": self.reason,
            "text": self.text,
        }


def public_markdown_files() -> list[Path]:
    files = [ROOT / "README.md"]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    return [path for path in files if path.is_file()]


def find_forbidden_phrases(text: str, *, relpath: str) -> list[Finding]:
    findings: list[Finding] = []
    for index, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        for phrase, reason in FORBIDDEN_PHRASES.items():
            if phrase in lowered:
                findings.append(
                    Finding(
                        path=relpath,
                        line=index,
                        phrase=phrase,
                        reason=reason,
                        text=line.strip(),
                    )
                )
    return findings


def missing_required_caveats() -> list[dict[str, object]]:
    missing: list[dict[str, object]] = []
    for relpath, snippets in REQUIRED_CAVEATS.items():
        path = ROOT / relpath
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        lowered = text.lower()
        for snippet in snippets:
            if snippet.lower() not in lowered:
                missing.append(
                    {
                        "path": relpath,
                        "required_snippet": snippet,
                        "reason": "required T1/T2 or legal/compliance caveat is missing",
                    }
                )
    return missing


def main() -> int:
    findings: list[Finding] = []
    for path in public_markdown_files():
        relpath = path.relative_to(ROOT).as_posix()
        findings.extend(
            find_forbidden_phrases(path.read_text(encoding="utf-8"), relpath=relpath)
        )
    missing = missing_required_caveats()
    payload = {
        "ok": not findings and not missing,
        "forbidden_claims": [finding.as_dict() for finding in findings],
        "missing_caveats": missing,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
