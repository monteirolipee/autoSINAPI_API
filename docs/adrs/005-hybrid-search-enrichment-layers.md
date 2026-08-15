# ADR 005 — Busca Híbrida em Camadas com Degradação Graciosa

## Status
Aprovado

## Contexto
O EPIC-GOOGLE-POWERBI-SINAPI exige busca relevante ("Google do SINAPI") sem
lock-in e sem quebrar consumidores existentes (demo, MCP, webapp). Busca textual
pura (`ILIKE %q%`) é lenta e irrelevante; busca vetorial depende de infra
(`pgvector`/Ollama) que pode estar indisponível. Precisamos de um pipeline que
**sempre responda**, enriquecendo quando possível e degradando com transparência
quando não.

## Decisão
Adotar **pipeline de busca em 5 camadas**, cada uma opcional e encapsulada, com
degradação graciosa explícita:

1. **Camada 1 — ILIKE baseline**: `unaccent(descricao) ILIKE unaccent(:q)`. Sempre ativa, sem dependências.
2. **Camada 2 — Trigrama GIN**: ranking via `similarity()` / `word_similarity()` usando o índice GIN do ADR-004. Ativa quando a extensão está instalada.
3. **Camada 3 — Relacional**: "composições relacionadas" por sobreposição de insumos (Jaccard sobre `vw_composicao_itens_unificados`) e `usado_em` (reuso de `get_onde_usado`).
4. **Camada 4 — Vetorial**: `cosine` contra a tabela do modelo configurado (`SEARCH_VECTOR_MODEL`). Se ausente/vazia → ignora.
5. **Camada 5 — Query expansion**: dicionário client → LLM server (`/search/expand`). Se LLM falhar/timeout → dicionário apenas; se ambos ausentes → `null`.

Contrato de resposta **estável**:
```json
{
  "data": [...],
  "meta": {
    "total": 137, "page": 1, "page_size": 20,
    "providers": {"ranking": "trigram|iliq", "vector": "vec_1024_bge_m3|null", "expansion": "dict|llm|null"},
    "degraded": []
  }
}
```
- Novos endpoints (`/search`, `/search/suggest`, `/search/related`, `/search/expand`, `/bi/cenario`) usam envelope.
- Endpoints legados mantêm shape de **array**; metadados opcionais via `?meta=1` e header `X-Total-Count` (não-breaking).
- Cada camada envolve `try/except` + timeout e **nunca propaga erro** — registra em `meta.degraded`.

## Consequências
- **Positivas**: disponibilidade alta (endpoint nunca 5xx por camada opcional), sem lock-in, rollback de modelo transparente, boa UX (o cliente mostra "resultados enriquecidos").
- **Negativas**: dois formatos de resposta (legado array vs novo envelope) exigem mapeamento no cliente; custo de RRF marginal.
- **Riscos**: mitigados — a fusão RRF adiciona <10ms; cache Redis nas camadas 4-5.

## Alternativas Consideradas
1. Substituir contratos legados por envelope único — rejeitada (breaking change).
2. Vetorial como camada obrigatória — rejeitada (lock-in).
3. LLM como camada obrigatória — rejeitada (latência/custo).