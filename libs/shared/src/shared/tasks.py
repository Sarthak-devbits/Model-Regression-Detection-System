"""Task names and queues: the contract between the orchestrator and the workers.

The orchestrator never imports worker code. It sends messages addressed to these names,
and the workers register their tasks under the same names.
"""

RUN_CASE = "eval.run_case"
JUDGE_CASE = "judge.judge_case"
AGGREGATE_RUN = "reports.aggregate_run"

QUEUE_EVAL = "eval"
QUEUE_JUDGE = "judge"
QUEUE_REPORTS = "reports"

TASK_QUEUES: dict[str, str] = {
    RUN_CASE: QUEUE_EVAL,
    JUDGE_CASE: QUEUE_JUDGE,
    AGGREGATE_RUN: QUEUE_REPORTS,
}
