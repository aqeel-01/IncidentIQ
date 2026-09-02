"""Tests for Celery worker configuration."""

from __future__ import annotations

from app.core.config import Settings
from app.workers.celery_app import configure_celery_app
from app.workers.config import celery_config_from_settings


def test_celery_config_from_settings_uses_redis_by_default() -> None:
    settings = Settings(
        _env_file=None,
        redis_url="redis://localhost:6379/0",
        celery_default_queue="investigation",
    )

    config = celery_config_from_settings(settings)

    assert config["broker_url"] == "redis://localhost:6379/0"
    assert config["result_backend"] == "redis://localhost:6379/0"
    assert config["task_default_queue"] == "investigation"
    assert config["task_routes"]["investigation.run"]["queue"] == "investigation"


def test_celery_config_allows_explicit_broker_override() -> None:
    settings = Settings(
        _env_file=None,
        redis_url="redis://localhost:6379/0",
        celery_broker_url="redis://broker:6379/1",
        celery_result_backend="redis://broker:6379/2",
    )

    assert settings.resolved_celery_broker_url == "redis://broker:6379/1"
    assert settings.resolved_celery_result_backend == "redis://broker:6379/2"


def test_configure_celery_app_autodiscovers_tasks() -> None:
    from celery import Celery

    settings = Settings(_env_file=None, redis_url="redis://localhost:6379/0")
    app = Celery("test-incidentiq")
    configure_celery_app(app, settings)

    assert app.conf.task_default_queue == "investigation"
    assert app.conf.task_max_retries == 3
    assert "investigation.run" in app.tasks
