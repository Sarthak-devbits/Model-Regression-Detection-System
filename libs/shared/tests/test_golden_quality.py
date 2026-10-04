from shared.golden_quality import Severity, check_dataset

CATEGORIES = ["billing", "technical", "account", "general"]
DIFFICULTIES = ["easy", "medium", "hard"]


def checks_found(findings, severity=None) -> set[str]:
    return {f.check for f in findings if severity is None or f.severity is severity}


def full_coverage_cases(make_case) -> list[dict]:
    """One case per category x difficulty, plus every required edge case."""
    cases = []
    n = 1
    for category in CATEGORIES:
        for difficulty in DIFFICULTIES:
            cases.append(make_case(n, category=category, difficulty=difficulty))
            n += 1
    cases[1]["edge_cases"] = ["ambiguous"]
    cases[2]["edge_cases"] = ["typos"]
    cases[4]["edge_cases"] = ["mixed_language"]
    cases[5]["edge_cases"] = ["sarcasm"]
    cases[7]["edge_cases"] = ["very_short"]
    cases[7]["input"]["email"] = "cant log in"
    return cases


def test_well_covered_dataset_has_no_errors(make_case, make_dataset) -> None:
    findings = check_dataset(make_dataset(full_coverage_cases(make_case)))
    assert checks_found(findings, Severity.ERROR) == set()
    # 12 cases is below the 50-case target, so only the size warning remains
    assert checks_found(findings) == {"size"}


def test_missing_category_is_an_error(make_case, make_dataset) -> None:
    cases = [make_case(1, category="billing"), make_case(2, category="technical")]
    findings = check_dataset(make_dataset(cases))
    errors = [f for f in findings if f.check == "category_coverage"]
    assert {f.message for f in errors} == {"no cases for 'account'", "no cases for 'general'"}
    assert all(f.severity is Severity.ERROR for f in errors)


def test_duplicate_email_text_is_an_error(make_case, make_dataset) -> None:
    cases = full_coverage_cases(make_case)
    cases[3]["input"]["email"] = cases[0]["input"]["email"].upper() + "   "
    findings = check_dataset(make_dataset(cases))
    duplicate = next(f for f in findings if f.check == "duplicate_email")
    assert duplicate.case_id == "gc-0004"
    assert "gc-0001" in duplicate.message


def test_missing_required_edge_cases_are_reported(make_case, make_dataset) -> None:
    cases = [make_case(i + 1, category=c) for i, c in enumerate(CATEGORIES)]
    findings = check_dataset(make_dataset(cases))
    coverage = next(f for f in findings if f.check == "edge_case_coverage")
    for tag in ["ambiguous", "very_short", "typos", "mixed_language", "sarcasm"]:
        assert tag in coverage.message


def test_ambiguous_case_marked_easy_is_flagged(make_case, make_dataset) -> None:
    cases = full_coverage_cases(make_case)
    cases[0]["edge_cases"] = ["ambiguous"]  # cases[0] is easy
    findings = check_dataset(make_dataset(cases))
    flagged = [f for f in findings if f.check == "tag_consistency"]
    assert [f.case_id for f in flagged] == ["gc-0001"]


def test_multi_sentence_summary_is_flagged(make_case, make_dataset) -> None:
    cases = full_coverage_cases(make_case)
    cases[0]["expected"]["summary"] = "Customer was double charged. They want a refund now."
    findings = check_dataset(make_dataset(cases))
    assert "summary_one_sentence" in checks_found(findings)
