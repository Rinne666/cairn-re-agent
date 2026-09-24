from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.worker_protocol import WorkerOutput


def valid_output() -> dict:
    return {
        "observations": [
            {
                "kind": "Observation",
                "label": "input enters function",
                "entity_key": "obs:1",
                "properties": {},
                "confidence": 0.8,
            }
        ],
        "evidence": [
            {
                "kind": "Evidence",
                "label": "call edge",
                "entity_key": "ev:1",
                "properties": {"source": "graph"},
                "confidence": 0.9,
            }
        ],
        "hypotheses": [
            {
                "kind": "Hypothesis",
                "label": "function validates key",
                "entity_key": "hyp:1",
                "properties": {},
                "confidence": 0.7,
            }
        ],
        "facts": [],
        "relations": [
            {
                "source_entity_key": "hyp:1",
                "target_entity_key": "ev:1",
                "kind": "supports",
                "properties": {},
            }
        ],
        "artifacts": [],
        "suggested_intents": [],
        "status": "completed",
        "summary": "The existing graph supports the hypothesis.",
    }


def test_worker_output_accepts_all_required_fields_and_explicit_relation():
    output = WorkerOutput.model_validate(valid_output())
    assert output.relations[0].kind == "supports"
    assert output.observations[0].entity_key == "obs:1"


@pytest.mark.parametrize(
    "field",
    [
        "observations",
        "evidence",
        "hypotheses",
        "facts",
        "relations",
        "artifacts",
        "suggested_intents",
        "status",
        "summary",
    ],
)
def test_worker_output_rejects_missing_required_field(field):
    payload = valid_output()
    del payload[field]
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


def test_worker_output_rejects_unknown_fields():
    payload = valid_output()
    payload["model"] = "should-not-leak"
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


@pytest.mark.parametrize(
    "category,kind",
    [
        ("observations", "Evidence"),
        ("evidence", "Observation"),
        ("hypotheses", "Fact"),
        ("facts", "Hypothesis"),
    ],
)
def test_finding_kind_must_match_category(category, kind):
    payload = valid_output()
    payload[category] = [{"kind": kind, "label": "x", "entity_key": f"{category}:x"}]
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


def test_duplicate_entity_keys_across_categories_are_rejected():
    payload = valid_output()
    payload["hypotheses"][0]["entity_key"] = "ev:1"
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


@pytest.mark.parametrize("field", ["kind", "label", "entity_key"])
def test_finding_identifiers_must_be_nonempty(field):
    payload = valid_output()
    payload["observations"][0][field] = ""
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


def test_finding_properties_must_be_an_object():
    payload = valid_output()
    payload["evidence"][0]["properties"] = []
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


@pytest.mark.parametrize(
    "bad_relation",
    [
        {"source_entity_key": "x", "target_entity_key": "y", "kind": "produced", "properties": {}},
        {"source_entity_key": "", "target_entity_key": "y", "kind": "supports", "properties": {}},
        {"source_entity_key": "x", "target_entity_key": "", "kind": "supports", "properties": {}},
        {"source_entity_key": 1, "target_entity_key": "y", "kind": "supports", "properties": {}},
        {
            "source_entity_key": "x",
            "target_entity_key": "y",
            "kind": "supports",
            "properties": [],
        },
        {
            "source_entity_key": "x",
            "kind": "supports",
            "target_entity_key": "y",
            "properties": {},
            "extra": True,
        },
    ],
)
def test_invalid_relations_are_rejected(bad_relation):
    payload = valid_output()
    payload["relations"] = [bad_relation]
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


@pytest.mark.parametrize(
    "kind",
    ["derived_from", "supports", "contradicts", "verified_by", "references", "calls", "flows_to"],
)
def test_all_core_relation_kinds_are_allowed(kind):
    payload = valid_output()
    payload["relations"][0]["kind"] = kind
    assert WorkerOutput.model_validate(payload).relations[0].kind == kind


@pytest.mark.parametrize("confidence", [-0.1, 1.1, "0.7", True])
def test_confidence_must_be_a_bounded_float(confidence):
    payload = valid_output()
    payload["evidence"][0]["confidence"] = confidence
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


def test_artifact_and_suggestion_are_strict_and_suggestions_are_limited():
    payload = valid_output()
    payload["artifacts"] = [
        {
            "kind": "decompilation",
            "path": "artifacts/a.txt",
            "sha256": "abc",
            "summary": "Function body",
            "size": 12,
            "provenance": {"source": "demo"},
        }
    ]
    payload["suggested_intents"] = [
        {
            "description": "Inspect the caller",
            "source_entity_keys": ["ev:1"],
            "goal_relevance": "high",
            "information_gain": "medium",
            "confidence": "medium",
            "expected_cost": "low",
        }
    ]
    assert WorkerOutput.model_validate(payload).artifacts[0].size == 12

    invalid = deepcopy(payload)
    invalid["artifacts"][0]["size"] = -1
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(invalid)

    invalid = deepcopy(payload)
    invalid["suggested_intents"][0]["source_entity_keys"] = [1]
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(invalid)

    invalid = deepcopy(payload)
    invalid["suggested_intents"][0]["description"] = ""
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(invalid)

    invalid = deepcopy(payload)
    invalid["suggested_intents"][0]["confidence"] = 0.7
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(invalid)

    invalid = valid_output()
    invalid["suggested_intents"] = [{"description": f"intent {i}"} for i in range(4)]
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(invalid)


@pytest.mark.parametrize("field", ["kind", "path", "sha256", "summary", "size", "provenance"])
def test_artifact_requires_every_typed_field(field):
    payload = valid_output()
    artifact = {
        "kind": "decompilation",
        "path": "result.txt",
        "sha256": "hash",
        "summary": "body",
        "size": 1,
        "provenance": {},
    }
    del artifact[field]
    payload["artifacts"] = [artifact]
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", ""),
        ("path", ""),
        ("sha256", ""),
        ("summary", ""),
        ("size", True),
        ("provenance", []),
    ],
)
def test_artifact_invalid_values_are_rejected(field, value):
    payload = valid_output()
    payload["artifacts"] = [
        {
            "kind": "decompilation",
            "path": "result.txt",
            "sha256": "hash",
            "summary": "body",
            "size": 1,
            "provenance": {},
        }
    ]
    payload["artifacts"][0][field] = value
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_worker_output_status_is_explicit(status):
    payload = valid_output()
    payload["status"] = status
    assert WorkerOutput.model_validate(payload).status == status


def test_worker_output_rejects_unknown_status():
    payload = valid_output()
    payload["status"] = "done"
    with pytest.raises(ValidationError):
        WorkerOutput.model_validate(payload)
