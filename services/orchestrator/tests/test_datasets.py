import json

import pytest

from orchestrator.datasets import DatasetError, load_cases


def test_cases_become_worker_messages(make_golden) -> None:
    loaded = load_cases(make_golden(), "v1")
    assert loaded.status == "draft"
    assert [c.case_id for c in loaded.cases] == ["gc-0001", "gc-0002"]
    assert loaded.cases[0].ideal_summary == "Customer wants a refund."


def test_unregistered_version(make_golden) -> None:
    with pytest.raises(DatasetError, match="not in the registry"):
        load_cases(make_golden(), "v2")


def test_frozen_dataset_that_changed_is_rejected(make_golden) -> None:
    golden = make_golden(status="frozen")
    path = golden / "v1" / "cases.json"
    data = json.loads(path.read_text())
    data["cases"][0]["expected"]["category"] = "general"
    path.write_text(json.dumps(data))
    with pytest.raises(DatasetError, match="changed after it was frozen"):
        load_cases(golden, "v1")
