"""
Testes da busca multi-termo estilo Google (EPIC-search-engine-google-powerbi).

Cobertura:
  - `_tokenize_query`: divide a query em tokens, ignora espaços repetidos/vazios.
  - `_build_token_match`: monta cláusula por token (AND/OR), score somado por token,
    fallback ILIKE simples sem trigram.
  - `_search_where`: AND por token em queries multi-termo (ex.: "alvenaria cimento"),
    fallback OR quando AND não encontra itens (resultados parciais), e caminho de
    token único preservado (zero regressão).
  - `search_unified`: mesma lógica tokenizada em `/search`.
"""
from unittest.mock import Mock, patch

import pytest

from api import crud


def _fake_rows(mappings):
    out = []
    for m in mappings:
        row = Mock()
        row._mapping = m
        out.append(row)
    return out


class TestTokenizeQuery:
    def test_single_word(self):
        assert crud._tokenize_query("cimento") == ["cimento"]

    def test_multiple_words(self):
        assert crud._tokenize_query("alvenaria cimento") == ["alvenaria", "cimento"]

    def test_collapses_whitespace(self):
        assert crud._tokenize_query("  alvenaria   cimento  ") == ["alvenaria", "cimento"]

    def test_empty(self):
        assert crud._tokenize_query("") == []
        assert crud._tokenize_query("   ") == []

    def test_does_not_touch_numeric(self):
        assert crud._tokenize_query("92711") == ["92711"]


class TestBuildTokenMatch:
    def test_and_combines_tokens_with_trigram(self):
        clause, params, score = crud._build_token_match(
            "t.descricao", ["alvenaria", "cimento"], trigram=True, combine="AND",
        )
        assert " AND " in clause
        assert "ILIKE f_unaccent(:t_0)" in clause
        assert "ILIKE f_unaccent(:t_1)" in clause
        assert params["t_0"] == "%alvenaria%"
        assert params["t_1"] == "%cimento%"
        assert params["q_0"] == "alvenaria"
        assert params["q_1"] == "cimento"
        assert "similarity" in score and "word_similarity" in score
        assert "+" in score
        assert score.endswith("AS score")

    def test_or_combines_tokens_with_trigram(self):
        clause, _, _ = crud._build_token_match(
            "t.descricao", ["alvenaria", "cimento"], trigram=True, combine="OR",
        )
        assert " OR " in clause

    def test_fallback_plain_ilike_without_trigram(self):
        clause, params, score = crud._build_token_match(
            "t.descricao", ["alvenaria", "cimento"], trigram=False, combine="AND",
        )
        assert "unaccent" not in clause
        assert "similarity" not in score
        assert score == "NULL::float AS score"
        assert params["t_0"] == "%alvenaria%"
        assert "q_0" not in params

    def test_short_token_skips_trigram_score(self):
        clause, params, score = crud._build_token_match(
            "t.descricao", ["bloco", "de"], trigram=True, combine="AND",
        )
        # token curto ("de") ainda filtra por ILIKE, mas não pontua por trigram
        assert "ILIKE f_unaccent(:t_0)" in clause
        assert "ILIKE :t_1" in clause
        assert "q_1" not in params


class _DbWithSequentialResults:
    """Mock de db que devolve listas de linhas por chamada de fetchall()."""

    def __init__(self, call_results):
        self.db = Mock()
        ex = Mock()
        ex.fetchall.side_effect = call_results
        self.db.execute.return_value = ex

    def sql(self):
        return str(self.db.execute.call_args[0][0])

    def params(self):
        return self.db.execute.call_args[0][1]


class TestSearchWhereMultiToken:
    def _call(self, db, q, **kw):
        return crud._search_where(
            db, q,
            table_item="composicoes", table_preco="custos",
            item_alias="c", join_col="composicao_codigo",
            select_cols="c.codigo, c.descricao",
            uf="SP", data_referencia="2026-07", regime="NAO_DESONERADO",
            skip=0, limit=10, **kw,
        )

    def test_multiword_and_sql(self):
        rows = _fake_rows([{"codigo": 87327, "descricao": "ALVENARIA ... CIMENTO",
                            "total_count": 1}])
        s = _DbWithSequentialResults([rows])
        with patch.object(crud, "_trigram_enabled", return_value=True):
            self._call(s.db, "alvenaria cimento")
        assert "ILIKE f_unaccent(:t_0)" in s.sql()
        assert "ILIKE f_unaccent(:t_1)" in s.sql()
        assert " AND " in s.sql()
        assert s.params()["t_0"] == "%alvenaria%"
        assert s.params()["t_1"] == "%cimento%"

    def test_multiword_or_fallback_when_zero(self):
        rows_or = _fake_rows([
            {"codigo": 87327, "descricao": "ARGAMASSA ... ALVENARIA ... CIMENTO",
             "total_count": 3},
        ])
        s = _DbWithSequentialResults([[], rows_or])
        with patch.object(crud, "_trigram_enabled", return_value=True):
            result = self._call(s.db, "alvenaria cimento portland")
        assert result["items"]
        assert result["total"] == 3
        assert result.get("relaxed") is True
        assert " OR " in s.sql()

    def test_no_or_fallback_when_and_has_results(self):
        rows = _fake_rows([{"codigo": 1, "descricao": "X", "total_count": 1}])
        s = _DbWithSequentialResults([rows])
        with patch.object(crud, "_trigram_enabled", return_value=True):
            result = self._call(s.db, "alvenaria cimento")
        assert result["total"] == 1
        assert not result.get("relaxed")

    def test_single_token_preserves_query_param(self):
        s = _DbWithSequentialResults([[]])
        with patch.object(crud, "_trigram_enabled", return_value=True):
            self._call(s.db, "brita")
        assert "ILIKE f_unaccent(:query)" in s.sql()
        assert s.params()["q"] == "brita"

    def test_single_token_fallback_without_trigram(self):
        s = _DbWithSequentialResults([[]])
        with patch.object(crud, "_trigram_enabled", return_value=False):
            self._call(s.db, "brita")
        assert "ILIKE :query" in s.sql()
        assert "unaccent" not in s.sql()
        assert "NULL::float AS score" in s.sql()

    def test_empty_query_returns_empty(self):
        db = Mock()
        result = self._call(db, "   ")
        assert result == {"items": [], "total": 0}
        db.execute.assert_not_called()


class TestSearchUnifiedMultiToken:
    def test_multiword_and_sql(self):
        rows = _fake_rows([{"codigo": 87327, "tipo": "composicao", "total_count": 1}])
        s = _DbWithSequentialResults([rows])
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_unified(db=s.db, q="alvenaria cimento", uf="SP",
                                data_referencia="2026-07", regime="NAO_DESONERADO",
                                tipo="all", sort="relevance", skip=0, limit=10)
        assert "ILIKE f_unaccent(:t_0)" in s.sql()
        assert "ILIKE f_unaccent(:t_1)" in s.sql()
        assert " AND " in s.sql()
        assert s.params()["t_1"] == "%cimento%"

    def test_multiword_or_fallback_when_zero(self):
        rows_or = _fake_rows([{"codigo": 87327, "tipo": "composicao", "total_count": 5}])
        s = _DbWithSequentialResults([[], rows_or])
        with patch.object(crud, "_trigram_enabled", return_value=True):
            result = crud.search_unified(db=s.db, q="alvenaria cimento portland", uf="SP",
                                         data_referencia="2026-07",
                                         regime="NAO_DESONERADO", tipo="all",
                                         sort="relevance", skip=0, limit=10)
        assert result["items"]
        assert result.get("relaxed") is True
        assert " OR " in s.sql()

    def test_empty_query_returns_empty(self):
        db = Mock()
        result = crud.search_unified(db=db, q="  ", uf="SP", data_referencia="2026-07",
                                     regime="NAO_DESONERADO", tipo="all",
                                     sort="relevance", skip=0, limit=10)
        assert result == {"items": [], "total": 0}
        db.execute.assert_not_called()