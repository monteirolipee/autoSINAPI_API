"""Embedding model registry + pgvector (ADR-006 / STORY-SRC-004).

Creates the `embedding_models` registry table and enables the `vector`
extension for semantic search. Extension enable is fault-tolerant
(ADR-006): if the deployed postgres image does not ship pgvector, the
registry stays empty / marked error and search degrades gracefully to
trigram-only (discovery down path).

Per-model vector tables (`vec_<dims>_<slug>`) are created dynamically at
runtime by `api/vector_store.py` (helper DDL centralized) instead of
Alembic, to honor ADR-006 "distributed by model" without schema lock-in.

Revision ID: 007
Revises: 006
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Registry SSOT de modelos de embedding (ADR-006).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_models (
            id          SERIAL PRIMARY KEY,
            slug        TEXT UNIQUE NOT NULL,
            model_name  TEXT NOT NULL,
            dims        INTEGER NOT NULL,
            status      TEXT NOT NULL DEFAULT 'ready',
            row_count   INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # Extensao vector: tolerante a ausencia (degradacao graciosa, ADR-006).
    has_vector = False
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # Confirmacao pos-criacao: CREATE IF NOT EXISTS nao falha quando a
        # extensao ja esta instalada, mas precisamos saber se o tipo existe.
        has_vector = op.get_bind().execute(
            "SELECT 1 FROM pg_type WHERE typname = 'vector'"
        ).fetchone() is not None
    except Exception:
        has_vector = False

    if not has_vector:
        # Banco sem pgvector: registra o estado para log/debug legivel.
        op.execute(
            "INSERT INTO embedding_models (slug, model_name, dims, status, row_count) "
            "VALUES ('pgvector_unavailable', 'pgvector', 0, 'error', 0) "
            "ON CONFLICT (slug) DO NOTHING"
        )


def downgrade() -> None:
    # Extensao removida apenas se nada mais a usa (tabelas vec_* ja caíram).
    try:
        op.execute("DROP EXTENSION IF EXISTS vector")
    except Exception:
        pass
    op.execute("DROP TABLE IF EXISTS embedding_models")