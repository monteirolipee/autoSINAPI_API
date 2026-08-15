"""
Camada vetorial (ADR-006 / STORY-SRC-004, Fase 4).

Centraliza o DDL dinâmico, o provider de embeddings (bge-m3 via Ollama do
notebook lampbook com fallback nomic local) e as operações de upsert/busca
cosine sobre tabelas `vec_<dims>_<slug>`. Degradação graciosa: se a extensão
`vector` não existir ou o provider estiver fora, as funções retornam vazio
sem lançar 5xx (SPEC-RULE-search-pipeline-graceful-degradation).
"""
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings

logger = logging.getLogger("autosinapi.vector_store")

# --- Registry de modelos suportados (ADR-006: SSOT) ---
# slug é o identificador usado no registry embedding_models e nomeia a tabela
# vetorial via `vec_<dims>_<slug>`.
VECTOR_MODELS: Dict[str, dict] = {
    "bge_m3": {"model_name": "bge-m3", "dims": 1024},
    "nomic_embed_text": {"model_name": "nomic-embed-text", "dims": 768},
}


def table_name(dims: int, slug: str) -> str:
    """Nome da tabela vetorial para um modelo: `vec_<dims>_<slug>`."""
    return f"vec_{dims}_{slug}"


def get_embedding_table(tipo_item: str) -> str:
    """Tabela de origem (insumos/composicoes) por tipo_item, via settings."""
    if tipo_item == "insumo":
        return settings.TABLE_INSUMOS
    if tipo_item == "composicao":
        return settings.TABLE_COMPOSICOES
    raise ValueError(f"tipo_item desconhecido para embeddings: {tipo_item}")


def _ollama_embed(url: str, model: str, texts: List[str], timeout: float) -> List[List[float]]:
    """Chama o endpoint `/api/embed` do Ollama e extrai `embeddings`."""
    if not texts:
        return []
    payload = json.dumps({"model": model, "input": texts}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    embeddings = data.get("embeddings") or data.get("data") or []
    out = []
    for e in embeddings:
        vec = e.get("embedding") if isinstance(e, dict) else e
        if isinstance(vec, list):
            out.append([float(x) for x in vec])
    return out


class EmbeddingProvider:
    """Provider resiliente de embeddings com fallback primário/alternativo.

    Primário: bge-m3 no Ollama do notebook (lampbook).
    Alternativo: nomic-embed-text no Ollama local (server_ollama).
    """

    def __init__(
        self,
        primary_url: Optional[str] = None,
        primary_model: Optional[str] = None,
        fallback_url: Optional[str] = None,
        fallback_model: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self.primary_url = primary_url or settings.EMBEDDING_PRIMARY_URL
        self.primary_model = primary_model or settings.EMBEDDING_PRIMARY_MODEL
        self.fallback_url = fallback_url or settings.EMBEDDING_FALLBACK_URL
        self.fallback_model = fallback_model or settings.EMBEDDING_FALLBACK_MODEL
        self.timeout = timeout or settings.EMBEDDING_TIMEOUT

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Gera embeddings; usa o fallback se o primário falhar."""
        if not texts:
            return []
        try:
            return _ollama_embed(self.primary_url, self.primary_model, texts, self.timeout)
        except Exception as exc:  # noqa: BLE001 - degradação graciosa
            logger.warning("Embedding primário (%s %s) falhou: %s; usando fallback (%s %s)",
                           self.primary_url, self.primary_model, exc,
                           self.fallback_url, self.fallback_model)
            try:
                return _ollama_embed(self.fallback_url, self.fallback_model, texts, self.timeout)
            except Exception as exc2:  # noqa: BLE001
                logger.error("Embedding fallback também falhou: %s", exc2)
                return []


def _vector_type_available(db: Session) -> bool:
    return db.execute(
        text("SELECT 1 FROM pg_type WHERE typname = 'vector'")
    ).first() is not None


def ensure_vector_table(db: Session, dims: int, slug: str) -> Optional[str]:
    """Cria (se ausente) a tabela vec_<dims>_<slug> e retorna o nome.

    Retorna None se a extensão vector não estiver disponível (degradação).
    """
    if not _vector_type_available(db):
        return None
    tname = table_name(dims, slug)
    ddl = f"""
        CREATE TABLE IF NOT EXISTS {tname} (
            codigo     INTEGER NOT NULL,
            tipo_item  TEXT NOT NULL,
            embedding  vector({dims}),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (codigo, tipo_item)
        )
    """
    db.execute(text(ddl))
    db.commit()
    return tname


def upsert_batch(db: Session, tname: str, tipo_item: str,
                 rows: List[Tuple[int, List[float]]]) -> int:
    """Upsert em lote de pares (codigo, embedding) na tabela vetorial."""
    if not rows:
        return 0
    params = [
        {"codigo": str(c), "tipo": tipo_item, "emb": "[" + ",".join(f"{x:.6f}" for x in v) + "]"}
        for c, v in rows
    ]
    # Para cada linha, primeiro remove registros antigos (DELETE) para evitar
    # conflitos de constraints únicas não vetoriais, depois insere. O upsert
    # ON CONFLICT (codigo, tipo_item) é a operação canônica; executada em lote.
    db.execute(
        text(
            f"""
            INSERT INTO {tname} (codigo, tipo_item, embedding)
            VALUES (:codigo, :tipo, :emb)
            ON CONFLICT (codigo, tipo_item)
            DO UPDATE SET embedding = EXCLUDED.embedding, updated_at = now()
            """
        ),
        params,
    )
    db.commit()
    return len(params)


def cosine_search(db: Session, tname: str, tipo_item: str, query_vec: List[float],
                  limit: int = 20) -> List[dict]:
    """Busca cosine `<=>`; retorna lista de dicts codigo/tipo/similarity.

    `tipo_item='all'` busca em todos os tipos (insumo + composicao).
    """
    literal = "[" + ",".join(f"{v:.6f}" for v in query_vec) + "]"
    tipo_filter = (
        "WHERE tipo_item = :tipo AND embedding IS NOT NULL"
        if tipo_item in ("insumo", "composicao")
        else "WHERE embedding IS NOT NULL"
    )
    rows = db.execute(
        text(
            f"""
            SELECT codigo, tipo_item, 1 - (embedding <=> :query) AS similarity
            FROM {tname}
            {tipo_filter}
            ORDER BY embedding <=> :query
            LIMIT :limit
            """
        ),
        {"query": literal, "tipo": tipo_item, "limit": limit},
    ).fetchall()
    return [
        {"codigo": r.codigo, "tipo_item": r.tipo_item, "similarity": float(r.similarity)}
        for r in rows
    ]


def refresh_row_count(db: Session, dims: int, slug: str) -> None:
    """Sincroniza embedding_models.row_count com o total real da tabela."""
    if not _vector_type_available(db):
        return
    tname = table_name(dims, slug)
    try:
        total = db.execute(text(f"SELECT count(*) AS n FROM {tname}")).scalar() or 0
    except Exception:  # noqa: BLE001 - tabela ainda não criada
        total = 0
    db.execute(
        text(
            """
            UPDATE embedding_models
            SET row_count = :n, updated_at = now()
            WHERE slug = :slug AND dims = :dims
            """
        ),
        {"n": int(total), "slug": slug, "dims": dims},
    )
    db.commit()