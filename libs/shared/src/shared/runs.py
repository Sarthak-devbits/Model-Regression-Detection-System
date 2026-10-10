"""Contracts for eval runs: what tasks exchange, what's stored, what the API returns."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from shared.categories import Category
from shared.prompts import PromptConfig


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Trigger(StrEnum):
    MANUAL = "manual"
    PR = "pr"
    MAIN = "main"
    NIGHTLY = "nightly"


class Verdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    CRITICAL = "critical"
    NO_BASELINE = "no_baseline"
    INCONCLUSIVE = "inconclusive"  # too many infrastructure errors to judge the prompt


# ---------- messages between orchestrator and workers ----------


class CaseTask(BaseModel):
    """One golden case, as sent to a worker. Only what the worker needs."""

    case_id: str
    email: str
    expected_category: Category
    ideal_summary: str
    difficulty: str


class CaseResult(BaseModel):
    """Everything measured for one case in one run."""

    case_id: str
    difficulty: str
    expected_category: Category
    predicted_category: Category | None = None
    category_correct: bool = False
    summary: str | None = None
    judge_score: int | None = Field(default=None, ge=1, le=5)
    judge_reason: str | None = None
    latency_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    raw_output: str | None = None


# ---------- results of a whole run ----------


class GroupAccuracy(BaseModel):
    total: int
    passed: int
    accuracy: float


class RunMetrics(BaseModel):
    total: int
    passed: int
    accuracy: float
    by_category: dict[str, GroupAccuracy]
    by_difficulty: dict[str, GroupAccuracy]
    judged: int
    mean_judge_score: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    input_tokens: int
    output_tokens: int
    errors: dict[str, int]


class CaseFlip(BaseModel):
    """A case whose pass/fail changed between the baseline and this run."""

    case_id: str
    expected_category: Category
    baseline_predicted: Category | None
    current_predicted: Category | None
    baseline_summary: str | None
    current_summary: str | None
    current_error: str | None


class Comparison(BaseModel):
    baseline_run_id: str
    accuracy_delta_pp: float
    by_category_delta_pp: dict[str, float]
    judge_score_delta: float | None
    latency_p95_delta_ms: float | None
    tokens_delta: int
    regressions: list[CaseFlip]
    improvements: list[CaseFlip]


# ---------- API shapes ----------


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: PromptConfig
    dataset_version: str = Field(pattern=r"^v\d+$")
    trigger: Trigger = Trigger.MANUAL
    git_ref: str | None = None
    pr_number: int | None = None


class CreateRunResponse(BaseModel):
    run_id: str
    status: RunStatus
    status_url: str


class RunRecord(BaseModel):
    run_id: str
    status: RunStatus
    trigger: Trigger
    git_ref: str | None
    pr_number: int | None
    prompt_version: str
    model: str
    dataset_version: str
    judge_version: str
    case_count: int
    is_baseline: bool
    baseline_run_id: str | None
    verdict: Verdict | None
    metrics: RunMetrics | None
    comparison: Comparison | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class PromoteBaselineRequest(BaseModel):
    run_id: str


class Baseline(BaseModel):
    dataset_version: str
    judge_version: str
    run_id: str
    promoted_at: datetime
