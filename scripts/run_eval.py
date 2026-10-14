"""Submit an eval run to the orchestrator, wait for it, and print the result.

Usage (from the repo root):
    uv run python scripts/run_eval.py --prompt prompts/classifier/v1.yaml
    uv run python scripts/run_eval.py --prompt prompts/classifier/v2.yaml --dataset v1
    uv run python scripts/run_eval.py --promote RUN_ID

Exit codes: 0 = pass, warn or no baseline; 1 = critical regression;
            2 = could not get a verdict (run failed, inconclusive, or the API was unreachable).
Phase 5's GitHub Action uses these exit codes to block merges.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from shared.prompts import load_prompt

ROOT = Path(__file__).resolve().parent.parent
FINISHED = {"completed", "failed"}


def make_client(url: str) -> httpx.Client:
    token = os.environ.get("ORCHESTRATOR_API_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=url, headers=headers, timeout=30)


def wait_for_run(client: httpx.Client, run_id: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        run = client.get(f"/runs/{run_id}").raise_for_status().json()
        if run["status"] in FINISHED:
            return run
        if time.monotonic() > deadline:
            raise TimeoutError(f"run {run_id} still {run['status']} after {timeout_s}s")
        print(f"  ... {run['status']}", flush=True)
        time.sleep(3)


def print_report(run: dict[str, Any]) -> None:
    m = run["metrics"]
    print(f"\nRun {run['run_id']}  prompt {run['prompt_version']}  dataset {run['dataset_version']}")
    print(f"Verdict: {run['verdict'].upper()}")
    print(f"Accuracy: {m['accuracy']:.1%} ({m['passed']}/{m['total']})")
    if m["mean_judge_score"] is not None:
        print(f"Summary judge score: {m['mean_judge_score']:.2f} / 5 ({m['judged']} judged)")
    if m["latency_p95_ms"] is not None:
        print(f"Latency p50 / p95: {m['latency_p50_ms']:.0f} / {m['latency_p95_ms']:.0f} ms")
    print(f"Tokens: {m['input_tokens']} in, {m['output_tokens']} out")
    if m["errors"]:
        print(f"Errors: {m['errors']}")

    print("\nBy category:")
    for name, group in m["by_category"].items():
        print(f"  {name:<10} {group['accuracy']:>6.1%}  ({group['passed']}/{group['total']})")

    comparison = run["comparison"]
    if comparison is None:
        print("\nNo baseline to compare against. Promote a run with --promote RUN_ID.")
        return
    print(f"\nCompared with baseline {comparison['baseline_run_id']}:")
    print(f"  accuracy {comparison['accuracy_delta_pp']:+.1f} points")
    for name, delta in comparison["by_category_delta_pp"].items():
        print(f"  {name:<10} {delta:+.1f} points")
    for label, flips in (("Regressions", "regressions"), ("Improvements", "improvements")):
        print(f"\n{label}: {len(comparison[flips])}")
        for flip in comparison[flips]:
            now = flip["current_predicted"] or flip["current_error"]
            print(f"  {flip['case_id']}  expected {flip['expected_category']}: {flip['baseline_predicted']} -> {now}")


def cmd_run(client: httpx.Client, args: argparse.Namespace) -> int:
    prompt = load_prompt(ROOT / args.prompt)
    body = {
        "prompt": prompt.model_dump(mode="json"),
        "dataset_version": args.dataset,
        "trigger": args.trigger,
        "git_ref": args.git_ref,
        "pr_number": args.pr_number,
    }
    created = client.post("/runs", json=body)
    if created.status_code != 202:
        print(f"Could not start run: HTTP {created.status_code} {created.text}")
        return 2
    run_id = created.json()["run_id"]
    print(f"Started {run_id} (prompt {prompt.version_id}, dataset {args.dataset})")

    run = wait_for_run(client, run_id, args.timeout)
    if run["status"] == "failed":
        print(f"Run failed: {run['error']}")
        return 2
    print_report(run)
    if run["verdict"] == "inconclusive":
        print(f"\nInconclusive: {run['error']}")
        return 2
    return 1 if run["verdict"] == "critical" else 0


def cmd_promote(client: httpx.Client, run_id: str) -> int:
    reply = client.post("/baselines", json={"run_id": run_id})
    if reply.status_code != 200:
        print(f"Could not promote: HTTP {reply.status_code} {reply.json().get('detail')}")
        return 2
    baseline = reply.json()
    print(f"{run_id} is now the baseline for dataset {baseline['dataset_version']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an eval and print the result")
    parser.add_argument("--url", default=os.environ.get("ORCHESTRATOR_URL", "http://localhost:8000"))
    parser.add_argument("--prompt", default="prompts/classifier/v1.yaml")
    parser.add_argument("--dataset", default="v1")
    parser.add_argument("--trigger", default="manual", choices=["manual", "pr", "main", "nightly"])
    parser.add_argument("--git-ref", default=None)
    parser.add_argument("--pr-number", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for the run")
    parser.add_argument("--promote", metavar="RUN_ID", help="promote a finished run to baseline")
    args = parser.parse_args()

    try:
        with make_client(args.url) as client:
            if args.promote:
                return cmd_promote(client, args.promote)
            return cmd_run(client, args)
    except httpx.ConnectError:
        print(f"Could not reach the orchestrator at {args.url}. Is the stack running? (make up)")
        return 2
    except (httpx.HTTPStatusError, TimeoutError) as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
