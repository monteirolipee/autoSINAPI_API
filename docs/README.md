# 🚀 autoSINAPI API — Documentação do Core API

Bem-vindo à documentação do **autoSINAPI API**, a API RESTful mínima e open-source (GPLv3) baseada em FastAPI para expor dados, preços, composições e inteligência de negócio (BI) da base SINAPI.

---

## 🗺️ Mapeamento do Bounded Context (DDD)

A API fornece a camada de entrega (Delivery Layer) dos dados processados pelo ETL.

*   **Lógica Core (Domain):** Estrutura de busca textual, inteligência analítica (BOM, ABC, HH, Produtividade).
*   **Portas de Entrada (Inbound Ports):** Endpoints HTTP públicos (ex: `/api/v1/public/insumos`), rotas de BI.
*   **Portas de Saída (Outbound Ports):** Repositório de dados via banco de dados relacional e conexões Redis.

---

## 📂 Índice da Documentação (Template Unificado)

Navegue pelos arquivos da especificação técnica local:

1.  **[Requisitos do Produto (prd.md)](./prd.md):** Especificação funcional da API, histórico de retificações e rastreabilidade de dados.
2.  **[Arquitetura Híbrida MVC-Hexagonal (architecture.md)](./architecture.md):** Divisão de pacotes, controllers (FastAPI), interfaces (Ports) e conexões do banco de dados (Adapters).
3.  **[Regras de Rastreabilidade (data_traceability_rules.md)](./data_traceability_rules.md):** Políticas de inserção (UPSERT), colunas de auditoria obrigatórias e tracking de retificações da Caixa.
4.  **[Decisões de Arquitetura (adrs/)](./adrs/):**
    *   **[ADR 003 — Transição para Programação Assíncrona](./adrs/003-asyncpg-transition.md):** Decisão sobre adoção de drivers `asyncpg` e concorrência massiva.
    *   **[ADR 004 — Busca Textual Otimizada com GIN e Trigram](./adrs/004-trigram-gin-search.md):** Abandono de `ILIKE` simples por busca de similaridade performática.
4.  **[Agilidade e Histórico (agile/)](./agile/):**
    *   **[Sprint - Enriquecimento de API](./agile/SPRINT_ENRIQUECIMENTO.md)**
    *   **[Sprint - Cronograma de Trabalho (WorkPlan)](./agile/WorkPlan.md)**
5.  **[Loops de Qualidade (loops/)](./loops/):**
    *   **[Audit Report — Plano de Refatoração](./loops/AUDIT_AND_REFACTOR_PLAN_20260518.md)**
    *   **[Review Report — Modernização](./loops/FINAL_MODERNIZATION_REPORT_20260518.md)**
    *   **[Review Report — Resolução de Gargalos](./loops/URGENT_SERVER_OVERLOAD_FIX.md)**
