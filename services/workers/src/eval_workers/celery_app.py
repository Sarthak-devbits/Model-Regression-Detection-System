"""The Celery application: broker connection, routing and reliability settings."""

from celery import Celery

from eval_workers.settings import WorkerSettings
from shared.logging import configure_logging
from shared.tasks import JUDGE_CASE, TASK_QUEUES

settings = WorkerSettings()
configure_logging(settings.service_name, settings.log_level)

celery_app = Celery(
    "regci",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["eval_workers.tasks"],
)

celery_app.conf.update(
    # Messages are plain JSON, never pickled Python objects.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Each task name goes to its own queue.
    task_routes={name: {"queue": queue} for name, queue in TASK_QUEUES.items()},
    # Reliability: confirm a message only after the task finishes, take one at a time.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Keep the judge within the provider's rate limit (per worker process).
    task_annotations={JUDGE_CASE: {"rate_limit": settings.judge_rate_limit}},
    # Task results only need to live long enough for the chord to finish.
    result_expires=60 * 60 * 24,
    # Keep our JSON log format instead of Celery's.
    worker_hijack_root_logger=False,
    broker_connection_retry_on_startup=True,
)
