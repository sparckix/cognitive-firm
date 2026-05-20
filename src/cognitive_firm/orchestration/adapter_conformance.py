"""Small conformance helpers for integration adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ConformanceCheck:
    check_id: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterConformanceReport:
    adapter_id: str
    family: str
    checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "family": self.family,
            "ok": self.ok,
            "checks": [check.as_dict() for check in self.checks],
        }


def run_adapter_conformance(
    *,
    adapter_id: str,
    family: str,
    checks: dict[str, Callable[[], bool]],
) -> AdapterConformanceReport:
    results: list[ConformanceCheck] = []
    for check_id, check in checks.items():
        try:
            passed = bool(check())
        except Exception as exc:  # pragma: no cover - exercised by callers
            results.append(ConformanceCheck(check_id=check_id, passed=False, detail=str(exc)))
        else:
            results.append(ConformanceCheck(check_id=check_id, passed=passed))
    return AdapterConformanceReport(adapter_id=adapter_id, family=family, checks=results)
