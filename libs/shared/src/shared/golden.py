"""Golden dataset contracts: the human-verified cases every eval run is scored against."""

import hashlib
import json
from collections import Counter
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.categories import Category

CASE_ID_PATTERN = r"^gc-\d{4}$"
VERSION_PATTERN = r"^v\d+$"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class EdgeCase(StrEnum):
    AMBIGUOUS = "ambiguous"
    VERY_SHORT = "very_short"
    TYPOS = "typos"
    MIXED_LANGUAGE = "mixed_language"
    SARCASM = "sarcasm"
    MULTI_ISSUE = "multi_issue"
    LONG = "long"


# The brief asks for these edge cases explicitly, so every dataset must include them.
REQUIRED_EDGE_CASES: frozenset[EdgeCase] = frozenset(
    {
        EdgeCase.AMBIGUOUS,
        EdgeCase.VERY_SHORT,
        EdgeCase.TYPOS,
        EdgeCase.MIXED_LANGUAGE,
        EdgeCase.SARCASM,
    }
)


class CaseSource(StrEnum):
    HAND_WRITTEN = "hand_written"
    EVAL_FAILURE = "eval_failure"
    PRODUCTION = "production"


class StrictModel(BaseModel):
    """Base for golden models: unknown keys are errors and objects can't be changed."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CaseInput(StrictModel):
    email: str = Field(min_length=1, max_length=8000)


class ExpectedOutput(StrictModel):
    category: Category
    summary: str = Field(min_length=10, max_length=300)


class GoldenCase(StrictModel):
    id: str = Field(pattern=CASE_ID_PATTERN)
    input: CaseInput
    expected: ExpectedOutput
    expected_difficulty: Difficulty
    edge_cases: list[EdgeCase] = Field(default_factory=list)
    notes: str = Field(min_length=1)
    source: CaseSource = CaseSource.HAND_WRITTEN
    added_in: str = Field(pattern=VERSION_PATTERN)

    @field_validator("edge_cases")
    @classmethod
    def no_duplicate_tags(cls, tags: list[EdgeCase]) -> list[EdgeCase]:
        if len(set(tags)) != len(tags):
            raise ValueError("edge_cases contains the same tag more than once")
        return tags


def version_number(version: str) -> int:
    """'v12' -> 12, so versions sort as numbers rather than text."""
    return int(version.removeprefix("v"))


class GoldenDataset(StrictModel):
    model_config = ConfigDict(populate_by_name=True)

    json_schema_ref: str | None = Field(default=None, alias="$schema")
    dataset_version: str = Field(pattern=VERSION_PATTERN)
    description: str = Field(min_length=1)
    labeling_guide_version: int = Field(ge=1)
    cases: list[GoldenCase] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_are_unique(self) -> "GoldenDataset":
        counts = Counter(case.id for case in self.cases)
        duplicates = sorted(case_id for case_id, n in counts.items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate case ids: {duplicates}")
        return self

    @model_validator(mode="after")
    def added_in_is_not_from_the_future(self) -> "GoldenDataset":
        current = version_number(self.dataset_version)
        for case in self.cases:
            if version_number(case.added_in) > current:
                raise ValueError(
                    f"{case.id} says added_in={case.added_in}, "
                    f"but this is dataset {self.dataset_version}"
                )
        return self

    def content_hash(self) -> str:
        """Fingerprint of the content, ignoring key order and whitespace."""
        payload = self.model_dump(mode="json", exclude={"json_schema_ref"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_dataset(path: Path) -> GoldenDataset:
    """Read and validate a dataset file. Raises pydantic.ValidationError if invalid."""
    return GoldenDataset.model_validate_json(path.read_text(encoding="utf-8"))
