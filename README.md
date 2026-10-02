# LLM Regression CI

Runs a golden dataset through an LLM feature whenever a prompt or model changes,
diffs the results against the last good run, and blocks merges or alerts Slack on regressions.

## Local setup
1. Install uv, Docker (with Compose v2), and make.
2. `cp .env.example .env`
3. `make install`
4. `make up`
5. `make check`

Full onboarding docs arrive in Phase 5.
