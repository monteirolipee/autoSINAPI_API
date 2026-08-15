"""
Testes da camada 4 (vetorial/RRF) do pipeline de busca (ADR-006).

Cobrem:
  - _rrf_merge: reorder híbrido deterministic, itens exclusivos vetoriais
    descartados (camada 4 apenas refina o conjunto textual).
  - unified_search: degradação graciosa quando a camada vetorial falha
    (várias rotas de erro → meta.degraded contém 'vector', sem 5xx).
  - unified_search: provider offline → degraded (sem exceção).
"""
import pytest

from api import search


def _item(codigo, tipo="insumo"):
    return {"codigo": codigo, "tipo": tipo, "descricao": f"item {codigo}", "valor": 1.0}


class TestRRFMerge:
    def test_empty_vector_keeps_trigram_order(self):
        items = [_item(1), _item(2)]
        assert search._rrf_merge(items, []) == items

    def test_no_trigram_items_stays_empty(self):
        assert search._rrf_merge([], [{"codigo": 9, "tipo_item": "insumo"}]) == []

    def test_shared_items_reranked_above_exclusive(self):
        items = [_item(1), _item(2), _item(3)]
        hits = [
            {"codigo": 3, "tipo_item": "insumo"},
            {"codigo": 1, "tipo_item": "insumo"},
        ]
        merged = search._rrf_merge(items, hits)
        # 3 e 1 aparecem nas duas listas → sobem; 2 (só trigrama) fica por último.
        # RRF determinístico: 1 soma 1/61+1/62, 3 soma 1/63+1/61 → 1 > 3.
        assert [it["codigo"] for it in merged] == [1, 3, 2]

    def test_discards_items_only_in_vector(self):
        items = [_item(1)]
        hits = [
            {"codigo": 1, "tipo_item": "insumo"},
            {"codigo": 999, "tipo_item": "insumo"},
        ]
        merged = search._rrf_merge(items, hits)
        codes = [it["codigo"] for it in merged]
        assert 999 not in codes
        assert 1 in codes

    def test_tipo_key_matches_properly(self):
        items = [_item(1, "insumo"), _item(2, "composicao")]
        hits = [{"codigo": 2, "tipo_item": "composicao"}]
        merged = search._rrf_merge(items, hits)
        assert merged[0]["codigo"] == 2


class TestUnifiedSearchVectorDegradation:
    def test_vector_off_not_in_providers(self):
        # Sem chamadas a banco: proíbe qualquer degradação fake.
        from api import crud
        crud._trigram_enabled = lambda db: True
        crud.search_unified = lambda *a, **k: {"items": [_item(1)], "total": 1}
        crud.get_usado_em_summary = lambda db, codigo, top=5: {}
        result = search.unified_search(None, "areia", "SP", "2026-07", "NAO_DESONERADO",
                                       vector="off")
        assert "vector" not in result["meta"]["providers"]
        assert "vector" not in result["meta"]["degraded"]

    def test_vector_provider_degradation_appends_vector(self, monkeypatch):
        from api import crud
        crud._trigram_enabled = lambda db: True
        crud.search_unified = lambda *a, **k: {"items": [_item(1)], "total": 1}
        crud.get_usado_em_summary = lambda db, codigo, top=5: {}
        import api.vector_store as vs

        class BoomEmbed:
            def embed(self, texts):
                raise RuntimeError("offline")

        monkeypatch.setattr(vs, "EmbeddingProvider", lambda *a, **k: BoomEmbed())
        result = search.unified_search(None, "areia", "SP", "2026-07", "NAO_DESONERADO",
                                       vector="on")
        assert "vector" not in result["meta"]["providers"]
        assert "vector" in result["meta"]["degraded"]
        assert len(result["items"]) == 1  # base trigrama intacta