# Handoff: Tags de Tier nos Endpoints — STORY-API-001

**Data:** 15 de Julho de 2026
**Epic:** EPIC-AUTOSINAPI-AUDIT
**Sprint:** SPRINT 1 — Alinhamento OpenAPI
**Stack:** SistemaServerLight (SSL)

---

## 1. Auditoria (Estado Anterior)

Nenhum endpoint em `main.py` declarava tags de tier. Usavam apenas tags conceituais (`Health`, `Public`, `Insumos`, `Business Intelligence`, etc.).

**Problema:** Swagger UI não agrupava endpoints por tier de plano. Desenvolvedor integrador não conseguia identificar visualmente quais endpoints pertencem a cada plano (Starter/Pro/Business).

**Arquivos afetados:**
- `repos/autosinapi_api/api/main.py` (22 endpoints)

---

## 2. Handoff (O Que Foi Feito)

### 2.1 Implementação

Conforme **SPEC-RULE Regra 1.1** + **GUIDE seção 2.1.1**, toda tag conceitual foi prefixada com `tier_X` como primeiro elemento:

| Tier | Categoria | Endpoints | Tag final |
|------|-----------|-----------|-----------|
| tier_1 | Health | `/health` | `["tier_1", "Health"]` |
| tier_1 | Public | `/stats`, `/filters` | `["tier_1", "Public"]` |
| tier_1 | Admin | `/admin/populate-database`, `/admin/tasks/{task_id}` | `["tier_1", "Admin"]` |
| tier_1 | Root | `/` | `["tier_1", "Root"]` |
| tier_1 | Insumos | `/insumos`, `/insumos/{codigo}` | `["tier_1", "Insumos"]` |
| tier_1 | Composições | `/composicoes`, `/composicoes/{codigo}` | `["tier_1", "Composições"]` |
| tier_2 | Business Intelligence | 12 endpoints `/bi/*` | `["tier_2", "Business Intelligence"]` |

Total: **22 endpoints** modificados.

### 2.2 TDD

| Fase | Resultado |
|------|-----------|
| 🔴 RED | 4 testes falham (nenhum endpoint com tier tag) |
| 🟢 GREEN | 4 testes passam (22 endpoints corrigidos) |

`tests/test_tier_tags.py` — 4 testes de validação da OpenAPI schema:
- `test_all_endpoints_have_tier_tag_as_first`
- `test_tier_1_classification`
- `test_tier_2_classification`
- `test_admin_and_root_are_tier_1`

### 2.3 Contrato de Integração

| Camada | O que muda |
|--------|-----------|
| **API** (`main.py`) | `tags` agora incluem `tier_X` como primeiro elemento |
| **Stack** (`stacks/autosinapi/`) | Nada — tags são metadata da API, não do Kong |
| **SSL** | Nada — sem acoplamento |

---

## 3. Critérios de Aceitação

- [x] 100% dos endpoints públicos têm `tags` começando com `"tier_1"` ou `"tier_2"`
- [x] Swagger UI agrupa por tier (FastAPI usa `tags[0]` como grupo)

---

## 4. Próximos Passos (Sprint 1)

| Story | Descrição | Prioridade |
|-------|-----------|------------|
| STORY-API-002 | Summaries explícitos (≤ 80 chars) | Alta |
| STORY-API-003 | Schemas Pydantic para endpoints POST | Alta |
| STORY-API-004 | Exemplos consistentes (`example` singular) | Alta |
| STORY-API-005 | Documentação consolidada de auth e erros | Média |

---

## 5. Referências

| Documento | Path |
|-----------|------|
| STORY | `stacks/autosinapi/docs/coordination/STORY-audit.md` (linhas 90-104) |
| SPEC-RULE | `stacks/autosinapi/docs/coordination/SPEC-RULE-audit.md` (Regra 1.1) |
| GUIDE | `stacks/autosinapi/docs/coordination/GUIDE-development.md` (seção 2.1.1) |
| Testes | `repos/autosinapi_api/tests/test_tier_tags.py` |
