---
id: AUDIT-API-autosinapi
type: audit
status: active
date: 2026-07-17
owner: platform
tags: [audit, api, fastapi, security, resilience, autosinapi]
links:
  - "repos/mundoaec/docs/audits/autosinapi/2026-07-17_AUDIT-GERAL.md"
  - "stacks/autosinapi/kong/docs/AUDIT-GATEWAY.md"
  - "repos/autosinapi_api/AutoSINAPI/docs/AUDIT-ETL.md"
  - "stacks/autosinapi/docs/planning/SPEC-018-hexagonal-architecture.md"
---

# 🧩 Auditoria de Orientação — Camada API (autoSINAPI)

> Documento de orientação da camada **API** (open source, `api/`, FastAPI + Celery + Alembic).
> Parte do ecossistema AutoSINAPI auditado em `repos/mundoaec/docs/audits/autosinapi/2026-07-17_AUDIT-GERAL.md`
> (repos independentes; caminho relativo à raiz do SistemaServerLight).
> Segue o padrão MVC-Hexagonal de `docs/architecture.md`. Contém as seções
> **Audit · Epic · Spec-Rule · Sprint · Story** para guiar o desenvolvimento.

---

## 0. Status de Remediação (2026-07-17)

- **P1-C (admin token constant-time / SR-API-2):** DONE — `api/main.py` usa
  `secrets.compare_digest` em `verify_admin_token`; 9 testes (`tests/test_admin_token.py`).
  Commit `12819d4`.
- **P1-A (authz defense-in-depth), P1-B (resiliência DB), P1-C-inputs (P1-C do roadmap mãe):**
  **pendente**.

---

## 1. Audit (API)

### 1.1 Coesão
- Sem ORM/domínio: tabelas referenciadas como **strings interpoladas** em `text()` (`crud.py` via
  `config.get_sandbox_table_name()`). A API não possui modelo de domínio nem `metadata`; tabelas
  centrais são criadas pelo ETL (AutoSINAPI), não pelo alembic da API → alto acoplamento a schema
  que a API não governa.
- `main.py` (~675 linhas) é *god-route-file*: vaza lógica (cálculo de date-range no router,
  `main.py:527-531`; `meses` unbounded). `portal.py` é o único `APIRouter` real. Não há `deps.py`.
- God-files: `main.py` (675) e `crud.py` (525) — manejáveis, mas `main.py` deve ser dividido por
  recurso.

### 1.2 Coerência
- 🔴 **ETL status vocabulary incompatível** (verificado): `api/tasks.py:55` checa
  `== "failed"`, mas o ETL retorna `"FALHA"` → falhas silenciosas, sem retry (ver `repos/autosinapi_api/AutoSINAPI/docs/AUDIT-ETL.md`).
- 🔴 **Colunas `origem_preco`/`percentual_mo` ausentes no alembic** (verificado): lidas em
  `crud.py:62,83,107,128`, escritas pelo ETL, sem migration → 500 em insumo/composição.
- Schema↔response gap: `HistoricoCusto` (`schemas.py:105-111`) declara campos sempre nulos;
  `AuditEvent` (`schemas.py:127-137`) aponta `sinapi_audit_log` (dropada na migration 004) e tem
  `old_values/new_values` hard-coded `NULL`.
- `get_composition_man_hours` (`main.py:464-477`) ignora `uf`/`regime` (diferente dos irmãos BOM).
- Date validation inconsistente: `historico` valida `data_fim` (400), mas `data_referencia` em outros
  endpoints retorna `(None,None)` silenciosamente → 404 em vez de 400.

### 1.3 Resiliência
- 🟠 **Pool de DB não endurecido**: `create_engine` (`database.py:34`) sem `pool_pre_ping`,
  `pool_size`/`max_overflow`/`pool_timeout`, nem statement timeout. Após restart do PG, conexões
  stale até recycle; sob carga o pool pequeno pode esgotar e bloquear threads.
- 🟠 **Sem degradação em outage de DB nos paths de dado**: `crud.py` não tem `try/except`; qualquer
  erro de DB → 500 não tratado. Só `health_check` degrada (retorna 503). Sem handler global.
- 🔴 **Lock ETL Redis `ex=3600` < `task_time_limit=5400`** (`populate_utils.py:42` vs
  `tasks.py:54`): ETL longo pode sobreviver ao lock; segundo ETL para o mesmo período pode iniciar e o
  `finally` (`:67-71`) pode apagar o lock do run mais novo.
- 🟠 **DB host env incorreto**: `populate_utils.py:47` usa `POSTGRES_NAME` (não setado) → host default
  `autosinapi_db` que não resolve (o serviço é `db`). Latente.
- Cache degrada bem (`cache_utils.py` catch Redis → no-cache). Porém **4 clientes Redis separados**
  (`cache_utils`, `tasks`, `populate_utils`, e um morto em `main.py:316`).

### 1.4 Robustez
- ✅ **SQLi: baixo risco** — todo input é parâmetro bound em `sqlalchemy.text()`; identificadores de
  tabela/coluna vêm de config (strings estáticas prefixadas) ou whitelist por igualdade
  (`crud.py:332-373`). Sem interpolação de input do usuário.
- 🟠 **Inputs unbounded** (DoS): `limit` sem teto (`main.py:400,435`, default 100) → `limit=1e8`;
  `codigos: List[int]` unbounded (CTE recursiva/`IN` grande); `meses` unbounded; `q` sem max.
- ✅ Sem `debug=True`/`--reload`; 500 genérico, sem vazamento de traceback.

### 1.5 Compatibilidade
- ✅ Migrations lineares e idempotentes (`001→004`, single head). Obs.: `alembic.ini:3` tem fallback
  hardcoded `admin:admin@autosinapi_db:5432/sinapi` (segredo em config — baixo/médio).
- 🟠 Deps não pinadas (`requirements.txt` nomes nus, incl. `psycopg2-binary` não recomendado p/ prod).
- 🟠 `Dockerfile` embute tooling de debug (`gdb`, `py-spy`, `memray`, `wget`, `procps`) em runtime; sem
  `HEALTHCHECK`; `CMD` single worker sem `--proxy-headers`/`--forwarded-allow-ips`.
- A API **não é autocontida**: 500 até o ETL popular os dados; tabelas centrais pertencem ao ETL.

### 1.6 Segurança
- 🔴 **Sem authorization em app para `/api/v1/public/*`**: authz existe **só** no Kong
  (`main.py:94-99` documenta tiers apenas como doc). Se o Kong for bypassado/mal-configurado, não há
  backstop e os tiers Starter/Pro/Business são ficção. O `kong/kong.yml` do repo expõe
  `public-demo-route` **sem `key-auth`** (só rate-limit demo) — reforça o risco.
- 🟠 Admin token não constant-time: `if token != settings.ADMIN_API_TOKEN` (`main.py:277`) → side-channel
  de timing; levanta 500 se `ADMIN_API_TOKEN` unset (`:270`).
- 🟠 API-key at rest: `portal/me` faz `WHERE k.key_value = :key_value` (`portal.py:36`) — confirmar se
  `saas.api_keys.key_value` é plaintext (o gateway hasheia, mas o `portal.py` consulta `key_value`).
- 🟠 `KONG_ADMIN_LISTEN=0.0.0.0:8001` (`docker-compose.yml:110`) sem auth na mesh externa.
- 🟠 CORS: `ALLOWED_ORIGINS` default `"*"` (`config.py:75`); `allow_credentials=False` para `"*"`, mas
  habilita credentials se origens específicas — incompatível com credenciais + wildcard.
- ✅ Sem segredos hardcoded no `api/`; cache usa `json` (não pickle); sem debug/reload em prod.

---

## 2. Epic (API)

**`EPIC-API-REMEDIATION`** — Tornar a API coesa (domínio/ORM), resiliente (pool+degradação), robusta
(inputs bounded) e com **defense-in-depth de authz** independente do gateway; alinhar contrato de
status e schema com o ETL.

---

## 3. Spec-Rule (API) — regras vinculantes

- **SR-API-1 (Segurança/Coerência):** Todo endpoint de dado em `/api/v1/public/*` **deve** ter um
  backstop de authz em app (ao menos validação de key/tier mínimo), não dependendo só do Kong.
- **SR-API-2 (Segurança):** Comparação de token admin **deve** usar `secrets.compare_digest`; ausência
  de `ADMIN_API_TOKEN` **deve** resultar em 500 controlado (não exception crua).
- **SR-API-3 (Resiliência):** `create_engine` **deve** configurar `pool_pre_ping=True`,
  `pool_size`/`max_overflow`/`pool_timeout` e statement timeout. Paths de dado **devem** ter
  tratamento de erro → 503 em outage de DB (handler global).
- **SR-API-4 (Resiliência):** Lock Redis de ETL `ex` **deve** ser ≥ `task_time_limit`; usar owner/redeem
  seguro no `finally` (evitar apagar lock alheio).
- **SR-API-5 (Robustez):** `limit`, `codigos`, `meses` e `q` **devem** ter teto máximo (ex.: 1000, 200,
  36, 100). Validação de `data_referencia` uniforme (400 em formato inválido).
- **SR-API-6 (Coerência/Schema):** Todo campo em Pydantic schema **deve** ser populado pela query
  correspondente (sem campos sempre-`null`); schemas que apontem tabelas dropadas **devem** ser
  corrigidos.
- **SR-API-7 (Compatibilidade):** `requirements.txt` pinado; remover tooling de debug do runtime Docker;
  adicionar `HEALTHCHECK`; `--forwarded-allow-ips` atrás de proxy.
- **SR-API-8 (Coesão/DDD):** Extrair domínio/ORM das tabelas centrais ou, no mínimo, centralizar
  nomes de tabela em `config` (já feito) e mover lógica de router para services; remover cliente Redis
  morto.

---

## 4. Sprint (API)

### P0 (bloqueadores)
- **Sprint API-P0-A — Contrato ETL↔API:** alinhar enum de status com ETL (SR integra `SR-ETL-1`);
  migration `origem_preco`/`percentual_mo`.
- **Sprint API-P0-B — Lock ETL:** `ex` ≥ `task_time_limit` + redeem seguro (SR-API-4).

### P1
- **Sprint API-P1-A — Authz defense-in-depth:** backstop em `/public/*` (SR-API-1); admin token
  constant-time (SR-API-2).
- **Sprint API-P1-B — Resiliência DB:** pool pre_ping + handler global 503 (SR-API-3); corrigir
  `POSTGRES_NAME` (SR-API-4 latente).
- **Sprint API-P1-C — Inputs bounded:** tetos em `limit/codigos/meses/q` + validação uniforme de datas
  (SR-API-5).

### P2
- **Sprint API-P2-A — Robustez/Qualidade:** pin deps; remover debug tooling; `HEALTHCHECK`;
  `--forwarded-allow-ips` (SR-API-7).
- **Sprint API-P2-B — Coesão:** extrair domínio/schemas sempre-populados (SR-API-6); dividir `main.py`;
  remover Redis morto (SR-API-8).
- **Sprint API-P2-C — CORS:** allowlist explícita em `ALLOWED_ORIGINS` (alinhado ao gateway).

---

## 5. Story (API)

### STORY-API-001 — Backstop de authz em app
- **Como** proprietário de segurança, **quero** que a API valide key/tier mesmo se o Kong falhar,
  **para** que o paywall não seja contornável.
- **Critérios de Aceite:**
  - [ ] Middleware/dependência valida `X-API-KEY` + tier mínimo em `/api/v1/public/*` (exceto demo).
  - [ ] Teste comprova 401 sem key mesmo com Kong ausente.

### STORY-API-002 — Pool e degradação de DB
- **Como** SRE, **quero** pool endurecido e 503 em outage, **para** evitar 500 críticos e conexões stale.
- **Critérios de Aceite:**
  - [ ] `pool_pre_ping=True` + sizing + statement timeout configurados.
  - [ ] Handler global retorna 503 em `OperationalError` de DB.

### STORY-API-003 — Lock ETL seguro
- **Como** DevOps, **quero** que o lock não seja apagado por run vizinho, **para** evitar ETL sobreposto.
- **Critérios de Aceite:**
  - [ ] `ex` ≥ `task_time_limit`; `finally` só libera se dono.
  - [ ] Teste de sobreposição não corrompe lock.

### STORY-API-004 — Inputs bounded
- **Como** defesa, **quero** tetos em parâmetros, **para** evitar DoS por payload massivo.
- **Critérios de Aceite:**
  - [ ] `limit≤1000`, `codigos≤200`, `meses≤36`, `q` com max; 400 em `data_referencia` inválida.

### STORY-API-005 — Schemas coerentes
- **Como** consumidor, **quero** schemas populados, **para** não receber campos nulos inexplicáveis.
- **Critérios de Aceite:**
  - [ ] `HistoricoCusto`/`AuditEvent` populados ou simplificados; sem referência a tabela dropada.
