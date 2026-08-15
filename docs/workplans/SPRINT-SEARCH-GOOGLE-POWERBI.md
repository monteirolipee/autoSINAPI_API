# Sprint — Search Engine: Google + PowerBI do SINAPI

> Sprint do core API para o EPIC-GOOGLE-POWERBI-SINAPI.
> Fases 1-4 (vetorial). Update: 2026-08-14. Status: Concluída (remanescentes: `/search/expand` LLM + MCP tools).

## Escopo resumido

| Fase | Entregável | Prioridade |
|------|-----------|-----------|
| 1 | Trigramas GIN (ADR-004), ranking, busca por código, total/paginação, cache fix, `/search/expand` (dict) | Alta |
| 2 | `/search` unificado, `/suggest`, `/related`, `usado_em`, `did you mean`, Kong tiers, webapp | Alta |
| 3 | BI enriquecido: variação, spread regional, tendências, `/bi/cenario` | Média |
| 4 | Vetorial distribuído (pgvector, Celery, RRF), query expansion LLM, MCP tools | Média |

## Tasks

### Fase 1 — ✅ concluída (2026-08-14)
- [x] Migration `006_search_trigram_gin`: `pg_trgm`, `unaccent`, `f_unaccent` IMMUTABLE, índices GIN.
- [x] `crud.py`: reescrever buscas com ranking trigram + score + `OR codigo`.
- [x] `main.py`: `?meta=1`, `X-Total-Count`.
- [x] `crud.py`: cache em `get_precos_all_ufs`.
- [x] Testes pytest: ranking, código, total, degradação trigram ausente.
- [ ] `/search/expand` (dict) — remanejado para Fase 4 (requer LLM/Ollama).

### Fase 2 — ✅ concluída (2026-08-14)
- [x] `api/search.py`: pipeline camadas 1-4 + RRF.
- [x] `api/main.py`: `/search`, `/search/suggest`, `/search/related`.
- [x] `api/crud.py`: `usado_em` + related (Jaccard), `did you mean`.
- [ ] Kong `plans.yaml` tiers.
- [x] Testes pytest + contrato OpenAPI.

### Fase 3 — ✅ concluída (2026-08-14)
- [x] `crud.py`: `_compute_variacao`, `_regional_stats`, tendências enriquecidas (`variacao_periodo`, `media_movel`, `inflacao_acumulada`), `get_cenario`/`get_cenario_spread`/`get_cenario_tendencias`.
- [x] `schemas.py`: `variacao_mensal`/`variacao_pct` em `HistoricoCusto` e `TendenciaClassificacao`; `RegionalStats`, `CenarioComposicao`, `CenarioResponse`.
- [x] `main.py`: `/bi/cenario` (tier_2) + `?meta=1` em `/precos-uf`.
- [x] Testes pytest (`tests/test_bi_enrichment.py`, 11 testes).

### Fase 4 — ✅ concluída (vetorial) 2026-08-14
- [x] Migration `007_embedding_models`: `vector` (try/except), registry `embedding_models`.
- [x] `api/vector_store.py` + Celery `generate_embeddings_task` + beat `generate-embeddings`.
- [x] Compose: `pgvector/pgvector:pg15` (imagem db; dados preservados, UID 999).
- [x] RRF no `/search` (`api/search.py` camada 4); `SEARCH_VECTOR_MODEL=bge_m3`.
- [x] Provider: bge-m3 (1024 dims) via Ollama do notebook `lampbook`, fallback nomic local.
- [x] População: 16.731 embeddings (6.145 insumos + 10.586 composições).
- [x] Testes pytest (unit + integração real: `test_vector_store.py`, `test_search_vector_layer.py`, `test_search_unified_integration.py`).
- [ ] `/search/expand` (dict) — remanescente (requer LLM/Ollama), fora desta fase.
- [ ] MCP tools — remanescente.

## DoD (Definition of Done)

- [x] Testes unitários/integração verdes (`pytest` no repo; integração real no container).
- [x] OpenAPI regenerado sem breaking change nos endpoints legados.
- [x] `curl` manual dos novos endpoints no ambiente stack.
- [x] Docs atualizadas (ADR-006, Spec-Rule, workplan).
- [ ] Kong sincronizado (`plans.yaml`) e MCP atualizado.
- [x] `meta.degraded` reporta corretamente ao desligar vetor/LLM.

## Verificação

```bash
# no host:
cd repos/autosinapi_api && python -m pytest -q
# migrations rodam no container api (alembic upgrade head)
bash automation/scripts/manage_stacks.sh logs autosinapi --tail 100
bash automation/scripts/manage_stacks.sh restart autosinapi
```

## Balanço

**Sprint concluída (Fases 1-4 vetorial) em 2026-08-14.**

- ✅ **Fase 1** trigram GIN + ranking; **Fase 2** `/search` unificado + `/suggest`/`/related`/`usado_em`/`did you mean`; **Fase 3** BI enriquecido (`/bi/cenario`, variação, spread regional, tendências); **Fase 4** vetorial (pgvector + RRF).
- **Fixes:** bug `UndefinedColumn` no `/search` (branch insumo/composição) corrigido com testes de integração real (23 passed no container).
- **Infra:** db migrado para `pgvector/pgvector:pg15` (dados preservados, backup `pg_dump` 132M); extension `vector 0.8.6`.
- **População:** 16.731 embeddings bge-m3 (6.145 insumos + 10.586 composições; ~20 min via Celery worker).
- **Busca híbrida:** `vector=on` → `providers: [trigram, vector]`, `degraded: []`; RRF reordena por relevância semântica; degrada graciosamente.
- **Testes:** host 221 passed / 4 ambiental (Postgres não exposto no host) / 11 skipped; container integração real 23 passed.
- **Remanescente:** `/search/expand` (LLM/Ollama) e MCP tools — não bloqueiam a entrega.
- **Docs:** ADR-006, STORY-SRC-004, EPIC (Fase 4 ✅), README atualizados.