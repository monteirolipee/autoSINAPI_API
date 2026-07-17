# api/tasks.py
"""
Módulo de Definição de Tarefas Assíncronas (Celery).

Este módulo define as tarefas que serão executadas em segundo plano pelos
workers do Celery. A principal vantagem é desacoplar processos demorados
da API principal, garantindo que a API permaneça rápida e responsiva.

- `celery_app`: Instancia a aplicação Celery e carrega sua configuração
  a partir do módulo `api.celery_config`.

- `populate_sinapi_task`: É a tarefa principal, que atua como uma ponte entre
  a API e o toolkit `autosinapi`. Ela recebe os dicionários de configuração
  do endpoint da API e os repassa para a função `autosinapi.run_etl`.
  Todo o processo de download, processamento e carga de dados acontece
  aqui, de forma isolada do processo da API.
"""

import os
import logging
from celery import Celery
import autosinapi

logger = logging.getLogger("autosinapi.tasks")

# Instancia o app Celery
celery_app = Celery('tasks')
celery_app.config_from_object('api.celery_config')


def run_populate_task(db_config: dict, sinapi_config: dict, lock_token: str = None) -> dict:
    """Executa o ETL e libera o lock de posse ao final.

    Extraído do wrapper Celery para ser testável de forma isolada. A liberação
    do lock só ocorre se este processo for o dono (token confere), evitando
    corrida entre retentativas/workers distintos.
    """
    year = sinapi_config.get('year')
    month = sinapi_config.get('month')
    state = sinapi_config.get('state', 'SP')
    mode_suffix = 'sandbox' if os.getenv("AUTOSINAPI_SANDBOX") == "true" else 'prod'
    try:
        logger.info("Iniciando ETL para %s %s/%s (Modo: %s)...", state, month, year, mode_suffix)
        return autosinapi.run_etl(
            db_config=db_config,
            sinapi_config=sinapi_config,
            mode='server'
        )
    finally:
        # Libera o lock SOMENTE se este worker for o dono (token confere).
        from .populate_utils import release_populate_lock
        release_populate_lock(year, month, state, lock_token, sandbox=(mode_suffix == "sandbox"))


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def populate_sinapi_task(self, db_config: dict, sinapi_config: dict, lock_token: str = None):
    """
    Ponte Celery para run_populate_task. Mantém a política de retentativa
    (específica do Celery) e delega a execução/liberação de lock.
    """
    result = run_populate_task(db_config, sinapi_config, lock_token=lock_token)

    if result.get("status") == "failure":
        msg = result.get("message", "")
        if "Too Many Requests" in msg or "429" in msg:
            raise self.retry(countdown=600)

    return result


@celery_app.task(acks_late=True, max_retries=1, default_retry_delay=3600)
def schedule_monthly_etl():
    """Periodic task (Celery beat): compute & dispatch ETL for each ETL_STATES."""
    from .config import settings
    from .populate_utils import compute_target_month, parse_etl_states, dispatch_populate

    try:
        year, month = compute_target_month(settings.ETL_LOOKBACK_MONTHS)
        states = parse_etl_states(settings.ETL_STATES)

        if not states:
            logger.warning("ETL_STATES is empty; no ETL dispatched")
            return {"dispatched": 0, "reason": "no states configured"}

        dispatched = 0
        for state in states:
            result = dispatch_populate(year, month, state)
            if result is not None:
                dispatched += 1
                logger.info("ETL dispatched: %s %02d/%d task=%s", state, month, year, result["task_id"])
            else:
                logger.info("ETL skipped (lock held): %s %02d/%d", state, month, year)

        logger.info("schedule_monthly_etl done: %d/%d dispatched", dispatched, len(states))
        return {"dispatched": dispatched, "total": len(states)}
    except Exception as exc:
        logger.error("schedule_monthly_etl failed: %s", exc, exc_info=True)
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except ImportError:
            pass
        raise
