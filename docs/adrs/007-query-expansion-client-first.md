# ADR 007 — Query Expansion Client-First com Fallback Server (LLM)

## Status
Aprovado

## Contexto
Para melhorar assertividade da busca ("Google do SINAPI"), consultas devem ser
**expandidas/enriquecidas**: sinônimos do domínio AEC ("cim" → "cimento",
"tijolo ceramico" → incluir "bloco ceramico"), normalização de acentos e sugestões
"você quis dizer". Um LLM oferece a melhor expansão, mas adiciona latência, custo
e dependência. O browser pode expandir instantaneamente sem rede.

## Decisão
**Expansão em duas camadas com fallback:**

1. **Client-first (sempre, instantâneo)** — módulo `synonyms.ts` no webapp:
   - normalização `unaccent` local;
   - dicionário de sinônimos/homonímia do domínio AEC (curated);
   - mapa classificação ↔ termos (ex.: "CONCRETO" ↔ "concreto", "traço");
   - fuzzy leve via prefixo. Zero rede, zero custo.
2. **Fallback server (`GET /api/v1/public/search/expand?q=`)**:
   - **(a) `provider: "dict"`** — sinônimos + `similarity()` trigrama ("did you mean") no servidor (rápido, determinístico);
   - **(b) `provider: "llm"`** — modelo local pequeno (Ollama `qwen3:0.6b`/`gemma3:1b`) via LiteLLM/Ollama, **timeout 800ms**, cache Redis TTL 24h, ativado por env `SEARCH_LLM_EXPAND_ENABLED`;
   - **(c)** falha/timeout → `provider: null` + `degraded: ["expand"]`. **Nunca** bloqueia a resposta principal.
3. **Fluxo webapp**: aplica expansão client sempre; se `results.length < threshold`,
   chama `/search/expand` **assíncrono** (não bloqueia render) e re-executa se vierem termos novos.

## Consequências
- **Positivas**: UX instantânea; latência controlada; sem lock-in de LLM; custo zero por padrão (LLM off).
- **Negativas**: dicionário manual precisa manutenção; LLM local pode devolver termos fora do domínio (mitigado por validação contra o léxico da base).
- **Riscos**: prompt-injection em `q` → o LLM só **extrai** termos (prompt fixo), nunca executa ação; resultado validado contra léxico.

## Alternativas Consideradas
1. Apenas dicionário server — rejeitada: perde "did you mean" e sinônimos melhores.
2. Apenas LLM — rejeitada: latência/custo e indisponibilidade quebram UX.
3. Embeddings client via transformers.js — rejeitada por ora (peso no bundle); mantida como feature-flag futura.