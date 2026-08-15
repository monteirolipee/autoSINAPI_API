# STORY-SRC-001 — Busca Relevante: Trigram ranking + Código + Total

> Relacionado: ADR-004, ADR-005, SPEC-RULE-search-pipeline-graceful-degradation. Status: **Concluído** (2026-08-14).

## Objetivo
Busca por descrição **relevante** (não alfabética), tolerante a acentos/erros, com **busca por código** e **total** — sem quebrar o contrato dos endpoints legados.

## Aceite
- `GET /api/v1/public/insumos?q=ciment` retorna itens com `score` (0..1) ordenados por relevância (prefixo/trigrama). ✅
- `GET /api/v1/public/insumos?q=92711` retorna o insumo com código 92711 (PK). ✅
- `{?meta=1}` retorna envelope `{items, total}`. ✅
- Header `X-Total-Count` presente mesmo sem `meta=1` (array preservado). ✅
- Sem `pg_trgm` instalado → degrada para ILIKE, `providers.ranking="ilike"`, sem erro. ✅

## Tasks
- [x] Alembic `006_search_trigram_gin` (extensões + índices GIN + `f_unaccent` IMMUTABLE).
- [x] `crud.py`: `search_insumos_by_descricao`/`search_composicoes_by_descricao` com `similarity`, `word_similarity(prefixo)`, `OR codigo`, `COUNT(*) OVER()` — helpers `_normalize_search_q`, `_trigram_enabled`, `_run_search`, `_search_where`.
- [x] `main.py`: enriquecer respostas (score, meta, X-Total-Count) — helper `_search_response`.
- [x] Fix cache `get_precos_all_ufs` (`@cache_result(ttl=3600)`).
- [x] Testes: `tests/test_search_improvements.py` (19 testes) + `tests/test_cache.py`.

## Arquivos
`alembic/versions/006_search_trigram_gin.py`, `api/crud.py`, `api/main.py`, `api/schemas.py`, `tests/test_search_improvements.py`, `tests/test_cache.py`.