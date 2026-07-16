# Como Contribuir com o AutoSINAPI

Ficamos muito felizes com seu interesse em contribuir! Este documento fornece as diretrizes para garantir que o processo de desenvolvimento seja o mais coerente, coeso, compatível e sustentável possível.

---

## 📖 Filosofia de Desenvolvimento: Document-First (DDD)

Adotamos a metodologia **Document-Driven Development (DDD)** como principal fonte de verdade:
1. **Nenhum código é escrito sem documentação prévia:** A documentação em `docs/` de cada projeto é o artefato primário.
2. **Definição prévia de ADRs:** Qualquer mudança de arquitetura deve ser registrada em um documento ADR (Architecture Decision Record) local antes de iniciar a escrita de código.
3. **RalphLoops de Qualidade:** Cada ciclo de desenvolvimento deve passar por:
   * **Audit (Auditoria):** Mapeamento do estado atual e identificação de falhas/gaps.
   * **Handoff (Entrega):** Documentação explícita de novos contratos de Portas & Adaptadores.
   * **Review (Revisão):** Validação técnica das decisões arquiteturais tomadas.

---

## 🛠️ Nomenclatura de Branches (Git)

Adotamos um fluxo de trabalho baseado no Git Flow simplificado.

-   **`main`**: Contém o código estável e de produção.
-   **`develop`**: Branch principal de desenvolvimento.
-   **`feature/<nome-da-feature>`**: Para novas funcionalidades (ex: `feature/analise-de-impacto`).
-   **`fix/<nome-da-correcao>`**: Para correções de bugs (ex: `fix/query-performance-insumos`).
-   **`hotfix/<descricao-curta>`**: Para correções críticas em produção.
-   **`docs/<descricao-curta>`**: Para atualizações da documentação.

---

## 📝 Mensagens de Commit (Rastreabilidade por Badges)

Para manter os commits claros e vinculados aos objetivos ágeis do projeto, as mensagens devem seguir a estrutura:

`[tipo]([escopo]): [[EPIC]] [[SPRINT]] [[STORY]] [comentário]`

*   **`[tipo]`**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.
*   **`[escopo]`**: Onde a mudança ocorreu (ex: `etl`, `api`, `gateway`, `infra`).
*   **`[EPIC]`**: Código/identificador do Epic ágil (ex: `CORE-API`, `ETL-PERF`, `SAAS-BILL`).
*   **`[SPRINT]`**: Número ou código da Sprint (ex: `SPRINT-01`).
*   **`[STORY]`**: Identificador da User Story ou Task (ex: `US-02`).

### Exemplo Real de Commit:
```bash
git commit -m "feat(api): [CORE-API] [SPRINT-01] [US-02] converter conexao sqlalchemy para assincrona com asyncpg"
```

---

## 📦 Estrutura dos Repositórios (Toolkit Submodule)

O core de processamento de dados (`AutoSINAPI/`) é um **submódulo Git** vinculado ao repositório [AutoSINAPI](https://github.com/LAMP-LUCAS/AutoSINAPI).

- **Desenvolvimento de ETL:** Deve ser commitado e enviado para o repositório do Toolkit (`AutoSINAPI/`).
- **Desenvolvimento da API:** Deve ser commitado no repositório `autosinapi_api`.
- **Independência:** Cada repositório mantém sua própria pasta `docs/` seguindo o template padrão local para manter a coesão sem acoplar os contextos.
- **Sincronia:** Se você atualizar o Toolkit, envie o PR correspondente no submódulo e depois execute o commit de atualização do ponteiro do submódulo neste repositório.

---

## 🔄 Geração da OpenAPI Spec (STORY-INFRA-004 / ADR-010)

A spec versionada (`docs/openapi.yaml`) é o **SSOT** e vive no repo da **STACK**
(`stacks/autosinapi/`), não aqui. A separação é deliberada:

- **Este repo (API)** possui a *lógica de geração*: `scripts/generate_openapi.sh`
  (extrai `/openapi.json` do runtime e converte para YAML idempotente) e o teste
  contratual `tests/test_openapi_generation.py` (TDD, valida SPEC-RULE 1.1/2.1/2.2/2.4/2.5/2.6).
- **Repo da STACK** orquestra a geração em CI (`.github/workflows/openapi-generation.yml`)
  e valida com `.spectral.yaml` (Regra 6.1, bloqueante) antes de versionar o SSOT.

**Segredos:** `AUTOSINAPI_STACK_APP_TOKEN` (GitHub App de escopo mínimo), `API_REPO`
e `API_REF` são propriedade do repo da STACK — **não** deste repo. A API é clonada
em modo read-only pelo workflow da STACK. Não adicione PAT de escrita da STACK
aqui.

**Local (dev):** para regenerar o SSOT manualmente a partir de um container da API
em execução:
```bash
API_CONTAINER=autosinapi_api bash scripts/generate_openapi.sh <caminho>/docs/openapi.yaml
```

---

## Submetendo Alterações

1. Desenvolva as alterações em sua branch local (`git checkout -b feature/minha-feature`).
2. Atualize o arquivo respectivo em `docs/` antes ou durante o desenvolvimento.
3. Faça o commit seguindo a convenção de badges acima.
4. Envie as alterações para o seu fork (`git push origin feature/minha-feature`).
5. Abra um **Pull Request (PR)** para a branch `develop` do repositório correspondente.

Obrigado por ajudar a construir a autoSINAPI!
