"""Utilities for dispatching ETL population tasks (DRY: shared by HTTP endpoint and Celery beat)."""

import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis
from dateutil.relativedelta import relativedelta

logger = logging.getLogger("autosinapi.populate_utils")

# SSOT: mesmo host do celery_config (autosinapi_redis). O alias genérico
# "redis" colide no server_mesh (server_redis), quebrando lock/cache.
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)

# Tempo de posse do lock: 90 min (uma execução de ETL completa não deve
# ultrapassar isso; sobra margem contra travamentos por crash).
LOCK_TTL_SECONDS = 5400


def _populate_lock_key(year: int, month: int, state: str, mode_suffix: str) -> str:
    return f"lock:autosinapi:populate:{year}:{month:02d}:{state.upper()}:{mode_suffix}"


def _decode_token(value):
    """Normaliza o valor retornado pelo Redis (bytes em produção, str em testes)."""
    if isinstance(value, bytes):
        try:
            return value.decode()
        except Exception:
            return value
    return value


def acquire_populate_lock(year: int, month: int, state: str, sandbox: bool = False) -> Optional[str]:
    """Adquire o lock exclusivo de ETL.

    Retorna um token de posse (UUID) em caso de sucesso, ou None se o lock
    já estiver ocupado por outra execução.
    """
    mode_suffix = "sandbox" if sandbox else "prod"
    lock_key = _populate_lock_key(year, month, state, mode_suffix)
    token = uuid.uuid4().hex
    if redis_client.set(lock_key, token, nx=True, ex=LOCK_TTL_SECONDS):
        return token
    return None


def release_populate_lock(year: int, month: int, state: str, token: Optional[str], sandbox: bool = False) -> None:
    """Libera o lock SOMENTE se o chamador for o dono (token confere).

    Evita que uma retentativa ou worker diferente libere o lock de uma
    execução em andamento, o que causaria corrida de ETLs.
    """
    if not token:
        return
    mode_suffix = "sandbox" if sandbox else "prod"
    lock_key = _populate_lock_key(year, month, state, mode_suffix)
    current = redis_client.get(lock_key)
    if current is None:
        return
    if _decode_token(current) == token:
        redis_client.delete(lock_key)


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


def build_db_config() -> dict:
    """Monta o db_config do worker ETL com credenciais conhecidas (SSOT).

    Ordem de precedência (ADR-033 R1.1): PG_* -> POSTGRES_* -> DB_HOST ->
    host padrão `db`. Em Compose, `db` é o alias privado da própria stack.
    As mesmas variáveis PG_* usadas pelo quota-alerter garantem que quem
    escreve e quem lê o banco concordam.
    """
    return {
        "host": os.getenv("PG_HOST", os.getenv("DB_HOST", "db")),
        "port": int(os.getenv("PG_PORT", "5432")),
        "database": os.getenv("PG_DATABASE", os.getenv("POSTGRES_DB", "sinapi")),
        "user": os.getenv("PG_USER", os.getenv("POSTGRES_USER", "admin")),
        "password": os.getenv("PG_PASSWORD", os.getenv("POSTGRES_PASSWORD", "admin")),
    }


def dispatch_populate(year: int, month: int, state: str) -> Optional[dict]:
    """Adquire o lock de ETL (com token de posse) e dispara populate_sinapi_task.

    Retorna dict com info da task se disparado, ou None se o lock já estiver
    ocupado (ETL em andamento). O token de posse é repassado à task para que
    ela só libere o lock se for a dona.
    """
    sandbox = os.getenv("AUTOSINAPI_SANDBOX", "false").lower() == "true"
    mode_suffix = "sandbox" if sandbox else "prod"

    token = acquire_populate_lock(year, month, state, sandbox=sandbox)
    if token is None:
        logger.info("ETL already in progress for %s %02d/%d (lock held)", state, month, year)
        return None

    lock_key = _populate_lock_key(year, month, state, mode_suffix)

    db_config = build_db_config()
    sinapi_config = {
        "year": year,
        "month": month,
        "state": state.upper(),
        "type": "REFERENCIA",
    }

    from .tasks import populate_sinapi_task

    task = populate_sinapi_task.delay(db_config, sinapi_config, lock_token=token)
    redis_client.set(f"task:{lock_key}", task.id, ex=86400)
    logger.info("ETL dispatched: state=%s %02d/%d task_id=%s", state, month, year, task.id)
    return {
        "message": "Population task started.",
        "task_id": task.id,
        "sandbox": sandbox,
        "lock_token": token,
    }
