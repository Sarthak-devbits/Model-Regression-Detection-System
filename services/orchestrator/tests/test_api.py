from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from orchestrator.main import create_app
from orchestrator.settings import OrchestratorSettings

PROMPT = {"version_id": "v1", "created_at": "2026-01-01T00:00:00Z", "system_prompt": "Classify."}


@pytest.fixture
def build(tmp_path: Path, prompts_dir: Path, make_golden, make_dispatcher):
    """Build a test client. Returns (client, dispatcher, settings)."""

    def _build(status: str = "draft", token: str | None = None, fail: bool = False):
        settings = OrchestratorSettings(
            _env_file=None,
            database_path=tmp_path / "db.sqlite3",
            golden_dir=make_golden(status=status),
            prompts_dir=prompts_dir,
            orchestrator_api_token=SecretStr(token) if token else None,
        )
        dispatcher = make_dispatcher(fail=fail)
        client = TestClient(create_app(settings=settings, dispatcher=dispatcher))
        return client, dispatcher, settings

    return _build


def start_run(client: TestClient, **extra) -> dict:
    response = client.post("/runs", json={"prompt": PROMPT, "dataset_version": "v1", **extra})
    assert response.status_code == 202, response.text
    return response.json()


def test_healthz_reports_judge_version(build) -> None:
    client, _, _ = build()
    assert client.get("/healthz").json() == {"status": "ok", "judge_version": "v1"}


def test_create_run_dispatches_every_case(build) -> None:
    client, dispatcher, _ = build()
    created = start_run(client, trigger="pr", pr_number=42)
    assert created["status"] == "running"
    assert created["status_url"].endswith(f"/runs/{created['run_id']}")
    assert len(dispatcher.calls) == 1
    assert len(dispatcher.calls[0]["cases"]) == 2

    run = client.get(f"/runs/{created['run_id']}").json()
    assert (run["status"], run["trigger"], run["pr_number"]) == ("running", "pr", 42)
    assert run["judge_version"] == "v1"


def test_unknown_dataset_is_422(build) -> None:
    client, dispatcher, _ = build()
    response = client.post("/runs", json={"prompt": PROMPT, "dataset_version": "v9"})
    assert response.status_code == 422
    assert "not in the registry" in response.json()["detail"]
    assert dispatcher.calls == []


def test_queue_down_is_503_and_run_marked_failed(build) -> None:
    client, _, _ = build(fail=True)
    response = client.post("/runs", json={"prompt": PROMPT, "dataset_version": "v1"})
    assert response.status_code == 503
    run = client.get("/runs").json()[0]
    assert run["status"] == "failed"
    assert "redis is down" in run["error"]


def test_missing_run_is_404(build) -> None:
    client, _, _ = build()
    assert client.get("/runs/run_nope").status_code == 404
    assert client.get("/runs/run_nope/cases").status_code == 404


def test_baseline_needs_a_completed_run(build) -> None:
    client, _, _ = build()
    run_id = start_run(client)["run_id"]
    response = client.post("/baselines", json={"run_id": run_id})
    assert response.status_code == 409
    assert "not completed" in response.json()["detail"]


def test_baseline_needs_a_frozen_dataset(build, complete_run) -> None:
    client, _, settings = build(status="draft")
    run_id = start_run(client)["run_id"]
    complete_run(settings.database_path, run_id)
    response = client.post("/baselines", json={"run_id": run_id})
    assert response.status_code == 409
    assert "only frozen datasets" in response.json()["detail"]


def test_promote_baseline(build, complete_run) -> None:
    client, _, settings = build(status="frozen")
    run_id = start_run(client)["run_id"]
    complete_run(settings.database_path, run_id)

    assert client.post("/baselines", json={"run_id": run_id}).status_code == 200
    assert client.get(f"/runs/{run_id}").json()["is_baseline"] is True
    assert client.get("/baselines").json()[0]["run_id"] == run_id
    assert client.get(f"/runs/{run_id}/cases").json()[0]["case_id"] == "gc-0001"


def test_token_is_required_when_configured(build) -> None:
    client, _, _ = build(token="s3cret")
    assert client.get("/runs").status_code == 401
    assert client.get("/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/runs", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/healthz").status_code == 200
