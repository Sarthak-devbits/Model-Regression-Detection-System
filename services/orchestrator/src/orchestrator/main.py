"""HTTP API: create runs, read results, promote baselines."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request

from orchestrator import __version__
from orchestrator.auth import make_token_check
from orchestrator.datasets import DatasetError, load_cases
from orchestrator.dispatch import CeleryDispatcher, Dispatcher
from orchestrator.settings import OrchestratorSettings
from shared.logging import bind_context, configure_logging
from shared.prompts import load_judge_prompt
from shared.runs import (
    Baseline,
    CaseResult,
    CreateRunRequest,
    CreateRunResponse,
    PromoteBaselineRequest,
    RunRecord,
    RunStatus,
)
from shared.store import RunNotFoundError, RunStore

log = logging.getLogger(__name__)


def new_run_id() -> str:
    """Sortable and unique: run_20261004T091500_3f9a1c."""
    return f"run_{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


def create_app(
    settings: OrchestratorSettings | None = None,
    dispatcher: Dispatcher | None = None,
) -> FastAPI:
    settings = settings or OrchestratorSettings()
    configure_logging(settings.service_name, settings.log_level)

    store = RunStore(settings.database_path)
    judge_path = settings.prompts_dir / "judge" / f"{settings.judge_prompt_version}.yaml"
    judge_prompt = load_judge_prompt(judge_path)
    dispatcher = dispatcher or CeleryDispatcher(settings.redis_url)

    app = FastAPI(title="orchestrator", version=__version__)
    api = APIRouter(dependencies=[Depends(make_token_check(settings.orchestrator_api_token))])

    def get_run_or_404(run_id: str) -> RunRecord:
        try:
            return store.get_run(run_id)
        except RunNotFoundError:
            raise HTTPException(404, f"run {run_id} not found") from None

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "judge_version": judge_prompt.version_id}

    @api.post("/runs", status_code=202)
    def create_run(body: CreateRunRequest, request: Request) -> CreateRunResponse:
        try:
            dataset = load_cases(settings.golden_dir, body.dataset_version)
        except DatasetError as exc:
            raise HTTPException(422, str(exc)) from exc

        run_id = new_run_id()
        bind_context(run_id=run_id)
        store.create_run(run_id, body, judge_prompt.version_id, len(dataset.cases))
        try:
            dispatcher.dispatch(run_id, dataset.cases, body.prompt, judge_prompt)
        except Exception as exc:
            store.set_status(run_id, RunStatus.FAILED, error=f"dispatch failed: {exc}")
            log.exception("dispatch failed")
            raise HTTPException(503, "queue unavailable") from exc

        store.set_status(run_id, RunStatus.RUNNING)
        log.info(
            "run dispatched",
            extra={"fields": {"cases": len(dataset.cases), "prompt": body.prompt.version_id}},
        )
        return CreateRunResponse(
            run_id=run_id,
            status=RunStatus.RUNNING,
            status_url=str(request.url_for("get_run", run_id=run_id)),
        )

    @api.get("/runs")
    def list_runs(limit: int = 20, dataset_version: str | None = None) -> list[RunRecord]:
        return store.list_runs(limit=min(limit, 100), dataset_version=dataset_version)

    @api.get("/runs/{run_id}")
    def get_run(run_id: str) -> RunRecord:
        return get_run_or_404(run_id)

    @api.get("/runs/{run_id}/cases")
    def get_run_cases(run_id: str) -> list[CaseResult]:
        get_run_or_404(run_id)
        return store.get_case_results(run_id)

    @api.post("/baselines")
    def promote_baseline(body: PromoteBaselineRequest) -> Baseline:
        run = get_run_or_404(body.run_id)
        if run.status != RunStatus.COMPLETED:
            raise HTTPException(409, f"run is {run.status}, not completed")
        try:
            dataset = load_cases(settings.golden_dir, run.dataset_version)
        except DatasetError as exc:
            raise HTTPException(409, str(exc)) from exc
        if dataset.status != "frozen":
            raise HTTPException(
                409,
                f"dataset {run.dataset_version} is {dataset.status}; only frozen datasets can have a baseline",
            )
        return store.set_baseline(body.run_id)

    @api.get("/baselines")
    def list_baselines() -> list[Baseline]:
        return store.list_baselines()

    app.include_router(api)
    return app
