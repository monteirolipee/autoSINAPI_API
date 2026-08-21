# STORY-SIN-094 — Manutenções 404 (case/acento) + Produtividade por folhas

**Data:** 2026-08-21 · **Origem:** análise de consumo do portal mundoaec (EPIC-14)
**ADR:** [008-bom-folhas-produtividade](../adrs/008-bom-folhas-produtividade.md)

## Bug 1 — `/bi/item/{tipo}/{codigo}/manutencoes` sempre 404

`manutencoes_historico.tipo_item` é gravado pelo ETL como
`'COMPOSICAO'`/`'COMPOSIÇÃO'`/`'INSUMO'` (maiúsculo, com variante acentuada —
54.448 registros), enquanto o path chega `'composicao'` minúsculo. O filtro
exato não casava → **404 para qualquer item**. Validado no banco:
`UPPER(TRANSLATE(...))` retorna os 3 eventos da composição 87328.

**Fix:** helper `_normalize_tipo_item()` + comparação
`TRANSLATE+UPPER` nos dois lados do WHERE.

## Bug 2 — `/produtividade.total_custo` com dupla contagem

Somava pais COMPOSICAO + filhos explodidos (533,41 para o 87328; folhas =
407,62). **Fix:** `_filter_bom_leaves()` antes do loop de classificação.

## Testes

- `tests/test_manutencao_produtividade_helpers.py`: normalização (case,
  acento, None) e folhas (fixture estrutural do 87328, COMP-folha legítima,
  BOM sem hierarquia, lista vazia).
- Suíte existente: 248 passed / 5 falhas pré-existentes em baseline (sem
  relação: legal/post_schemas funcionais).
