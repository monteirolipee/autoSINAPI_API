"""Implement trigram + unaccent GIN search (ADR-004).

Enables performant relevance-ranked textual search over `insumos.descricao`
and `composicoes.descricao` via pg_trgm + unaccent. Prior to this migration the
search relied on plain `ILIKE '%q%'` which forces sequential scans.

Revision ID: 006
Revises: 005
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # ADR-005 Camada 2 — extensões obrigatórias para ranking por trigrama.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # Wrapper IMMUTABLE de unaccent: funções em expressão de índice precisam
    # ser IMMUTABLE (Postgres exige). Ver wiki "Faster LIKE/ILIKE".
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        PARALLEL SAFE
        STRICT
        AS $func$
        SELECT public.unaccent('public.unaccent', $1)
        $func$
        """
    )

    # Imunizante: unaccent em insumos (non-deterministic? non-blocking build).
    op.execute("DROP INDEX IF EXISTS idx_insumos_descricao_gin")
    op.execute("DROP INDEX IF EXISTS idx_composicoes_descricao_gin")

    op.execute(
        """
        CREATE INDEX idx_insumos_descricao_gin
        ON insumos USING gin (f_unaccent(descricao) gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_composicoes_descricao_gin
        ON composicoes USING gin (f_unaccent(descricao) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_insumos_descricao_gin")
    op.execute("DROP INDEX IF EXISTS idx_composicoes_descricao_gin")
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
    # Extensões removidas apenas se nada mais as usa.
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS unaccent")