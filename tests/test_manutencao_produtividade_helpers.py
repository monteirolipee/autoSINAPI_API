"""Testes unitários dos helpers de Manutenções e Produtividade (SIN-094).

Bugs corrigidos validados contra o banco real da stack autosinapi (2026-08-21):
- `manutencoes_historico.tipo_item` guarda 'COMPOSICAO'/'COMPOSIÇÃO' (maiúsculo,
  com variante acentuada) enquanto o path chega como 'composicao' → 404 para
  qualquer item sem normalização.
- `/produtividade` somava pais+filhos do BOM linear (caso 87328: 533,41 vs
  folhas 407,62 — inflação de +29%).
"""

import pytest

from api.crud import _filter_bom_leaves, _normalize_tipo_item


class TestNormalizeTipoItem:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("composicao", "COMPOSICAO"),
            ("COMPOSICAO", "COMPOSICAO"),
            ("Composição", "COMPOSICAO"),   # variante acentuada presente no banco
            ("COMPOSIÇÃO", "COMPOSICAO"),
            (" insumo ", "INSUMO"),
            ("INSUMO", "INSUMO"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_normaliza_case_e_acento(self, raw, expected):
        assert _normalize_tipo_item(raw) == expected


def _row(codigo, tipo="INSUMO", nivel=1, impacto=None):
    return {
        "item_codigo": codigo,
        "tipo_item": tipo,
        "nivel": nivel,
        "coeficiente_total": 1.0,
        "custo_unitario": 10.0,
        "custo_impacto_total": impacto if impacto is not None else 10.0,
    }


class TestFilterBomLeaves:
    def test_fixture_real_87328_pais_descartados(self):
        """Estrutura real do 87328: n1 = 3 insumos + 4 composições; n2/n3 =
        desdobramento. Folhas = 15 linhas; pais COMPOSIÇÃO descartados."""
        rows = []
        # nível 1: materiais diretos
        for cod, imp in [(43617, 0.42), (370, 116.84), (1379, 172.05)]:
            rows.append(_row(cod, "INSUMO", 1, imp))
        # nível 1: composições pai (MO/equipamento)
        for cod, imp in [(88398, 2.62), (88393, 4.04), (88377, 92.62), (88316, 18.99)]:
            rows.append(_row(cod, "COMPOSICAO", 1, imp))
        # nível 2: filhos (encargos/EPIs/horistas) + sub-composições pai
        n2_insumos_imp = [14.52, 2.44, 71.34, 4.63, 0.36, 3.47, 13.56, 0.91]
        for idx, imp in enumerate(n2_insumos_imp):
            rows.append(_row(10000 + idx, "INSUMO", 2, imp))
        for idx, imp in enumerate([2.78, 0.64, 0.71, 2.53]):
            rows.append(_row(20000 + idx, "COMPOSIÇÃO", 2, imp))  # acento!
        # nível 3: folhas profundas
        rows.append(_row(2705, "INSUMO", 3, 2.53))
        rows.append(_row(37545, "INSUMO", 3, 4.17))

        leaves = _filter_bom_leaves(rows)

        codigos = {r["item_codigo"] for r in leaves}
        # nenhum pai sobrevive
        for pai in (88398, 88393, 88377, 88316):
            assert pai not in codigos
        for pai in range(20000, 20004):
            assert pai not in codigos
        # todas as folhas permanecem (fixture reduzido: 13 de 25 linhas)
        assert len(leaves) == 13
        total = sum(r["custo_impacto_total"] for r in leaves)
        # payload REAL do 87328: 25 linhas → 15 folhas = 407,62
        # (oficial publicado: 412,75; linear bugado: 533,41)
        assert round(total, 2) == 407.24

    def test_composicao_folha_sem_filhos_permanece(self):
        """COMP sem linha mais profunda é folha legítima (custo consolidado)."""
        rows = [_row(1, "INSUMO", 1, 5.0), _row(2, "COMPOSICAO", 1, 7.0)]
        leaves = _filter_bom_leaves(rows)
        assert len(leaves) == 2

    def test_sem_hierarquia_retorna_integral(self):
        """BOM raso (nível único) não perde linhas."""
        rows = [_row(i, "COMPOSICAO", None, 3.0) for i in range(3)]
        assert len(_filter_bom_leaves(rows)) == 3

    def test_lista_vazia(self):
        assert _filter_bom_leaves([]) == []
