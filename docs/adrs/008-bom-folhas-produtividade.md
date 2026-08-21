# ADR-008 — BOM hierárquico: folhas como base de cálculo analítico

**Status:** aceito · **Data:** 2026-08-21 · **Origem:** SIN-094 (consumo mundoaec)

## Contexto

`get_composicao_bom` (CTE recursiva) retorna pais e filhos na mesma lista:
composições pai com custo consolidado (`custo_unitario` de
`custos_composicoes_mensal`) **e** seus insumos explodidos nos níveis abaixo.
Consumidores que somam linearmente duplicam custo. Caso real (composição
87328, SP/2026-07/NAO_DESONERADO):

| Regra | Total |
|---|---|
| Linear (pais+filhos) | 533,41 |
| **Folhas** | **407,62** |
| Oficial publicado (`custo_total`) | 412,75 |

O `/produtividade` herdou a soma linear → `total_custo` inflado (+29%).

## Decisão

1. **Helper único `_filter_bom_leaves(rows)`** em `api/crud.py`: descarta linha
   COMPOSICAO que tenha linha mais profunda na lista; COMP sem filhos na lista
   permanece (folha legítima). BOM sem níveis utilizáveis → integral
   (retrocompatível).
2. `/produtividade` passa a totalizar sobre as folhas.
3. `/hora-homem` e `/otimizar` já filtravam INSUMO — inalterados.

## Consequências

- `total_custo` do produtividade fica consistente com o consumo client-side
  (portal mundoaec, ADR-040 de lá) e com o custo oficial (~1% de ruído de
  arredondamento da publicação).
- Quebra sutil: quem dependia do valor inflado verá redução ~20–30% no
  `total_custo` de composições multi-nível — é a correção.
