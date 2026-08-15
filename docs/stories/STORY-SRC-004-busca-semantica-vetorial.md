# STORY-SRC-004 — Busca Semântica Vetorial (pgvector + RRF)

> Relacionado: EPIC-GOOGLE-POWERBI-SINAPI (Fase 4), ADR-006.
> Status: Concluída (2026-08-14) — parte vetorial; `/search/expand` LLM e MCP tools remanescentes.

## Objetivo
Adicionar a camada 4 do pipeline de busca: embeddings vetoriais distribuídos por modelo
(pgvector), geração via Celery com fallback de provider e fusão RRF com o ranking trigrama — busca semântica "Google do SINAPI" com degradação graciosa.

## Aceite
- [x] Migration `007_embedding_models`: registry `embedding_models` + `CREATE EXTENSION vector` tolerante (degradação se imagem sem pgvector).
- [x] Imagem do banco `pgvector/pgvector:pg15` (substitui `postgres:15-alpine`; dados em `./data/postgres` preservados, UID 999).
- [x] `api/vector_store.py`: DDL dinâmico por modelo, `EmbeddingProvider` (bge-m3 no notebook `lampbook` → fallback nomic local), upsert em lotes, busca cosine `<=>`, `refresh_row_count`.
- [x] Celery `generate_embeddings_task(model_slug, tipo_items)` + beat `generate-embeddings` (diário 04:00 UTC).
- [x] `/search` híbrido: RRF trigrama+vetorial via `vector=on`; `SEARCH_VECTOR_MODEL=bge_m3` → `vec_1024_bge_m3`.
- [x] População: 16.731 embeddings (6.145 insumos + 10.586 composições).
- [x] Testes: `tests/test_vector_store.py` (9), `tests/test_search_vector_layer.py` (7), integração real no container.
- [x] `meta.degraded` reporta `vector` quando provider/extensão fora (sem 5xx).

## Tasks
- [x] Migration `007_embedding_models`.
- [x] Compose: troca da imagem do db + chown do volume (UID 70→999) + backup `pg_dump`.
- [x] `api/vector_store.py` + settings de embedding (`EMBEDDING_*`, `SEARCH_VECTOR_MODEL`).
- [x] Celery: task + beat schedule.
- [x] Camada 4 RRF em `api/search.py` com degradação graciosa.
- [x] População dos embeddings em produção (20 min).

## Arquivos
`alembic/versions/007_embedding_models.py`, `api/vector_store.py`, `api/search.py`,
`api/tasks.py`, `api/celery_config.py`, `api/config.py`, `stacks/autosinapi/compose.yaml`, `tests/`.