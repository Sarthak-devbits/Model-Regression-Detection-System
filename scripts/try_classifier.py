"""Send one email to the running classifier service, using a prompt file.

Usage (from the repo root):
    uv run python scripts/try_classifier.py "I was charged twice"
    uv run python scripts/try_classifier.py "..." --prompt prompts/classifier/v2.yaml
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

from shared.prompts import load_prompt

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify one email via the service")
    parser.add_argument("email", help="the email text, in quotes")
    parser.add_argument("--prompt", default="prompts/classifier/v1.yaml")
    parser.add_argument("--url", default="http://localhost:8001")
    args = parser.parse_args()

    prompt = load_prompt(ROOT / args.prompt)
    body = {"email": args.email, "prompt": prompt.model_dump(mode="json")}

    try:
        response = httpx.post(f"{args.url}/classify", json=body, timeout=60)
    except httpx.ConnectError:
        print(f"Could not reach {args.url}. Is the service running? Try: make classifier-dev")
        return 1

    print(f"HTTP {response.status_code}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    return 0 if response.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
