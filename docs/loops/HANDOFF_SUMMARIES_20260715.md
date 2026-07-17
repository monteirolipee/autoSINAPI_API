# Handoff: Summaries Explícitos — STORY-API-002

**Data:** 15 de Julho de 2026
**Epic:** EPIC-AUTOSINAPI-AUDIT
**Sprint:** SPRINT 1 — Alinhamento OpenAPI
**Stack:** SistemaServerLight (SSL)

---

## 1. Auditoria (Estado Anterior)

Nenhum dos 22 endpoints em `api/main.py` declarava `summary` no decorador.
O FastAPI derivava o `summary` automaticamente da primeira linha do docstring,
o que viola a **SPEC-RULE Regra 2.1** (summary explícito é obrigatório).

**Problema:** Sem `summary` explícito, não há garantia de formato nem de
tamanho padronizados; a documentação Swagger fica dependente da redação dos
docstrings e não é auditável como conformidade.

**Arquivos afetados:**
- `repos/autosinapi_api/api/main.py` (22 endpoints)

---

## 2. Handoff (O Que Foi Feito)

### 2.1 Implementação

Conforme **SPEC-RULE Regra 2.1** + **GUIDE seção 2.1.1**, todo endpoint recebeu
o argumento nomeado `summary="Verbo + objeto + complemento"` (≤ 80 chars) como
parâmetro explícito do decorador, imediatamente após `tags`:

| # | Endpoint | summary |
|---|----------|---------|
| 1 | `GET /health` | `Verificar health check da API` |
| 2 | `GET /stats` | `Obter estatísticas do banco de dados` |
| 3 | `GET /filters` | `Obter filtros dinâmicos disponíveis` |
| 4 | `POST /admin/populate-database` | `Disparar população da base de dados` |
| 5 | `GET /admin/tasks/{task_id}` | `Verificar status de tarefa Celery` |
| 6 | `GET /` | `Exibir mensagem de boas-vindas` |
| 7 | `GET /insumos/{codigo}` | `Consultar insumo por código e contexto` |
| 8 | `GET /insumos` | `Buscar insumos por descrição` |
| 9 | `GET /composicoes/{codigo}` | `Consultar composição por código e contexto` |
| 10 | `GET /composicoes` | `Buscar composições por descrição` |
| 11 | `GET /bi/composicao/{codigo}/bom` | `Obter Bill of Materials da composição` |
| 12 | `GET /bi/composicao/{codigo}/hora-homem` | `Calcular hora-homem da composição` |
| 13 | `POST /bi/curva-abc` | `Calcular curva ABC de insumos` |
| 14 | `GET /bi/composicao/{codigo}/otimizar` | `Obter candidatos para otimização` |
| 15 | `GET /bi/item/{tipo_item}/{codigo}/historico` | `Obter histórico de custo do item` |
| 16 | `GET /bi/item/{tipo_item}/{codigo}/manutencoes` | `Obter histórico de manutenções do item` |
| 17 | `GET /bi/audit/{tipo_item}/{codigo}` | `Obter trilha de auditoria do item` |
| 18 | `POST /bi/curva-abc/por-classificacao` | `Calcular curva ABC por classificação` |
| 19 | `GET /bi/tendencias/por-classificacao` | `Obter tendências por classificação` |
| 20 | `GET /bi/item/{tipo_item}/{codigo}/precos-uf` | `Obter preços do item em todas UFs` |
| 21 | `GET /bi/composicao/{codigo}/produtividade` | `Obter análise de produtividade` |
| 22 | `GET /bi/insumo/{codigo}/onde-usado` | `Obter composições que usam o insumo` |

Total: **22 endpoints** modificados. Todos os `summary` ≤ 80 chars e no formato
`Verbo (infinitivo) + objeto + complemento`.

### 2.2 TDD

| Fase | Resultado |
|------|-----------|
| 🔴 RED | `test_all_routes_have_explicit_summary` e `test_summary_format_verb_object` falham (nenhum decorador com `summary=` explícito; o runtime `summary` passava por derivar do docstring) |
| 🟢 GREEN | 3 testes passam (22 endpoints corrigidos) |

`tests/test_endpoint_summaries.py` — validação em duas camadas:
- **AST** (`_route_decorators`): inspeciona o código-fonte de `api/main.py` e
  garante que **todo** decorador de rota (`@app.get/post/...`) declara o
  argumento nomeado `summary=` — isto detecta a ausência de summary *explícito*,
  que o `summary` derivado do docstring mascararia em runtime.
- **OpenAPI runtime**: garante que o `summary` resultante tem ≤ 80 chars
  (`test_summary_max_length_80`) e começa com verbo no infinitivo + objeto
  (`test_summary_format_verb_object`).

Regressão: `tests/test_tier_tags.py` (STORY-API-001) segue 4/4 — 7 testes passam
no total.

### 2.3 Contrato de Integração

| Camada | O que muda |
|--------|-----------|
| **API** (`main.py`) | cada decorador de rota tem `summary=` explícito |
| **Stack** (`stacks/autosinapi/`) | Nada — metadata da API, sem acoplamento com Kong |
| **SSL** | Nada — sem acoplamento |
| **ETL** (`AutoSINAPI/`) | Nada — fora de escopo |

---

## 3. Critérios de Aceitação

- [x] 100% dos endpoints têm `summary` explícito ≤ 80 chars
- [x] Formato: `Verbo + objeto + complemento`

Verificação em runtime (API ao vivo): 22 endpoints, 0 sem `summary`, 0 acima de 80 chars.

---

## 4. Próximos Passos (Sprint 1)

| Story | Descrição | Prioridade |
|-------|-----------|------------|
| STORY-API-003 | Schemas Pydantic para endpoints POST | Alta |
| STORY-API-004 | Exemplos consistentes (`example` singular) | Alta |
| STORY-API-005 | Documentação consolidada de auth e erros | Média |

---

## 5. Referências

| Documento | Path |
|-----------|------|
| STORY | `stacks/autosinapi/docs/coordination/STORY-audit.md` (linhas 107-121) |
| SPEC-RULE | `stacks/autosinapi/docs/coordination/SPEC-RULE-audit.md` (Regra 2.1) |
| GUIDE | `stacks/autosinapi/docs/coordination/GUIDE-development.md` (seção 2.1.1) |
| Testes | `repos/autosinapi_api/tests/test_endpoint_summaries.py` |
| Handoff anterior | `repos/autosinapi_api/docs/loops/HANDOFF_TIER_TAGS_20260715.md` |
