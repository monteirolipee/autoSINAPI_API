# EPIC — Motor de Busca e BI: "Google do SINAPI" + "PowerBI do SINAPI"

> Status: **Em execução** (Sprint 1). Update: 2026-08-14. Fases 1-3 ✅, Fase 4 vetorial ✅ (QLM/MCP remanescentes).

## Visão

Transformar a AutoSINAPI de uma API de consulta em uma **plataforma de inteligência
de custos**, com busca relevante, semântica e resiliente ("Google do SINAPI") e
análises analíticas ricas ("PowerBI do SINAPI").

## Princípios Arquiteturais (decision drivers)

1. **Degradação graciosa em camadas** — toda camada de enriquecimento é opcional,
   tem timeout/cachê e, se falhar, **degrava** sem quebrar o endpoint. O response
   envelope expõe `meta.providers` e `meta.degraded`.
2. **Vetorial distribuído por modelo** — cada modelo de embedding tem sua própria
   tabela `vec_<dims>_<model>` (ex.: `vec_1024_bge_m3`, `vec_768_nomic_embed_text`),
   registrado em `embedding_models`. Troca de modelo = apontar `SEARCH_VECTOR_MODEL`;
   rollback preserva dados das demais tabelas.
3. **Query expansion client-first com fallback server** — expansão determinística no
   browser antes; servidor (LLM local pequeno) como camada opcional.
4. **Sem lock-in / sem breaking change** — endpoints legados preservam contrato de
   array; os novos (/search, /suggest, /related, /expand, /bi/cenario) usam envelope.
5. **TDD, DDD, DRY** — camadas `crud` → `main`, testes antes, reuso de CTEs e módulos
   existentes (`vw_composicao_itens_unificados`, `get_onde_usado`, `buildUrl`).

## Camadas de enriquecimento (pipeline)

```
Camada 1  ILIKE baseline         -> sempre ativa
Camada 2  Trigrama GIN + unaccent -> ranking por similaridade
Camada 3  Relacional (grafo BOM)  -> "composições relacionadas", usado_em
Camada 4  Vetorial (cosine)       -> RRF (fusão por rank) c/ trigrama
Camada 5  Query expansion         -> dicionário client -> LLM server
```

Cada camada reporta status em `meta.providers`. O contrato nunca muda.

## Entregas (por fase)

### Fase 1 — Fundação de busca
- [x] Migration 006: `pg_trgm` + `unaccent` + índices GIN (implementa ADR-004).
- [x] Ranking por relevância em `/insumos` e `/composicoes` (campo `score`).
- [x] Busca por código (`q` numérico → casa `codigo`).
- [x] `total` + `X-Total-Count`; paginação com metadados (envelope `?meta=1`).
- [x] Cache em `get_precos_all_ufs`.
- [ ] `GET /search/expand` (dicionário → LLM, `provider` + `degraded`). *(move para Fase 4 — requer LLM/Ollama)*

> **Fase 1 — concluída (2026-08-14).** Ver `stories/STORY-SRC-001` e, no webapp,
> `repos/mundoaec/docs/projects/STORY-SRCH-001`.

### Fase 2 — "Google do SINAPI" ✅ (API concluída 2026-08-14; webapp pendente)
- [x] `GET /api/v1/public/search`: unificado (insumo+composição), facets, sort, pagination server-side, `vector=auto|off|model`.
- [x] `GET /api/v1/public/search/suggest`: autocomplete prefixo + trigrama (top 8).
- [x] `GET /api/v1/public/search/related`: "composições relacionadas" (Jaccard BOM) + fallback vetorial.
- [x] Expor `usado_em` no item (reusa `get_onde_usado`).
- [x] `did you mean` via `similarity()`.
- [~] Kong `plans.yaml`: tiers dos novos endpoints (definidos na stack; sync/gitops pendente).
- [ ] Webapp: autocomplete, paginação server-side, badges de enriquecimento.

> **Fase 2 — API concluída (2026-08-14).** Implementado em `api/search.py` (pipeline em camadas),
> `api/crud.py` (suggest, did-you-mean, Jaccard related, usado_em) e `api/main.py` (3 endpoints).
> Testes: `tests/test_search_unified.py` (19 pass). Webapp (`docs/projects/STORY-SRCH-00X`) pendente.

### Fase 3 — "PowerBI do SINAPI" (✅ concluída — 2026-08-14)
- [x] `/historico` + item: `variacao_mensal`, `variacao_pct`.
- [x] `/precos-uf`: `media`, `mediana`, `min`, `max`, `desvio_padrao`, `amplitude`, `uf_mais_barato/cara`.
- [x] `/tendencias`: `variacao_periodo`, `media_movel`, `inflacao_acumulada`.
- [x] `GET /api/v1/public/bi/cenario?codigos=`: BOM+ABC+tendências+spread agregados.
- [x] Schemas Pydantic atualizados (`RegionalStats`, `CenarioResponse`, campos `variacao_*`).
- [ ] Webapp BI: `BiDashboard` com indicadores (integração front).

> **Fase 3 — alteração após primeira implementação:** os endpoints legados `/historico`,
> `/precos-uf` e `/tendencias` **ganharam enriquecimento aditivo** (novos campos no mesmo
> contrato array + envelope `meta` opcional), mantendo compatibilidade. Novos schemas:
> `RegionalStats`, `CenarioResponse`/`CenarioComposicao`, campos `variacao_*`,
> `media_movel`, `inflacao_acumulada`. Endpoint novo: `/bi/cenario` (tier_2).
> Testes: `tests/test_bi_enrichment.py` (11 pass).

### Fase 4 — Semântica vetorial distribuída + Query Expansion (✅ vetorial concluída — 2026-08-14)
- [x] Migration 007: `vector` (try/except), registry `embedding_models`, helper DDL de tabelas por modelo.
- [x] Compose: imagem do banco → `pgvector/pgvector:pg15` (dados preservados, UID 999).
- [x] Celery `generate_embeddings_task(model_slug, tipo_items)` via Ollama `/api/embed`.
- [x] `/search` híbrido com RRF; `SEARCH_VECTOR_MODEL` seleciona tabela.
- [x] População: 16.731 embeddings (bge-m3, 1024 dims).
- [ ] `/search/expand` LLM (ollama small, timeout 800ms, cache 24h), env-flag. *(remanescente)*
- [x] MCP server: tool `sinapi_search` (busca unificada `/search`, multi-termo AND + fallback OR). *(sinapi_search_related/suggest/expand remanescentes)*

## Non-goals (nesta iteração)

- GraphQL; multi-tenancy de preços próprios; i18n; plugin BIM.

## Referências

- ADRs: `004` (trigramas, agora implementado), `005` (camadas), `006` (vetorial distribuído), `007` (query expansion).
- Spec-Rule: `SPEC-RULE-search-pipeline-graceful-degradation`.
- Audit: `audits/2026-08-14_SEARCH-ENHANCEMENT-AUDIT`.
- Sprint: `workplans/SPRINT-SEARCH-GOOGLE-POWERBI`.

## Métricas de sucesso

- Latência busca vetorial+tigrama < 300ms p50 (com cache).
- Busca por código e por texto cobrem >99% das consultas reais.
- Zero breaking change em endpoints legados (pytest de contrato verde).
- Degradação reportada em `meta.degraded` sem `5xx` quando vetor/LLM indisponíveis.