"""Add ETL traceability columns missing from alembic history.

The application DDL in autosinapi/core/database.py already declares
`origem_preco` (precos_insumos_mensal) and `percentual_mo`
(custos_composicoes_mensal), but the alembic migrations 001-004 never
added them. Databases provisioned via alembic therefore lack these
columns, causing the processor load to fail. This migration reconciles
the schema using idempotent ADD COLUMN IF NOT EXISTS statements.

Revision ID: 005
Revises: 004
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE precos_insumos_mensal "
        "ADD COLUMN IF NOT EXISTS origem_preco VARCHAR(10)"
    )
    op.execute(
        "ALTER TABLE custos_composicoes_mensal "
        "ADD COLUMN IF NOT EXISTS percentual_mo NUMERIC"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE custos_composicoes_mensal DROP COLUMN IF EXISTS percentual_mo")
    op.execute("ALTER TABLE precos_insumos_mensal DROP COLUMN IF EXISTS origem_preco")
