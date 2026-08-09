"""
Testes para T-6 (ADR-034 / SPEC-RULE-BASE-MONITORING B4):

1. `GET /api/v1/public/base` expõe `{ available_base, consumed_base, status, sources, as_of }`.
2. `/api/v1/public/health` adiciona `max_data_referencia` (consumida).
3. `available_base` vem do calendário (e permanece quando probe bloqueado — B4.3).
4. `status` segue `resolve_status` (current / new-base-available).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app
from api.database import get_db
from api import sinapi_disponibilidade as disp


class _FakeRow:
    def __init__(self, value):
        self._value = value

    def __getitem__(self, idx):
        return self._value


class _FakeResult:
    def __init__(self, value=None):
        self._value = value

    def first(self):
        if self._value is None:
            return None
        return _FakeRow(self._value)

    def mappings(self):
        return self


class _FakeDB:
    """Captura SQL e devolve max(data_referencia) configurável."""

    def __init__(self, max_data_referencia=None):
        self.max_data_referencia = max_data_referencia
        self.statements = []

    def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        if "max(data_referencia)" in str(stmt):
            return _FakeResult(self.max_data_referencia)
        return _FakeResult()


@pytest.fixture
def captured_db():
    db = _FakeDB(max_data_referencia=None)
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


class TestBaseEndpointDocumented:
    def test_base_endpoint_in_openapi(self, openapi):
        assert "/api/v1/public/base" in openapi["paths"], (
            "Endpoint /api/v1/public/base ausente no OpenAPI"
        )

    def test_base_endpoint_tags(self, openapi):
        get_spec = openapi["paths"]["/api/v1/public/base"]["get"]
        tags = get_spec.get("tags", [])
        assert tags and tags[0] == "tier_1"

    def test_base_endpoint_summary(self, openapi):
        get_spec = openapi["paths"]["/api/v1/public/base"]["get"]
        assert get_spec.get("summary", "")


class TestBaseEndpointCurrent:
    def test_current_when_available_equals_consumed(self, monkeypatch, captured_db):
        captured_db.max_data_referencia = date(2026, 6, 1)
        monkeypatch.setattr(disp, "expected_latest_competence", lambda today: "2026-06")
        client = TestClient(app)
        resp = client.get("/api/v1/public/base")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available_base"] == "2026-06"
        assert body["consumed_base"] == "2026-06"
        assert body["status"] == "current"
        assert "sources" in body
        assert "as_of" in body

    def test_new_base_available_when_calendar_ahead(self, monkeypatch, captured_db):
        captured_db.max_data_referencia = date(2026, 6, 1)
        monkeypatch.setattr(disp, "expected_latest_competence", lambda today: "2026-07")
        client = TestClient(app)
        resp = client.get("/api/v1/public/base")
        assert resp.status_code == 200
        assert resp.json()["status"] == "new-base-available"

    def test_new_base_available_when_consumed_missing(self, monkeypatch, captured_db):
        # Sem consumida (base vazia) + base disponível no calendário → há base
        # nova a ingerir (resolve_status: available != None e consumed None).
        monkeypatch.setattr(disp, "expected_latest_competence", lambda today: "2026-06")
        client = TestClient(app)
        resp = client.get("/api/v1/public/base")
        assert resp.status_code == 200
        assert resp.json()["status"] == "new-base-available"


class TestHealthMaxDataReferencia:
    def _health(self, client):
        # Redis pode estar indisponível no host (degraded=503); o campo
        # max_data_referencia deve estar presente em qualquer dos casos.
        resp = client.get("/api/v1/public/health")
        assert resp.status_code in (200, 503)
        return resp

    def test_health_exposes_max_data_referencia(self, monkeypatch, captured_db):
        captured_db.max_data_referencia = date(2026, 6, 1)
        client = TestClient(app)
        body = self._health(client).json()
        assert body["max_data_referencia"] == "2026-06"

    def test_health_max_is_null_when_no_data(self, captured_db):
        client = TestClient(app)
        body = self._health(client).json()
        assert body.get("max_data_referencia") is None
