from datetime import UTC, datetime

from celery import Celery

from orchestrator.dispatch import build_workflow
from shared.prompts import JudgePromptConfig, PromptConfig
from shared.runs import CaseTask

PROMPT = PromptConfig(version_id="v1", created_at=datetime(2026, 1, 1, tzinfo=UTC), system_prompt="x")
JUDGE = JudgePromptConfig(version_id="v1", created_at=datetime(2026, 1, 1, tzinfo=UTC), system_prompt="y")


def cases(n: int) -> list[CaseTask]:
    return [
        CaseTask(
            case_id=f"gc-{i:04d}",
            email="e",
            expected_category="billing",
            ideal_summary="s",
            difficulty="easy",
        )
        for i in range(1, n + 1)
    ]


def test_workflow_is_a_chord_of_run_then_judge_chains() -> None:
    app = Celery("test")  # building signatures needs no broker connection
    workflow = build_workflow(app, "run_1", cases(3), PROMPT, JUDGE)

    header, body = workflow.tasks, workflow.body
    assert len(header) == 3
    first_chain = header[0].tasks
    assert [s.task for s in first_chain] == ["eval.run_case", "judge.judge_case"]
    assert first_chain[0].options["queue"] == "eval"
    assert first_chain[1].options["queue"] == "judge"
    assert first_chain[0].args[0] == "run_1"
    assert first_chain[0].args[1]["case_id"] == "gc-0001"
    assert body.task == "reports.aggregate_run"
    assert body.options["queue"] == "reports"
    assert body.args == ("run_1",)
