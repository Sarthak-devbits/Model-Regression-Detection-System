"""SQLite storage for runs, case results and baselines.

Used by the orchestrator (creates runs, reads results) and the report worker
(writes results). Each method opens a short connection and one transaction.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from shared.runs import (
    Baseline,
    CaseResult,
    Comparison,
    CreateRunRequest,
    RunMetrics,
    RunRecord,
    RunStatus,
    Verdict,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id           TEXT PRIMARY KEY,
    status           TEXT NOT NULL,
    trigger          TEXT NOT NULL,
    git_ref          TEXT,
    pr_number        INTEGER,
    prompt_version   TEXT NOT NULL,
    prompt_json      TEXT NOT NULL,
    model            TEXT NOT NULL,
    dataset_version  TEXT NOT NULL,
    judge_version    TEXT NOT NULL,
    case_count       INTEGER NOT NULL,
    baseline_run_id  TEXT,
    verdict          TEXT,
    metrics_json     TEXT,
    comparison_json  TEXT,
    error            TEXT,
    created_at       TEXT NOT NULL,
    finished_at      TEXT
);

CREATE TABLE IF NOT EXISTS case_results (
    run_id              TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    case_id             TEXT NOT NULL,
    result_json         TEXT NOT NULL,
    category_correct    INTEGER NOT NULL,
    judge_score         INTEGER,
    PRIMARY KEY (run_id, case_id)
);

CREATE TABLE IF NOT EXISTS baselines (
    dataset_version  TEXT NOT NULL,
    judge_version    TEXT NOT NULL,
    run_id           TEXT NOT NULL REFERENCES runs(run_id),
    promoted_at      TEXT NOT NULL,
    PRIMARY KEY (dataset_version, judge_version)
);

CREATE INDEX IF NOT EXISTS idx_runs_created ON runs (created_at);
"""


class RunNotFoundError(Exception):
    pass


def now_utc() -> datetime:
    return datetime.now(UTC)


class RunStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection]:
        """One connection, one transaction: commit if the block succeeds, roll back if not."""
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # ---------- writes ----------

    def create_run(self, run_id: str, request: CreateRunRequest, judge_version: str, case_count: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, status, trigger, git_ref, pr_number, prompt_version,
                                  prompt_json, model, dataset_version, judge_version,
                                  case_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    RunStatus.QUEUED,
                    request.trigger,
                    request.git_ref,
                    request.pr_number,
                    request.prompt.version_id,
                    request.prompt.model_dump_json(),
                    request.prompt.model,
                    request.dataset_version,
                    judge_version,
                    case_count,
                    now_utc().isoformat(),
                ),
            )

    def set_status(self, run_id: str, status: RunStatus, error: str | None = None) -> None:
        is_final = status in (RunStatus.COMPLETED, RunStatus.FAILED)
        finished = now_utc().isoformat() if is_final else None
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, error = ?, finished_at = ? WHERE run_id = ?",
                (status, error, finished, run_id),
            )

    def save_results(
        self,
        run_id: str,
        results: list[CaseResult],
        metrics: RunMetrics,
        comparison: Comparison | None,
        verdict: Verdict,
        error: str | None = None,
    ) -> None:
        """Store every case result and the run summary in one transaction."""
        with self._connect() as conn:
            conn.execute("DELETE FROM case_results WHERE run_id = ?", (run_id,))
            conn.executemany(
                """
                INSERT INTO case_results
                    (run_id, case_id, result_json, category_correct, judge_score)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(run_id, r.case_id, r.model_dump_json(), int(r.category_correct), r.judge_score) for r in results],
            )
            conn.execute(
                """
                UPDATE runs
                SET status = ?, metrics_json = ?, comparison_json = ?, verdict = ?,
                    baseline_run_id = ?, error = ?, finished_at = ?
                WHERE run_id = ?
                """,
                (
                    RunStatus.COMPLETED,
                    metrics.model_dump_json(),
                    comparison.model_dump_json() if comparison else None,
                    verdict,
                    comparison.baseline_run_id if comparison else None,
                    error,
                    now_utc().isoformat(),
                    run_id,
                ),
            )

    def set_baseline(self, run_id: str) -> Baseline:
        run = self.get_run(run_id)
        promoted_at = now_utc()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO baselines (dataset_version, judge_version, run_id, promoted_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (dataset_version, judge_version)
                DO UPDATE SET run_id = excluded.run_id, promoted_at = excluded.promoted_at
                """,
                (run.dataset_version, run.judge_version, run_id, promoted_at.isoformat()),
            )
        return Baseline(
            dataset_version=run.dataset_version,
            judge_version=run.judge_version,
            run_id=run_id,
            promoted_at=promoted_at,
        )

    # ---------- reads ----------

    def get_run(self, run_id: str) -> RunRecord:
        with self._connect() as conn:
            row = conn.execute(f"{_RUN_SELECT} WHERE r.run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return _row_to_run(row)

    def list_runs(self, limit: int = 20, dataset_version: str | None = None) -> list[RunRecord]:
        sql = _RUN_SELECT
        params: list[object] = []
        if dataset_version:
            sql += " WHERE r.dataset_version = ?"
            params.append(dataset_version)
        sql += " ORDER BY r.created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_run(row) for row in rows]

    def get_case_results(self, run_id: str) -> list[CaseResult]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT result_json FROM case_results WHERE run_id = ? ORDER BY case_id",
                (run_id,),
            ).fetchall()
        return [CaseResult.model_validate_json(row["result_json"]) for row in rows]

    def get_baseline_run_id(self, dataset_version: str, judge_version: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_id FROM baselines WHERE dataset_version = ? AND judge_version = ?",
                (dataset_version, judge_version),
            ).fetchone()
        return row["run_id"] if row else None

    def list_baselines(self) -> list[Baseline]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM baselines ORDER BY dataset_version").fetchall()
        return [Baseline.model_validate(dict(row)) for row in rows]


_RUN_SELECT = """
SELECT r.*, (b.run_id IS NOT NULL) AS is_baseline
FROM runs r
LEFT JOIN baselines b ON b.run_id = r.run_id
"""


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    data = dict(row)
    metrics, comparison = data.pop("metrics_json"), data.pop("comparison_json")
    data.pop("prompt_json")
    data["is_baseline"] = bool(data["is_baseline"])
    data["metrics"] = RunMetrics.model_validate_json(metrics) if metrics else None
    data["comparison"] = Comparison.model_validate_json(comparison) if comparison else None
    return RunRecord.model_validate(data)
