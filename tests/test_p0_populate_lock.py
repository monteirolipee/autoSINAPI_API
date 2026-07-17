"""
P0 audit fixes for the API layer (autosinapi_api).

Covers:
  - Ownership-safe ETL lock (token de posse): só o dono pode liberar.
  - TTL do lock 3600s -> 5400s.
  - Host padrão do banco "autosinapi_db" -> "db".
  - Status do ETL alinhado ("failure") consumido pela task Celery.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Torna o pacote autosinapi (submódulo ETL) importável localmente para os
# testes que tocam api.tasks (que faz `import autosinapi`).
_AUTOSINAPI_PATH = os.path.join(os.path.dirname(__file__), "..", "AutoSINAPI")
if _AUTOSINAPI_PATH not in sys.path:
    sys.path.insert(0, _AUTOSINAPI_PATH)

from api import populate_utils  # noqa: E402


class FakeRedis:
    """Redis em memória para testar posse de lock sem dependência externa."""

    def __init__(self):
        self.store = {}
        self.calls = []

    def set(self, key, value, nx=False, ex=None, px=None, xx=False, keepttl=False):
        self.calls.append(("set", key, value, {"nx": nx, "ex": ex}))
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        if key in self.store:
            del self.store[key]
            return 1
        return 0


def _patch_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(populate_utils, "redis_client", fake)
    return fake


def test_acquire_populate_lock_sets_ttl(monkeypatch):
    fake = _patch_redis(monkeypatch)
    token = populate_utils.acquire_populate_lock(2024, 1, "SP")

    assert token and len(token) == 32
    assert (
        "set",
        "lock:autosinapi:populate:2024:01:SP:prod",
        token,
        {"nx": True, "ex": 5400},
    ) in fake.calls


def test_acquire_populate_lock_is_exclusive(monkeypatch):
    fake = _patch_redis(monkeypatch)
    t1 = populate_utils.acquire_populate_lock(2024, 1, "SP")
    t2 = populate_utils.acquire_populate_lock(2024, 1, "SP")

    assert t1 is not None
    assert t2 is None  # lock já ocupado


def test_release_populate_lock_only_owner(monkeypatch):
    fake = _patch_redis(monkeypatch)
    token = populate_utils.acquire_populate_lock(2024, 1, "SP")
    key = "lock:autosinapi:populate:2024:01:SP:prod"

    # Worker diferente tenta liberar com token errado -> não libera
    populate_utils.release_populate_lock(2024, 1, "SP", "wrong-token")
    assert fake.get(key) == token

    # Dono libera -> lock removido
    populate_utils.release_populate_lock(2024, 1, "SP", token)
    assert fake.get(key) is None


def test_release_populate_lock_no_token_is_noop(monkeypatch):
    fake = _patch_redis(monkeypatch)
    populate_utils.acquire_populate_lock(2024, 1, "SP")
    key = "lock:autosinapi:populate:2024:01:SP:prod"

    populate_utils.release_populate_lock(2024, 1, "SP", None)
    assert fake.get(key) is not None  # nada acontece sem token


def test_dispatch_populate_passes_lock_token(monkeypatch):
    fake = _patch_redis(monkeypatch)
    from api import tasks as tasks_mod

    task_mock = MagicMock()
    task_mock.delay.return_value = MagicMock(id="task-123")
    monkeypatch.setattr(tasks_mod, "populate_sinapi_task", task_mock)

    result = populate_utils.dispatch_populate(2024, 1, "SP")

    assert result is not None
    assert result["lock_token"]
    _, kwargs = task_mock.delay.call_args
    assert kwargs.get("lock_token") == result["lock_token"]


def test_dispatch_populate_default_host_is_db(monkeypatch):
    fake = _patch_redis(monkeypatch)
    from api import tasks as tasks_mod

    captured = {}

    task_mock = MagicMock()

    def _delay(*a, **k):
        captured["args"] = a
        captured["kwargs"] = k
        return MagicMock(id="x")

    task_mock.delay.side_effect = _delay
    monkeypatch.setattr(tasks_mod, "populate_sinapi_task", task_mock)
    monkeypatch.delenv("POSTGRES_NAME", raising=False)

    populate_utils.dispatch_populate(2024, 1, "SP")

    assert captured["args"][0]["host"] == "db"


def test_run_populate_task_releases_only_owner(monkeypatch):
    """run_populate_task só libera o lock se receber o token de posse."""
    from api import tasks

    monkeypatch.setattr(tasks.autosinapi, "run_etl", MagicMock(
        return_value={"status": "failure", "message": "boom"}
    ))
    released = {}
    monkeypatch.setattr(
        populate_utils, "release_populate_lock",
        lambda y, m, s, token, sandbox=False: released.update(token=token),
    )

    tasks.run_populate_task(
        {"host": "db"}, {"year": 2024, "month": 1, "state": "SP"}, lock_token="TOK-1"
    )

    assert released.get("token") == "TOK-1"
