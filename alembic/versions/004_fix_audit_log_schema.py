"""Fix sinapi_audit_log schema to ETL-run-log format.

Drops the old audit-trail schema (id, table_name, record_pk, operation,
old_values, new_values, motivo_manutencao) and recreates the table with
the ETL-run-log schema (run_id, data_referencia, records_inserted,
tables_updated) that matches the application code in database.py.

Revision ID: 004
Revises: 003
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Drop old audit-trail schema indexes
    op.drop_index("idx_audit_table_name", table_name="sinapi_audit_log")
    op.drop_index("idx_audit_created_at", table_name="sinapi_audit_log")
    op.drop_index("idx_audit_etl_run", table_name="sinapi_audit_log")

    # Drop old audit-trail table (migration 002 schema)
    op.drop_table("sinapi_audit_log")

    # Create ETL-run-log schema (matching database.py DDL)
    op.create_table(
        "sinapi_audit_log",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("data_referencia", sa.String(20), nullable=True),
        sa.Column("records_inserted", sa.Integer(), nullable=True),
        sa.Column("tables_updated", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    # Drop ETL-run-log table
    op.drop_table("sinapi_audit_log")

    # Recreate audit-trail schema (migration 002 format)
    op.create_table(
        "sinapi_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("record_pk", postgresql.JSONB(), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("old_values", postgresql.JSONB(), nullable=True),
        sa.Column("new_values", postgresql.JSONB(), nullable=True),
        sa.Column("sinapi_versao", sa.String(20), nullable=True),
        sa.Column("etl_run_id", sa.String(36), nullable=True),
        sa.Column("motivo_manutencao", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Recreate old indexes
    op.create_index("idx_audit_table_name", "sinapi_audit_log", ["table_name"])
    op.create_index("idx_audit_created_at", "sinapi_audit_log", ["created_at"])
    op.create_index("idx_audit_etl_run", "sinapi_audit_log", ["etl_run_id"])
