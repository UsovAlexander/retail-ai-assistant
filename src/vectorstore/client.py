"""Qdrant client + embedding model, as process-wide singletons.

Safety rail (CLAUDE.md): this module refuses to mutate any collection other
than ``retail_schema`` / ``retail_few_shot``. See [[Qdrant_Collections]].
"""

from __future__ import annotations

import logging
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, ScoredPoint, VectorParams
from sentence_transformers import SentenceTransformer

from src.config import get_settings

logger = logging.getLogger(__name__)

# LaBSE-en-ru embedding size (spec §4.3).
EMBEDDING_DIM = 768


def allowed_collections() -> frozenset[str]:
    s = get_settings()
    return frozenset({s.qdrant_schema_collection, s.qdrant_few_shot_collection})


def _assert_allowed(name: str) -> None:
    if name not in allowed_collections():
        raise ValueError(
            f"Refusing to touch collection '{name}'. This project may only "
            f"mutate {sorted(allowed_collections())} (safety rail)."
        )


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    s = get_settings()
    logger.info("Connecting to Qdrant at %s:%s", s.qdrant_host, s.qdrant_port)
    return QdrantClient(host=s.qdrant_host, port=s.qdrant_port)


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    s = get_settings()
    logger.info("Loading embedding model '%s' ...", s.embedding_model)
    return SentenceTransformer(s.embedding_model)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts into unit-normalized vectors (cosine-ready)."""
    model = get_embedder()
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return vectors.tolist()


def embed_one(text: str) -> list[float]:
    return embed([text])[0]


def recreate_collection(name: str) -> None:
    """Drop (if present) and create ``name`` with cosine distance. Guarded."""
    _assert_allowed(name)
    client = get_qdrant_client()
    if client.collection_exists(name):
        logger.info("Dropping existing collection '%s'", name)
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )
    logger.info("Created collection '%s' (dim=%d, cosine)", name, EMBEDDING_DIM)


def upsert(name: str, points: list[PointStruct]) -> None:
    """Upsert points into a guarded collection."""
    _assert_allowed(name)
    get_qdrant_client().upsert(collection_name=name, points=points)


def search(name: str, query: str, limit: int = 3) -> list[ScoredPoint]:
    """Semantic search: return the top-``limit`` points with payloads.

    Read-only, so any (including allowed) collection name is fine here.
    """
    client = get_qdrant_client()
    response = client.query_points(
        collection_name=name,
        query=embed_one(query),
        limit=limit,
        with_payload=True,
    )
    return response.points
