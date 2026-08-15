# STORY-SRC-002 — Endpoint Unificado /search + Suggest + Related

> Relacionado: ADR-005, ADR-006, SPEC-RULE-search-pipeline-graceful-degradation. Status: ✅ Concluída (2026-08-14).

## Objetivo
Busca unificada insumo+composição com ranking híbrido, facets, paginação server-side, autocomplete e "composições relacionadas" — a espinha dorsal do "Google do SINAPI".

## Aceite
- `GET /api/v1/public/search?q=&uf=&data_referencia=&regime=&tipo=all|insumo|composicao&sort=relevance|price_asc|price_desc|name&page=&page_size=&vector=auto|off|<slug>` retorna envelope com `meta.providers` e `meta.degraded`.
- `GET /api/v1/public/search/suggest?q=` → top 8 (prefixo + trigrama, cross-type).
- `GET /api/v1/public/search/related?codigo=&tipo=&uf=&data_referencia=&regime=` → top 5 por Jaccard BOM (fallback vetorial).
- Item da busca expõe `usado_em` (top 5 + total) quando `tipo=insumo`.
- `did you mean` quando `similarity` do termo mais próximo > limiar.

## Tasks
- [x] `api/search.py`: pipeline camadas + RRF.
- [x] `api/main.py`: 3 endpoints novos.
- [x] `api/crud.py`: Jaccard related, `usado_em`, suggest, did-you-mean.
- [~] Kong `plans.yaml` tiers (definidos na stack; aguarda sync/gitops).
- [x] Testes pytest (`tests/test_search_unified.py`, 19 testes) + contrato OpenAPI.

## Verificação
Suíte: `tests/test_search_unified.py` (19 pass). Endpoints `/search`, `/search/suggest`, `/search/related` expostos com `response_model` e tags de tier. `meta.degraded` reportado quando a camada vetorial está indisponível.

## Arquivos
`api/search.py` (novo), `api/main.py`, `api/crud.py`, `api/schemas.py`, `stacks/autosinapi/kong/plans.yaml`, `tests/`.