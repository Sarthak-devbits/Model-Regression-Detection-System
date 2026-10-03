"""HTTP layer: FastAPI routes and error handling around classify_email."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from classifier_service import __version__
from classifier_service.classifier import InvalidModelOutputError, classify_email
from classifier_service.llm import FakeLLMClient, LLMClient, LLMError, OpenAIClient
from classifier_service.settings import ClassifierSettings
from shared.classification import ClassifyRequest, ClassifyResponse, ErrorResponse
from shared.logging import bind_context, configure_logging


def build_llm_client(settings: ClassifierSettings) -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    if settings.openai_api_key is None:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or use LLM_PROVIDER=fake.")
    return OpenAIClient.from_api_key(
        settings.openai_api_key.get_secret_value(),
        timeout_s=settings.request_timeout_s,
        max_retries=settings.max_retries,
    )


def error_response(status_code: int, body: ErrorResponse) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=body.model_dump())


def create_app(
    settings: ClassifierSettings | None = None,
    llm: LLMClient | None = None,
) -> FastAPI:
    settings = settings or ClassifierSettings()
    configure_logging(settings.service_name, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        client = llm or build_llm_client(settings)
        app.state.llm = client
        yield
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()

    app = FastAPI(title="classifier-service", version=__version__, lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "llm_provider": settings.llm_provider}

    @app.post(
        "/classify",
        response_model=ClassifyResponse,
        responses={502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def classify(body: ClassifyRequest, request: Request) -> ClassifyResponse:
        bind_context(prompt_version=body.prompt.version_id)
        return await classify_email(body.email, body.prompt, request.app.state.llm)

    @app.exception_handler(InvalidModelOutputError)
    async def on_invalid_output(_: Request, exc: InvalidModelOutputError) -> JSONResponse:
        body = ErrorResponse(
            error="invalid_model_output",
            detail=exc.reason,
            retryable=False,
            raw_output=exc.raw_output,
        )
        return error_response(502, body)

    @app.exception_handler(LLMError)
    async def on_llm_error(_: Request, exc: LLMError) -> JSONResponse:
        if exc.retryable:
            return error_response(
                503, ErrorResponse(error="llm_unavailable", detail=str(exc), retryable=True)
            )
        return error_response(
            502, ErrorResponse(error="llm_request_failed", detail=str(exc), retryable=False)
        )

    return app
