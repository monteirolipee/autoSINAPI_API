# ADR 006 — Embeddings Vetoriais Distribuídos por Modelo (pgvector)

## Status
Aprovado — **Implementado (Fase 4, STORY-SRC-004, 2026-08-14)**.

## Evidências de Implementação
- Migration `007_embedding_models` (registry + `CREATE EXTENSION vector` tolerante).
- Imagem do banco: `pgvector/pgvector:pg15` (substituiu `postgres:15-alpine`;
  dados em `./data/postgres` preservados, PG_VERSION 15; ownership ajustado p/ UID 999).
- `api/vector_store.py`: DDL dinâmico centralizado, `EmbeddingProvider` com fallback
  (bge-m3 via Ollama do notebook `lampbook` → nomic-embed-text local), upsert em
  lotes, busca cosine `<=>`, `refresh_row_count`.
- Provider ativo: **bge-m3 (1024 dims)** em `vec_1024_bge_m3` — 16.731 linhas
  (6.145 insumos + 10.586 composições).
- Camada 4 (RRF) em `api/search.py`: `unified_search(vector=on)` combina trigrama +
  vetorial; degrada para `degraded:["vector"]` quando a infra sai do ar.
- Celery: `generate_embeddings_task` + beat `generate-embeddings` (diário 04:00 UTC).
- Testes: `tests/test_vector_store.py`, `tests/test_search_vector_layer.py`,
  `tests/test_search_unified_integration.py` (validação real no banco).

## Contexto
A camada 4 do ADR-005 exige busca semântica vetorial. Diferentes modelos de
embedding produzem vetores de **dimensões diferentes** (ex.: `nomic-embed-text` =
768 dims, `bge-m3` = 1024 dims) e qualidades distintas. Queremos poder **testar
modelos e fazer rollback sem perder dados anteriores**, sem lock-in de modelo.

## Decisão
Modelo de armazenamento **distribuído por modelo**: uma tabela vetorial por modelo.

1. Tabela `embedding_models` (registry):
   ```sql
   CREATE TABLE embedding_models (
     id            SERIAL PRIMARY KEY,
     slug          TEXT UNIQUE NOT NULL,          -- 'vec_1024_bge_m3'
     model_name    TEXT NOT NULL,                 -- 'bge-m3'
     dims          INT NOT NULL,                  -- 1024
     status        TEXT DEFAULT 'ready',          -- queued|embedding|ready|error
     row_count     INT DEFAULT 0,
     created_at    TIMESTAMPTZ DEFAULT now(),
     updated_at    TIMESTAMPTZ DEFAULT now()
   );
   ```
2. Tabela vetorial por modelo (criada dinamicamente, `CREATE TABLE IF NOT EXISTS`):
   ```sql
   CREATE TABLE vec_1024_bge_m3 (
     codigo       INT NOT NULL,
     tipo_item    TEXT NOT NULL,                   -- 'INSUMO' | 'COMPOSICAO'
     embedding    vector(1024) NOT NULL,
     generated_at TIMESTAMPTZ DEFAULT now(),
     PRIMARY KEY (codigo, tipo_item)
   );
   ```
3. Seleção do modelo ativo via env `SEARCH_VECTOR_MODEL=vec_1024_bge_m3`
   (default `vec_1024_bge_m3`). A camada 4 consulta **apenas** a tabela selecionada.
4. Geração via Celery `generate_embeddings_task(model_slug, tipo_items)` usando
   o endpoint `/api/embed` do Ollama; upsert em lotes; atualiza `embedding_models`.
5. Extensão `vector` criada em migration **com try/except**: se a imagem do banco
   não suportar, o registry fica vazio e a camada 4 degrada para trigrama (ADR-005).

## Consequências
- **Positivas**: rollback = trocar `SEARCH_VECTOR_MODEL` (dados preservados); A/B de modelos; sem lock-in; falha de um modelo não afeta outros; geração paralelizável por modelo.
- **Negativas**: duplicação de dados entre modelos (gerar embeddings de novo por modelo custa ~minutos para 17k itens); espaço em disco adicional.
- **Riscos**: tabelas dinâmicas fora de controle do Alembic → mitigado por helper DDL centralizado (`vector_store.py`) e registry.

## Alternativas Consideradas
1. Colunas `embedding` previstas no schema de `insumos`/`composicoes` — rejeitada: trocar modelo exigiria migração destrutiva; um item de tipo só (não permitiria insumo+composição com dimensões distintas no mesmo modelo facilmente).
2. Tabela única com coluna `model_slug` — rejeitada: coluna `vector(n)` tem dimensão fixa; modelos com dims diferentes exigiriam `cast`, degradando performance e clareza.
3. Store externo (redis/faiss) — rejeitada: perde joins SQL e transparência.