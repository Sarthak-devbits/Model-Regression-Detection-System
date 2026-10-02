# 1. Monorepo with a uv workspace

Status: accepted

## Context
The system has several Python services (classifier, orchestrator, Celery workers,
dashboard) that exchange the same data contracts. Separate repos would duplicate
those contracts and drift apart.

## Decision
One repository. Python packages are uv workspace members with a single lockfile.
Shared contracts and utilities live in `libs/shared` and are imported by every
service. Each service keeps its own pyproject.toml and Dockerfile.

## Consequences
- A contract change is one PR, tested against every service at once.
- Services share one schema version; independent versioning would need a package registry.
- New services must be added to the workspace member list explicitly.
