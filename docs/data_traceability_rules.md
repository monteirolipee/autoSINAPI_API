# Regras de Rastreabilidade e Auditoria de Dados (Data Traceability)

Este documento restaura e detalha as regras arquiteturais estritas para garantia de confiabilidade (Reliability) e rastreabilidade (Traceability) dos dados processados pelo AutoSINAPI.

## 1. Problema Histórico
O fluxo antigo do ETL utilizava comandos de `APPEND` ou `INSERT ... ON CONFLICT DO NOTHING` para a carga mensal de preços. Como a Caixa Econômica Federal frequentemente publica planilhas **retificadas** (corrigidas) semanas após a publicação inicial, a abordagem `DO NOTHING` fazia com que o AutoSINAPI ignorasse solenemente os valores corrigidos. Além disso, não havia colunas de log temporal, inviabilizando qualquer auditoria sobre a idade do dado.

## 2. Metadados Obrigatórios (Colunas de Auditoria)
Todas as tabelas de domínio (catálogos e séries temporais) **devem** obrigatoriamente conter as seguintes colunas de rastreabilidade:

| Coluna | Tipo (Postgres) | Descrição | Comportamento no ETL |
| :--- | :--- | :--- | :--- |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Data/hora exata da primeira inserção do registro. | Preenchido com `NOW()` apenas no INSERT inicial. |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | Data/hora da última modificação (retificação). | Atualizado via `EXCLUDED.updated_at` ou trigger no UPSERT. |
| `sinapi_versao`| `VARCHAR(10)` | O mês de referência oficial do arquivo que originou o dado (ex: `2024.12`). | Sempre atualizado no UPSERT. |
| `etl_run_id` | `UUID` | Identificador único da execução do pipeline do ETL. | Sempre atualizado no UPSERT. Permite rollback de execuções com falha. |

## 3. Política de Inserção (UPSERT Mandatório)
* Todo e qualquer comando de persistência no PostgreSQL, orquestrado pelo ETL, deve utilizar a cláusula `ON CONFLICT (chaves_primarias) DO UPDATE`.
* Se um preço ou composição já existir para a chave primária `(codigo, uf, data_referencia, regime)`, o valor **deverá ser sobrescrito** com o novo valor extraído, e a coluna `updated_at` deve ser renovada. 

## 4. Auditoria de Manutenções (Status)
A Caixa também publica o arquivo de "Manutenções", descrevendo se um insumo foi ativado ou inativado.
* O status do item (tabelas `insumos` e `composicoes`) só deve ser alterado após o cruzamento com a última linha temporal da tabela `manutencoes_historico`.
* A API Mínima deve fornecer o endpoint `/api/v1/public/bi/audit/{tipo}/{codigo}` para retornar todo o rastro das colunas de auditoria listadas acima, garantindo a governança técnica e prestação de contas (Accountability).
