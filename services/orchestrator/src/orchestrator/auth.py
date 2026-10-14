"""Optional bearer-token check for every API route except the health check."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

bearer_scheme = HTTPBearer(auto_error=False)

# "Run bearer_scheme and give me its result": None when no Authorization header was sent.
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def make_token_check(expected: SecretStr | None):
    def check(credentials: BearerCredentials) -> None:
        if expected is None:
            return
        given = credentials.credentials if credentials else ""
        if not secrets.compare_digest(given, expected.get_secret_value()):
            raise HTTPException(
                status_code=401,
                detail="missing or invalid API token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return check
