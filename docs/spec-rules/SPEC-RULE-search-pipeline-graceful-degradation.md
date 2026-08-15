# SPEC-RULE — Search Pipeline com Degradação Graciosa

> Regra de implementação do pipeline de busca em camadas (ADR-005/006/007).
> Aplicável a `api/crud.py`, `api/main.py`, `api/vector_store.py`. Update: 2026-08-14.

## 1. Contrato de resposta do envelope (novos endpoints `/search*`)

```
data:  array de itens
meta:
  total          int
  page           int (1-indexed)
  page_size      int
  providers:
    ranking      "trigram" | "iliq"        (camada usada para rankear)
    vector       "<slug>" | null           (tabela vetorial consultada)
    expansion    "dict" | "llm" | null
  degraded       string[]                  (lista de camadas que falharam)
```

## 2. Endpoints legados (sem breaking change)

- `/api/v1/public/insumos` e `/composicoes` mantêm o **array** de retorno.
- Metadados opcionais: `?meta=1` retorna o envelope; header `X-Total-Count` **sempre presente**.

## 3. Camadas — obrigações

### Camada 1 (ILIKE baseline) — OBRIGATÓRIA
- Sempre retorna resultados; nunca lança. `unaccent(descricao) ILIKE unaccent(:q)`.

### Camada 2 (Trigram) — OPCIONAL, preferida
- Usar `similarity()` para ordenar e `word_similarity()` para score de prefixo.
- Retornar campo `score` (0..1) em cada item.
- Se a extensão não estiver disponível, capturar e degradar para Camada 1 (`providers.ranking="iliq"`).

### Camada 3 (Relacional) — endpoints `/search/related` e campo `usado_em`
- `usado_em`: reutilizar `get_onde_usado` (DRY) → top 5 + `total`.
- `related`: sobreposição de insumos via `vw_composicao_itens_unificados`;
  Jaccard `|A∩B| / |A∪B|`, limiar configurável (default 0.3), top 5.
- Degrada: se nenhum relacionado relacional, tentar vetorial (cosseno) e então `[]`.

### Camada 4 (Vetorial) — OPCIONAL
- Somente se `SEARCH_VECTOR_MODEL` resolvo para uma tabela existente no registry.
- Fusão com trigrama via **Reciprocal Rank Fusion** (k=60): `score = Σ 1/(k+rank)`.
- Query: `embedding <#> :q_embedding` (inner product, pgvector) ordena por `1 - (embedding <#> q)`.

### Camada 5 (Expansão) — OPCIONAL
- `GET /search/expand?q=`: tenta dict (sinônimos + `similarity`) → LLM (env-flag, timeout 800ms, cache 24h).
- Resposta: `{ terms: [...], provider: "dict"|"llm"|null, degraded: [] }`.

## 4. Regras transversais

- **Nunca 5xx** por falha de camada opcional → `try/except` local + `meta.degraded`.
- **Cache**: camadas 2-5 usam `@cache_result`/Redis com TTL (3600s busca, 86400s BI).
- **Timeouts**: LLM 800ms; vetor 500ms (query indexada).
- **DRY**: centralizar lógica nova em `api/search.py` e `api/vector_store.py`;
  `crud.py` mantém as queries puras.
- **TDD**: cada camada tem teste de unidade com cenário de degradação simulada
  (monkeypatch de extensão/modelo indisponível).

## 5. Segurança

- `q` é string de busca: escapar via bind parameters (`:q`), nunca f-string.
- Prompt do LLM fixo (extração de termos), sem executar conteúdo de `q`.
- Tabelas dinâmicas `vec_<model>`: slug validado por regex `^vec_\d+_[a-z0-9_]+$`.