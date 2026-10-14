"""The three Celery tasks. Each is a thin wrapper: validate input, call logic, return JSON."""

import asyncio
import logging
from functools import lru_cache
from typing import Any

import httpx

from eval_workers.celery_app import celery_app, settings
from eval_workers.classifier_client import call_classifier
from eval_workers.compare import compare_runs, decide_verdict
from eval_workers.judge import (
    InvalidJudgeOutputError,
    JudgeVerdict,
    judge_summary,
    overlap_judge_reply,
)
from eval_workers.scoring import build_case_result, compute_metrics, retry_delay
from shared.llm import FakeLLMClient, LLMClient, LLMError, OpenAIClient
from shared.logging import bind_context, clear_context
from shared.prompts import JudgePromptConfig
from shared.runs import CaseResult, CaseTask, RunStatus, Verdict
from shared.store import RunStore
from shared.tasks import AGGREGATE_RUN, JUDGE_CASE, RUN_CASE

log = logging.getLogger(__name__)


# ---------- eval queue ----------


@celery_app.task(name=RUN_CASE, bind=True, max_retries=settings.task_max_retries)
def run_case(self, run_id: str, case: dict[str, Any], prompt: dict[str, Any]) -> dict[str, Any]:
    """Send one golden case to the classifier service and score the category."""
    clear_context()
    bind_context(run_id=run_id, case_id=case["case_id"])
    task = CaseTask.model_validate(case)

    with httpx.Client(base_url=settings.classifier_url, timeout=settings.classifier_timeout_s) as c:
        outcome = call_classifier(c, task.email, prompt)

    if outcome.kind == "retryable" and self.request.retries < self.max_retries:
        log.warning("retrying case", extra={"fields": {"reason": outcome.error}})
        raise self.retry(countdown=retry_delay(self.request.retries))

    result = build_case_result(task, outcome)
    log.info("case done", extra={"fields": {"correct": result.category_correct}})
    return result.model_dump(mode="json")


# ---------- judge queue ----------


def build_judge_llm() -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLMClient(responder=overlap_judge_reply)
    if settings.openai_api_key is None:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or use LLM_PROVIDER=fake.")
    return OpenAIClient.from_api_key(
        settings.openai_api_key.get_secret_value(),
        timeout_s=settings.judge_timeout_s,
        max_retries=0,
    )


async def run_judge(judge_prompt: JudgePromptConfig, task: CaseTask, summary: str) -> JudgeVerdict:
    """Create the client inside this event loop, use it once, close it."""
    llm = build_judge_llm()
    try:
        return await judge_summary(llm, judge_prompt, task.email, task.ideal_summary, summary)
    finally:
        close = getattr(llm, "aclose", None)
        if close is not None:
            await close()


@celery_app.task(name=JUDGE_CASE, bind=True, max_retries=settings.task_max_retries)
def judge_case(
    self,
    case_result: dict[str, Any],
    run_id: str,
    case: dict[str, Any],
    judge_prompt: dict[str, Any],
) -> dict[str, Any]:
    """Grade the summary from run_case. Receives run_case's return value first."""
    clear_context()
    bind_context(run_id=run_id, case_id=case["case_id"])
    result = CaseResult.model_validate(case_result)
    if result.summary is None:
        return case_result

    task = CaseTask.model_validate(case)
    rubric = JudgePromptConfig.model_validate(judge_prompt)
    try:
        verdict = asyncio.run(run_judge(rubric, task, result.summary))
    except LLMError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(countdown=retry_delay(self.request.retries)) from exc
        failed = result.model_copy(update={"judge_reason": f"judge failed: {exc}"})
        return failed.model_dump(mode="json")
    except InvalidJudgeOutputError as exc:
        failed = result.model_copy(update={"judge_reason": str(exc)})
        return failed.model_dump(mode="json")

    judged = result.model_copy(update={"judge_score": verdict.score, "judge_reason": verdict.reason})
    return judged.model_dump(mode="json")


# ---------- reports queue ----------


@lru_cache(maxsize=1)
def get_store() -> RunStore:
    return RunStore(settings.database_path)


def infrastructure_error_rate(results: list[CaseResult]) -> float:
    """Share of cases that failed for reasons outside the prompt (outages, timeouts)."""
    if not results:
        return 0.0
    infra = [r for r in results if r.error and r.error != "invalid_model_output"]
    return len(infra) / len(results)


def aggregate(run_id: str, results: list[CaseResult], store: RunStore) -> Verdict:
    """Compute metrics, compare with the baseline if there is one, and save everything."""
    run = store.get_run(run_id)
    metrics = compute_metrics(results)

    infra_rate = infrastructure_error_rate(results)
    if infra_rate > settings.max_infra_error_rate:
        note = f"{infra_rate:.0%} of cases hit infrastructure errors: {metrics.errors}"
        store.save_results(run_id, results, metrics, None, Verdict.INCONCLUSIVE, error=note)
        return Verdict.INCONCLUSIVE

    baseline_id = store.get_baseline_run_id(run.dataset_version, run.judge_version)
    if baseline_id is None or baseline_id == run_id:
        store.save_results(run_id, results, metrics, comparison=None, verdict=Verdict.NO_BASELINE)
        return Verdict.NO_BASELINE

    baseline = store.get_run(baseline_id)
    assert baseline.metrics is not None
    comparison = compare_runs(baseline_id, baseline.metrics, store.get_case_results(baseline_id), metrics, results)
    verdict = decide_verdict(comparison.accuracy_delta_pp, settings.warn_threshold_pct, settings.critical_threshold_pct)
    store.save_results(run_id, results, metrics, comparison, verdict)
    return verdict


@celery_app.task(name=AGGREGATE_RUN, bind=True, max_retries=settings.task_max_retries)
def aggregate_run(self, results: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    """Chord callback: runs once, after every case in the run has finished."""
    clear_context()
    bind_context(run_id=run_id)
    store = get_store()
    try:
        case_results = [CaseResult.model_validate(r) for r in results]
        verdict = aggregate(run_id, case_results, store)
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=retry_delay(self.request.retries)) from exc
        store.set_status(run_id, RunStatus.FAILED, error=f"aggregation failed: {exc}")
        raise
    log.info("run complete", extra={"fields": {"verdict": verdict.value}})
    return {"run_id": run_id, "verdict": verdict.value}
