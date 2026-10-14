"""Turn a run into a Celery workflow and send it to Redis."""

from typing import Protocol

from celery import Celery, chain, chord
from celery.canvas import Signature

from shared.prompts import JudgePromptConfig, PromptConfig
from shared.runs import CaseTask
from shared.tasks import AGGREGATE_RUN, JUDGE_CASE, QUEUE_EVAL, QUEUE_JUDGE, QUEUE_REPORTS, RUN_CASE


class Dispatcher(Protocol):
    def dispatch(
        self,
        run_id: str,
        cases: list[CaseTask],
        prompt: PromptConfig,
        judge_prompt: JudgePromptConfig,
    ) -> None: ...


def build_workflow(
    app: Celery,
    run_id: str,
    cases: list[CaseTask],
    prompt: PromptConfig,
    judge_prompt: JudgePromptConfig,
) -> Signature:
    """A chord: for every case, run it then judge it; when all finish, aggregate once."""
    prompt_json = prompt.model_dump(mode="json")
    judge_json = judge_prompt.model_dump(mode="json")

    per_case = []
    for case in cases:
        case_json = case.model_dump(mode="json")
        run_step = app.signature(RUN_CASE, args=(run_id, case_json, prompt_json), queue=QUEUE_EVAL)
        judge_step = app.signature(JUDGE_CASE, args=(run_id, case_json, judge_json), queue=QUEUE_JUDGE)
        per_case.append(chain(run_step, judge_step))

    when_all_done = app.signature(AGGREGATE_RUN, args=(run_id,), queue=QUEUE_REPORTS)
    return chord(per_case, when_all_done)


class CeleryDispatcher:
    """Sends workflows by task name. The orchestrator never imports worker code."""

    def __init__(self, redis_url: str) -> None:
        self.app = Celery("orchestrator", broker=redis_url, backend=redis_url)
        self.app.conf.update(task_serializer="json", accept_content=["json"])

    def dispatch(
        self,
        run_id: str,
        cases: list[CaseTask],
        prompt: PromptConfig,
        judge_prompt: JudgePromptConfig,
    ) -> None:
        build_workflow(self.app, run_id, cases, prompt, judge_prompt).apply_async()
