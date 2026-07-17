"""Utilities for dispatching ETL population tasks (DRY: shared by HTTP endpoint and Celery beat)."""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

import redis
from dateutil.relativedelta import relativedelta

logger = logging.getLogger("autosinapi.populate_utils")

redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)


def compute_target_month(lookback: int = 1):
    """Return (year, month) of the SINAPI competência to import.

    Uses the current UTC date minus `lookback` months.
    """
    now = datetime.now(timezone.utc)
    target = now - relativedelta(months=lookback)
    return target.year, target.month


def parse_etl_states(states_csv: str) -> list:
    """Parse comma-separated list of states, returning uppercased, stripped list."""
    return [s.strip().upper() for s in states_csv.split(",") if s.strip()]


def dispatch_populate(year: int, month: int, state: str) -> Optional[dict]:
    """Set Redis lock and dispatch populate_sinapi_task.

    Returns dict with task info if dispatched, or None if lock held (already in progress).
    """
    sandbox = os.getenv("AUTOSINAPI_SANDBOX", "false").lower() == "true"
    mode_suffix = "sandbox" if sandbox else "prod"
    lock_key = (
        f"lock:autosinapi:populate:{year}:{month:02d}:{state.upper()}:{mode_suffix}"
    )

    if not redis_client.set(lock_key, "active", nx=True, ex=3600):
        logger.info("ETL already in progress for %s %02d/%d (lock held)", state, month, year)
        return None

    db_config = {
        "host": os.getenv("POSTGRES_NAME", "autosinapi_db"),
        "port": 5432,
        "database": os.getenv("POSTGRES_DB", "sinapi"),
        "user": os.getenv("POSTGRES_USER", "admin"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }
    sinapi_config = {
        "year": year,
        "month": month,
        "state": state.upper(),
        "type": "REFERENCIA",
    }

    from .tasks import populate_sinapi_task

    task = populate_sinapi_task.delay(db_config, sinapi_config)
    redis_client.set(f"task:{lock_key}", task.id, ex=86400)
    logger.info("ETL dispatched: state=%s %02d/%d task_id=%s", state, month, year, task.id)
    return {"message": "Population task started.", "task_id": task.id, "sandbox": sandbox}
