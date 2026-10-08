"""Quality checks beyond the schema: coverage, balance, duplicates, consistency."""

import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from shared.categories import Category
from shared.golden import REQUIRED_EDGE_CASES, Difficulty, EdgeCase, GoldenDataset


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    check: str
    message: str
    case_id: str | None = None


@dataclass(frozen=True)
class QualityRules:
    min_cases: int = 50
    max_cases: int = 100
    min_category_share: float = 0.15
    min_summary_words: int = 5
    max_summary_words: int = 40
    very_short_max_words: int = 15


SENTENCE_END = re.compile(r"[.!?](\s|$)")


def word_count(text: str) -> int:
    return len(text.split())


def normalize(text: str) -> str:
    """Lowercase and collapse whitespace, so near-identical emails count as duplicates."""
    return " ".join(text.lower().split())


def check_dataset(dataset: GoldenDataset, rules: QualityRules | None = None) -> list[Finding]:
    rules = rules or QualityRules()
    findings: list[Finding] = []
    findings += _check_size(dataset, rules)
    findings += _check_category_coverage(dataset, rules)
    findings += _check_difficulty_coverage(dataset)
    findings += _check_edge_case_coverage(dataset)
    findings += _check_duplicates(dataset)
    findings += _check_each_case(dataset, rules)
    return findings


def _check_size(dataset: GoldenDataset, rules: QualityRules) -> list[Finding]:
    n = len(dataset.cases)
    if n < rules.min_cases or n > rules.max_cases:
        return [
            Finding(
                Severity.WARNING,
                "size",
                f"{n} cases; the target is {rules.min_cases}-{rules.max_cases}",
            )
        ]
    return []


def _check_category_coverage(dataset: GoldenDataset, rules: QualityRules) -> list[Finding]:
    findings: list[Finding] = []
    counts = Counter(case.expected.category for case in dataset.cases)
    total = len(dataset.cases)
    for category in Category:
        count = counts.get(category, 0)
        if count == 0:
            findings.append(Finding(Severity.ERROR, "category_coverage", f"no cases for '{category}'"))
        elif count / total < rules.min_category_share:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "category_balance",
                    f"'{category}' is {count / total:.0%} of cases; aim for at least {rules.min_category_share:.0%}",
                )
            )
    return findings


def _check_difficulty_coverage(dataset: GoldenDataset) -> list[Finding]:
    findings: list[Finding] = []
    present = {(case.expected.category, case.expected_difficulty) for case in dataset.cases}
    for category in Category:
        missing = [d.value for d in Difficulty if (category, d) not in present]
        if missing:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "difficulty_coverage",
                    f"'{category}' has no {', '.join(missing)} cases",
                )
            )
    return findings


def _check_edge_case_coverage(dataset: GoldenDataset) -> list[Finding]:
    used = {tag for case in dataset.cases for tag in case.edge_cases}
    missing = sorted(tag.value for tag in REQUIRED_EDGE_CASES - used)
    if missing:
        return [
            Finding(
                Severity.WARNING,
                "edge_case_coverage",
                f"no cases tagged {', '.join(missing)}",
            )
        ]
    return []


def _check_duplicates(dataset: GoldenDataset) -> list[Finding]:
    findings: list[Finding] = []
    first_seen: dict[str, str] = {}
    for case in dataset.cases:
        key = normalize(case.input.email)
        if key in first_seen:
            findings.append(
                Finding(
                    Severity.ERROR,
                    "duplicate_email",
                    f"same email text as {first_seen[key]}",
                    case.id,
                )
            )
        else:
            first_seen[key] = case.id
    return findings


def _check_each_case(dataset: GoldenDataset, rules: QualityRules) -> list[Finding]:
    findings: list[Finding] = []
    for case in dataset.cases:
        summary = case.expected.summary
        words = word_count(summary)
        if not rules.min_summary_words <= words <= rules.max_summary_words:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "summary_length",
                    f"summary has {words} words; keep it between {rules.min_summary_words} and {rules.max_summary_words}",
                    case.id,
                )
            )
        if len(SENTENCE_END.findall(summary)) > 1:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "summary_one_sentence",
                    "summary looks like more than one sentence",
                    case.id,
                )
            )

        email_words = word_count(case.input.email)
        tagged_short = EdgeCase.VERY_SHORT in case.edge_cases
        if tagged_short and email_words > rules.very_short_max_words:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "tag_consistency",
                    f"tagged very_short but the email has {email_words} words",
                    case.id,
                )
            )
        if not tagged_short and email_words <= 5:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "tag_consistency",
                    f"email has only {email_words} words; should it be tagged very_short?",
                    case.id,
                )
            )
        if EdgeCase.AMBIGUOUS in case.edge_cases and case.expected_difficulty is Difficulty.EASY:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "tag_consistency",
                    "tagged ambiguous but marked easy",
                    case.id,
                )
            )
    return findings


def dataset_stats(dataset: GoldenDataset) -> dict[str, dict[str, int]]:
    """Counts by category and difficulty, plus edge-case tag totals."""
    table: dict[str, dict[str, int]] = {c.value: {d.value: 0 for d in Difficulty} for c in Category}
    for case in dataset.cases:
        table[case.expected.category.value][case.expected_difficulty.value] += 1
    tags = Counter(tag.value for case in dataset.cases for tag in case.edge_cases)
    table["edge_cases"] = {tag.value: tags.get(tag.value, 0) for tag in EdgeCase}
    return table
