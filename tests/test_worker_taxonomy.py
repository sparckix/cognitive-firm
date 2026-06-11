from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.operating_units import WORKER_CLASSES as OPERATING_UNIT_WORKER_CLASSES  # noqa: E402
from cognitive_firm.orchestration.worker_taxonomy import (  # noqa: E402
    WORKER_ARCHETYPES,
    WORKER_CLASSES,
    deploy_worker_archetype,
    get_worker_archetype,
    list_worker_archetypes,
)


def test_worker_classes_are_shared_with_operating_units():
    assert OPERATING_UNIT_WORKER_CLASSES == WORKER_CLASSES


def test_worker_archetypes_cover_each_worker_class():
    covered = {archetype.worker_class for archetype in list_worker_archetypes()}

    assert covered == set(WORKER_CLASSES)
    assert all(archetype.design_rule for archetype in WORKER_ARCHETYPES)


def test_transport_is_orthogonal_to_worker_structure():
    api = deploy_worker_archetype("fungible_llm_call", transport="api")
    cli = deploy_worker_archetype("fungible_llm_call", transport="subscription_cli")

    assert api.archetype == cli.archetype
    assert api.transport == "api"
    assert cli.transport == "subscription_cli"
    assert api.archetype.capability_model == "bare_llm"
    assert api.archetype.state_model == "stateless"
    assert api.archetype.fungibility_model == "fungible"


def test_agent_capability_does_not_force_singular_identity():
    fungible = get_worker_archetype("fungible_agent_worker")
    singular = get_worker_archetype("singular_agent_role")

    assert fungible.worker_class == "agent"
    assert singular.worker_class == "agent"
    assert fungible.capability_model == "tool_using_agent"
    assert singular.capability_model == "tool_using_agent"
    assert fungible.fungibility_model == "fungible"
    assert singular.fungibility_model == "singular"
    assert fungible.state_model == "stateless"
    assert singular.state_model == "stateful"


def test_unknown_worker_archetype_and_transport_fail():
    with pytest.raises(KeyError):
        get_worker_archetype("missing")
    with pytest.raises(ValueError):
        deploy_worker_archetype("fungible_llm_call", transport="carrier_pigeon")
