# ADR 004 — Busca Textual Performática com Trigramas e Índices GIN

## Status
Implementado (migration `006_search_trigram_gin`, 2026-08-14)

## Contexto
Um dos casos de uso principais da API do AutoSINAPI é a busca textual rápida por insumos e composições (ex: "cimento portland", "tijolo cerâmico"). 
Atualmente, as buscas usam o operador `ILIKE '%query%'` do PostgreSQL. Em tabelas volumosas, isso força o banco a executar um *Sequential Scan* (varredura completa da tabela em disco), impedindo o uso de índices B-Tree tradicionais. Sob alta carga de requisições, isso consome 100% de I/O e CPU do servidor de banco, gerando latências de consulta superiores a 200ms e alto desperdício de energia.

## Decisão
Adotar índices baseados em **trigramas e operadores GIN (Generalized Inverted Index)**:
1.  Habilitar as extensões `pg_trgm` e `unaccent` no PostgreSQL via migration do Alembic.
2.  Criar o índice GIN `idx_insumos_busca_gin` na coluna `descricao` aplicando as funções:
    ```sql
    CREATE INDEX idx_insumos_busca_gin ON insumos USING gin (unaccent(descricao) gin_trgm_ops);
    ```
3.  Modificar a query no `crud.py` para usar similaridade de texto trigrama (operador `%`) ou similaridade `unaccent(descricao) ILIKE unaccent(:query)` casando com o índice.

## Consequências
*   **Positivas:**
    *   **Performance:** Latência de busca reduzida de ~200ms para < 10ms (Index Scan em vez de Seq Scan).
    *   **Inteligência de Busca:** A busca passa a tolerar erros de digitação e acentuação de forma nativa.
    *   **Eficiência Computacional:** Redução massiva de leituras em disco e esforço de CPU do PostgreSQL.
*   **Negativas:**
    *   Índices GIN ocupam mais espaço em disco e aumentam ligeiramente o tempo de escrita durante inserções (mas como o SINAPI é atualizado apenas uma vez por mês via ETL, esse impacto é irrelevante).
