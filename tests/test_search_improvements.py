"""
Testes para a Fase 1 da busca (SPEC-RULE-SEARCH / ADR-006 ranking trigram,
ADR-007 busca por código, paginação com total).

Cobertura:
  - `_normalize_search_q`: termo numérico vira código exato.
  - `_search_where` fallback (sem pg_trgm): ILIKE simples, score NULL.
  - `_search_where` trigram: usa unaccent + similarity, expõe score.
  - `_run_search`: total_count da janela vira `total`, item sem `total_count`.
  - Busca por código: cláusula `codigo = :codigo` e param presente.
  - Endpoint: `?meta=true` → envelope `{items,total}`; default → lista + header
    `X-Total-Count`; itens expõem `score`.
"""
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from api import crud, schemas
from api.main import app, _search_response


# --- _normalize_search_q ---

class TestNormalizeSearchQ:
    def test_numeric_term_becomes_code(self):
        assert crud._normalize_search_q("92711") == ("92711", 92711)

    def test_leading_zeros_preserved_for_match(self):
        assert crud._normalize_search_q("0001")[1] == 1

    def test_non_numeric_keeps_none_code(self):
        assert crud._normalize_search_q("brita") == ("brita", None)

    def test_empty_string_returns_empty_term(self):
        assert crud._normalize_search_q("  ") == ("", None)


# --- _run_search ---

class TestRunSearch:
    def _fake_row(self, mapping):
        row = Mock()
        row._mapping = mapping
        return row

    def test_total_comes_from_window_count(self):
        rows = [
            self._fake_row({"codigo": 1, "descricao": "A", "total_count": 42}),
            self._fake_row({"codigo": 2, "descricao": "B", "total_count": 42}),
        ]
        db = Mock()
        db.execute.return_value.fetchall.return_value = rows
        result = crud._run_search(db, "SELECT ...", {})
        assert result["total"] == 42
        assert len(result["items"]) == 2
        assert "total_count" not in result["items"][0]

    def test_total_zero_when_no_rows(self):
        db = Mock()
        db.execute.return_value.fetchall.return_value = []
        result = crud._run_search(db, "SELECT ...", {})
        assert result == {"items": [], "total": 0}


# --- _search_where: fallback e trigram ---

class TestSearchWhere:
    def _db(self, rows=None):
        db = Mock()
        db.execute.return_value.fetchall.return_value = rows or []
        return db

    def _call(self, db, q="brita", **kw):
        return crud._search_where(
            db, q,
            table_item="insumos", table_preco="precos_insumos",
            item_alias="i", join_col="insumo_codigo",
            select_cols="i.codigo, i.descricao",
            uf="SP", data_referencia="2025-09", regime="NAO_DESONERADO",
            skip=0, limit=10, **kw,
        )

    def test_fallback_uses_plain_ilike_no_unaccent(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=False):
            self._call(db)
            sql = str(db.execute.call_args[0][0])
        assert "unaccent" not in sql
        assert "ILIKE :query" in sql
        assert "similarity" not in sql

    def test_fallback_exposes_null_score(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=False):
            self._call(db)
            sql = str(db.execute.call_args[0][0])
        assert "NULL::float AS score" in sql

    def test_trigram_uses_unaccent_and_similarity(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            self._call(db)
            sql = str(db.execute.call_args[0][0])
            params = db.execute.call_args[0][1]
        assert "unaccent(" in sql
        assert "similarity(" in sql
        assert "word_similarity(" in sql
        assert params.get("q") == "brita"

    def test_trigram_orders_by_score(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            self._call(db)
            sql = str(db.execute.call_args[0][0])
        assert "ORDER BY score DESC" in sql

    def test_short_term_falls_back_even_with_trigram(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            self._call(db, q="ab")
            sql = str(db.execute.call_args[0][0])
        assert "unaccent" not in sql

    def test_numeric_q_adds_code_clause_and_param(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=False):
            self._call(db, q="92711")
            sql = str(db.execute.call_args[0][0])
            params = db.execute.call_args[0][1]
        assert "codigo = :codigo" in sql
        assert params.get("codigo") == 92711

    def test_extra_filter_applied(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=False):
            self._call(db, extra_where="AND UPPER(i.classificacao) = UPPER(:classificacao)",
                      extra_params={"classificacao": "ACO"})
            sql = str(db.execute.call_args[0][0])
            params = db.execute.call_args[0][1]
        assert "UPPER(i.classificacao) = UPPER(:classificacao)" in sql
        assert params.get("classificacao") == "ACO"

    def test_wrappers_return_envelope(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=False):
            result = crud.search_insumos_by_descricao(db, q="brita", uf="SP",
                                                      data_referencia="2025-09",
                                                      regime="NAO_DESONERADO",
                                                      skip=0, limit=10)
        assert "items" in result and "total" in result


# --- Endpoint / resposta ---

class TestSearchResponseHelper:
    def test_meta_false_returns_bare_list_with_header(self):
        result = {"items": [{"codigo": 1}], "total": 3}
        resp = _search_response(result, meta=False)
        assert resp.headers["X-Total-Count"] == "3"
        import json
        assert json.loads(bytes(resp.body)) == [{"codigo": 1}]

    def test_meta_true_returns_envelope(self):
        result = {"items": [{"codigo": 1}], "total": 3}
        resp = _search_response(result, meta=True)
        assert resp.headers["X-Total-Count"] == "3"
        import json
        payload = json.loads(bytes(resp.body))
        assert payload == {"items": [{"codigo": 1}], "total": 3}


class TestSearchEndpoint:
    @pytest.fixture
    def client(self):
        with patch("api.main.crud.search_insumos_by_descricao",
                   return_value={"items": [
                       {"codigo": 92711, "descricao": "Brita graduada",
                        "unidade": "M3", "preco_mediano": 150.5,
                        "classificacao": "AGREGADOS", "status": "ATIVO",
                        "score": 0.85},
                   ], "total": 1}):
            yield TestClient(app)

    def test_default_returns_list_and_total_header(self, client):
        r = client.get("/api/v1/public/insumos",
                       params={"q": "brita", "uf": "SP", "data_referencia": "2025-09"})
        assert r.status_code == 200
        assert r.headers.get("X-Total-Count") == "1"
        assert isinstance(r.json(), list)
        assert r.json()[0]["codigo"] == 92711
        assert r.json()[0]["score"] == 0.85

    def test_meta_true_returns_envelope(self, client):
        r = client.get("/api/v1/public/insumos",
                       params={"q": "brita", "uf": "SP", "data_referencia": "2025-09",
                               "meta": "true"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert isinstance(body["items"], list)
        assert r.headers.get("X-Total-Count") == "1"

    def test_openapi_documents_search_result_schemas(self):
        spec = TestClient(app).get("/openapi.json").json()
        paths = spec["paths"]
        assert paths["/api/v1/public/insumos"]["get"]["parameters"]
        meta_param = next(p for p in paths["/api/v1/public/insumos"]["get"]["parameters"]
                          if p["name"] == "meta")
        assert meta_param["in"] == "query"
        assert "InsumoSearchResult" in spec["components"]["schemas"]
        assert "ComposicaoSearchResult" in spec["components"]["schemas"]
        assert "score" in spec["components"]["schemas"]["Insumo"]["properties"]
