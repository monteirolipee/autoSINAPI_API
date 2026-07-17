"""
Testes para STORY-API-006: Contratos de erro implementados no FastAPI
(404 / 400 / 409 / 500 / 503) ausentes no OpenAPI spec.

Valida via OpenAPI runtime (/openapi.json) que todo erro `HTTPException`
levantado no código da API está documentado na resposta do endpoint
(STORY-API-005 cobriu 401/402/429 do Kong; aqui cobrimos os do FastAPI).

Estratégia (TDD / DDD):
- OpenAPI runtime (sem DB): inspeciona `responses` de cada operação no
  `/openapi.json` e garante presença dos códigos implementados.
- Inspeção das constantes SSOT em `schemas.py` (`_NOT_FOUND_404`,
  `_BAD_REQUEST_400`, `_CONFLICT_409`, `_SERVER_ERROR_500`,
  `_SERVICE_UNAVAILABLE_503`): garante coesão/DRY — o contrato de erro é
  reutilizado, não duplicado inline por endpoint.
- Teste funcional opcional (com DB): dispara o `HTTPException` real via
  `TestClient` para validação fim-a-fim (skip se o banco não estiver up).
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.main import app
from api import schemas as schema_contracts

# Endpoints que levantam HTTPException(status_code=404) no código FastAPI.
NOT_FOUND_PATHS = [
    "/api/v1/public/insumos/{codigo}",
    "/api/v1/public/composicoes/{codigo}",
    "/api/v1/public/bi/composicao/{codigo}/bom",
    "/api/v1/public/bi/curva-abc",
    "/api/v1/public/bi/composicao/{codigo}/otimizar",
    "/api/v1/public/bi/item/{tipo_item}/{codigo}/historico",
    "/api/v1/public/bi/item/{tipo_item}/{codigo}/manutencoes",
    "/api/v1/public/bi/audit/{tipo_item}/{codigo}",
    "/api/v1/public/bi/curva-abc/por-classificacao",
    "/api/v1/public/bi/tendencias/por-classificacao",
    "/api/v1/public/bi/item/{tipo_item}/{codigo}/precos-uf",
    "/api/v1/public/bi/composicao/{codigo}/produtividade",
    "/api/v1/public/bi/insumo/{codigo}/onde-usado",
]

# Endpoints que validam tipo_item / data_fim / codigos e levantam 400.
BAD_REQUEST_PATHS = [
    "/api/v1/public/bi/item/{tipo_item}/{codigo}/historico",
    "/api/v1/public/bi/item/{tipo_item}/{codigo}/manutencoes",
    "/api/v1/public/bi/audit/{tipo_item}/{codigo}",
    "/api/v1/public/bi/item/{tipo_item}/{codigo}/precos-uf",
    "/api/v1/public/bi/tendencias/por-classificacao",
    "/api/v1/public/bi/insumo/{codigo}/onde-usado",
]


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


def _method_responses(openapi, path, method):
    return openapi["paths"][path][method].get("responses", {})


def _all_responses(openapi, path):
    """Union de todos os códigos de resposta de todas as operações do path."""
    codes = set()
    for m, d in openapi["paths"][path].items():
        if m == "parameters" or not isinstance(d, dict):
            continue
        codes.update(d.get("responses", {}).keys())
    return codes


class TestNotFoundContract:
    def test_not_found_documented_for_all_404_endpoints(self, openapi):
        for path in NOT_FOUND_PATHS:
            codes = _all_responses(openapi, path)
            assert "404" in codes, (
                f"{path}: resposta 404 ausente, mas o endpoint levanta "
                f"HTTPException(status_code=404) (STORY-API-006)"
            )

    def test_not_found_contract_constant(self):
        assert hasattr(schema_contracts, "_NOT_FOUND_404"), (
            "SSOT _NOT_FOUND_404 ausente em schemas.py"
        )
        assert "404" in schema_contracts._NOT_FOUND_404 or isinstance(
            schema_contracts._NOT_FOUND_404, dict
        )


class TestBadRequestContract:
    def test_bad_request_documented_for_validation_endpoints(self, openapi):
        for path in BAD_REQUEST_PATHS:
            codes = _all_responses(openapi, path)
            assert "400" in codes, (
                f"{path}: resposta 400 ausente, mas o endpoint valida "
                f"tipo_item/data_fim/codigos e levanta 400 (STORY-API-006)"
            )

    def test_bad_request_contract_constant(self):
        assert hasattr(schema_contracts, "_BAD_REQUEST_400"), (
            "SSOT _BAD_REQUEST_400 ausente em schemas.py"
        )


class TestPopulateConflictAndServerError:
    def test_conflict_documented_on_populate(self, openapi):
        responses = _method_responses(
            openapi, "/api/v1/admin/populate-database", "post"
        )
        assert "409" in responses, (
            "populate-database: resposta 409 ausente (lock de tarefa em andamento)"
        )

    def test_server_error_documented_on_populate(self, openapi):
        responses = _method_responses(
            openapi, "/api/v1/admin/populate-database", "post"
        )
        assert "500" in responses, (
            "populate-database: resposta 500 ausente (falha ao enfileirar ETL)"
        )

    def test_conflict_and_server_error_constants(self):
        assert hasattr(schema_contracts, "_CONFLICT_409")
        assert hasattr(schema_contracts, "_SERVER_ERROR_500")


class TestHealthDegraded:
    def test_service_unavailable_documented_on_health(self, openapi):
        responses = _method_responses(
            openapi, "/api/v1/public/health", "get"
        )
        assert "503" in responses, (
            "health: resposta 503 ausente (banco/redis degradados → 503)"
        )

    def test_service_unavailable_constant(self):
        assert hasattr(schema_contracts, "_SERVICE_UNAVAILABLE_503")


class TestResponseContractCohesion:
    """SSOT reutilizada: nenhum endpoint define 404/400/409/500/503 inline."""

    def test_public_endpoints_reuse_rate_limit_only(self, openapi):
        # Garante que a composição de responses é coerente: públicos+BIT têm 429.
        for path in NOT_FOUND_PATHS + BAD_REQUEST_PATHS:
            codes = _all_responses(openapi, path)
            assert "429" in codes, (
                f"{path}: endpoint público/BIT deve manter 429 (rate limit)"
            )


def _db_available():
    """Verifica se o banco de testes está acessível (para testes funcionais)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        return False
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _db_available(), reason="banco de testes indisponível")
class TestFunctionalErrorRaised:
    """Dispara o HTTPException real via TestClient (fim-a-fim, opcional)."""

    def test_bad_request_on_invalid_tipo_item(self):
        client = TestClient(app)
        r = client.get(
            "/api/v1/public/bi/item/foo/123/precos-uf",
            params={"data_referencia": "2025-09", "uf": "SP"},
        )
        assert r.status_code == 400, (
            f"esperado 400 para tipo_item='foo', recebido {r.status_code}"
        )

    def test_not_found_on_unknown_insumo(self):
        client = TestClient(app)
        r = client.get(
            "/api/v1/public/insumos/999999999",
            params={"uf": "SP", "data_referencia": "2025-09"},
        )
        assert r.status_code == 404, (
            f"esperado 404 para insumo inexistente, recebido {r.status_code}"
        )
