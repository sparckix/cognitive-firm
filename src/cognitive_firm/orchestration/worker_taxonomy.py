"""Worker taxonomy for cognitive-firm operating units.

The taxonomy separates worker structure from sourcing:

- capability model: bare LLM, tool-using agent, deterministic system, or human;
- fungibility model: fungible or singular identity;
- state model: stateless or stateful;
- transport: API, subscription CLI, local process, human, or external service.

Transport is deliberately orthogonal. Moving a worker from API to subscription
CLI changes cost and capability constraints; it does not by itself turn a
fungible worker into a singular one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


WorkerClass = Literal["deterministic", "llm", "agent", "governance", "operator"]
CapabilityModel = Literal["deterministic_system", "bare_llm", "tool_using_agent", "human"]
StateModel = Literal["stateless", "stateful"]
FungibilityModel = Literal["fungible", "singular"]
TransportModel = Literal["api", "subscription_cli", "local_process", "human", "external_service", "unspecified"]
StateLocation = Literal["external_artifacts", "session_and_artifacts", "human_context_and_artifacts"]

WORKER_CLASSES: tuple[WorkerClass, ...] = (
    "deterministic",
    "llm",
    "agent",
    "governance",
    "operator",
)

TRANSPORTS: tuple[TransportModel, ...] = (
    "api",
    "subscription_cli",
    "local_process",
    "human",
    "external_service",
    "unspecified",
)


@dataclass(frozen=True)
class WorkerArchetype:
    archetype_id: str
    worker_class: WorkerClass
    capability_model: CapabilityModel
    fungibility_model: FungibilityModel
    state_model: StateModel
    state_location: StateLocation
    description: str
    design_rule: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class WorkerDeployment:
    archetype: WorkerArchetype
    transport: TransportModel

    def as_dict(self) -> dict[str, str]:
        return {**self.archetype.as_dict(), "transport": self.transport}


WORKER_ARCHETYPES: tuple[WorkerArchetype, ...] = (
    WorkerArchetype(
        archetype_id="deterministic_gate",
        worker_class="deterministic",
        capability_model="deterministic_system",
        fungibility_model="fungible",
        state_model="stateless",
        state_location="external_artifacts",
        description="Schema checks, replay, filters, digest checks, and deterministic projections.",
        design_rule="Use when the check should be reproducible and independent of worker identity.",
    ),
    WorkerArchetype(
        archetype_id="fungible_llm_call",
        worker_class="llm",
        capability_model="bare_llm",
        fungibility_model="fungible",
        state_model="stateless",
        state_location="external_artifacts",
        description="A bounded model call that proposes, classifies, mutates, or summarizes from supplied context.",
        design_rule="Externalize context in artifacts; do not rely on private session memory.",
    ),
    WorkerArchetype(
        archetype_id="fungible_agent_worker",
        worker_class="agent",
        capability_model="tool_using_agent",
        fungibility_model="fungible",
        state_model="stateless",
        state_location="external_artifacts",
        description="A tool-using/code-executing worker used as interchangeable labor over externalized context.",
        design_rule="Use when action capability is needed but identity continuity is not part of the value.",
    ),
    WorkerArchetype(
        archetype_id="singular_agent_role",
        worker_class="agent",
        capability_model="tool_using_agent",
        fungibility_model="singular",
        state_model="stateful",
        state_location="session_and_artifacts",
        description="A named role or agent session that carries continuity across related work.",
        design_rule="Use when continuity is valuable enough to justify persistent identity.",
    ),
    WorkerArchetype(
        archetype_id="independent_reviewer",
        worker_class="governance",
        capability_model="tool_using_agent",
        fungibility_model="singular",
        state_model="stateful",
        state_location="session_and_artifacts",
        description="A reviewer, auditor, or governance role whose identity matters during a review window.",
        design_rule="Keep review identity distinct from production identity when independent review matters.",
    ),
    WorkerArchetype(
        archetype_id="human_operator",
        worker_class="operator",
        capability_model="human",
        fungibility_model="singular",
        state_model="stateful",
        state_location="human_context_and_artifacts",
        description="A human actor exercising judgment, authority, taste, relationship work, or residual-risk ownership.",
        design_rule="Represent bounded human work with receipts rather than treating it as hidden approval.",
    ),
)


def list_worker_archetypes() -> list[WorkerArchetype]:
    return list(WORKER_ARCHETYPES)


def get_worker_archetype(archetype_id: str) -> WorkerArchetype:
    for archetype in WORKER_ARCHETYPES:
        if archetype.archetype_id == archetype_id:
            return archetype
    raise KeyError(f"unknown worker archetype: {archetype_id}")


def deploy_worker_archetype(archetype_id: str, *, transport: TransportModel | str) -> WorkerDeployment:
    if transport not in TRANSPORTS:
        raise ValueError(f"invalid transport {transport!r}; expected one of {sorted(TRANSPORTS)}")
    return WorkerDeployment(
        archetype=get_worker_archetype(archetype_id),
        transport=transport,  # type: ignore[arg-type]
    )
