# Audit — Motor de Busca e BI (2026-08-14)

> Auditoria do estado atual dos endpoints de busca e BI da AutoSINAPI API,
> identificando lacunas para a evolução rumo ao "Google do SINAPI" e
> "PowerBI do SINAPI". Serviu de entrada para o EPIC-GOOGLE-POWERBI-SINAPI.

## Escopo

- `repos/autosinapi_api`: `api/crud.py`, `api/main.py`, `api/schemas.py`, `alembic/versions/`.
- Banco `sinapi` (PostgreSQL 15): volumerias e índices reais.
- `repos/mundoaec`: `SearchInsumo.astro`, `search-controller.ts`, `sinapi_http_adapter.ts`.

## Evidências coletadas

| # | Observação | Onde |
|---|-----------|------|
| A1 | Busca usa apenas `ILIKE '%q%'` na `descricao`; `ORDER BY descricao` alfabético | `crud.py:82-98`, `crud.py:127-143` |
| A2 | Extensões `pg_trgm` e `unaccent` **não instaladas**; sem índice GIN | `pg_extension` vazio; ADR-004 aprovado mas não implementado |
| A3 | `q` numérico não casa `codigo` → **busca por código inexistente** | `crud.py` (only ILIKE) |
| A4 | Busca não retorna `total`; paginação sem metadados server-side | `crud.py` / `main.py` |
| A5 | `get_precos_all_ufs` sem `@cache_result` (inconsistente c/ demais BI) | `crud.py:389` |
| A6 | Sem relações semânticas: sem trigrama, vetor, "relacionados", sinônimos | código |
| A7 | Webapp pagina client-side sobre `limit=100` fixo; `skip/limit` nunca enviado | `search-controller.ts`, `sinapi_http_adapter.ts:166` |
| A8 | Webapp não detecta código numérico na busca | `SearchInsumo.astro` |
| A9 | BI endpoints fortes, mas faltam métricas: variação %, spread regional, inflação acumulada, cenário agregado | `crud.py` BI section |
| A10 | Vetorização ausente; infra disponível: Ollama (`nomic-embed-text` 768d, `bge-m3` 1024d), LiteLLM, Redis | `docker ps` |

## Volume do banco (fonte do dimensionamento)

- `insumos`: 6.333 | `composicoes`: 10.737 | `precos_insumos_mensal`: 4.790.109 (17 competências, 27 UFs).

## Riscos identificados

- Busca textual em volume de 4,7M linhas de preço é **seq scan** sob carga (ADR-004 já previa).
- Mudança de contrato dos endpoints legados quebraria demo, MCP e webapp → **preservar shape de array** nos endpoints atuais; envelope novo apenas em `/search`.
- Adicionar extensões vetoriais pode falhar se imagem do banco não suportar → **degradação graciosa obrigatória**.

## Verificação (comandos)

- `docker exec autosinapi_db psql -U admin -d sinapi -t -c "SELECT indexname FROM pg_indexes WHERE tablename IN ('insumos','composicoes');"`
- `docker exec autosinapi_db psql -U admin -d sinapi -t -c "SELECT extname FROM pg_extension;"`

## Status

Documentado. Ações no EPIC-GOOGLE-POWERBI-SINAPI e Sprint de implementação.