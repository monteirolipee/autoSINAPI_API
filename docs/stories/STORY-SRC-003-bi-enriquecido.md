# STORY-SRC-003 — BI Enriquecido: Variação, Spread Regional e Cenário

> Relacionado: EPIC-GOOGLE-POWERBI-SINAPI (Fase 3). Status: Concluída (2026-08-14).

## Objetivo
Transformar os endpoints BI em analíticos: variação mês a mês, estatística regional e cenário orçamentário agregado — "PowerBI do SINAPI".

## Aceite
- [x] `GET /api/v1/public/bi/item/{tipo}/{codigo}/historico` → cada ponto com `variacao_mensal` e `variacao_pct` (vs mês anterior; `null` se sem dado).
- [x] `GET .../precos-uf` → `{uf, valor}` + bloco `stats` via `?meta=1`: `media, mediana, min, max, desvio_padrao, amplitude, uf_mais_barato, uf_mais_cara`.
- [x] `GET /bi/tendencias/por-classificacao` → `variacao_periodo`, `media_movel`, `inflacao_acumulada` no período.
- [x] `GET /api/v1/public/bi/cenario?codigos=1,2,3&uf=SP&data_referencia=...` → `{composicoes:[...], total_bom, abc, spread_regional, tendencias}` agregados.

## Tasks
- [x] `crud.py`: cálculo de variação (`_compute_variacao`), stats regionais (`_regional_stats` + `get_cenario_spread`), cenário (`get_cenario` reusando BOM/ABC/tendências).
- [x] `schemas.py`: novos campos (`variacao_mensal`/`variacao_pct` em `HistoricoCusto` e `TendenciaClassificacao`) e `RegionalStats`/`CenarioComposicao`/`CenarioResponse`.
- [x] `main.py`: endpoint `/bi/cenario` (tier_2) + `?meta=1` em `/precos-uf`.
- [x] Testes pytest com dados sintéticos (`tests/test_bi_enrichment.py`, 11 testes).

## Arquivos
`api/crud.py`, `api/schemas.py`, `api/main.py`, `tests/`.