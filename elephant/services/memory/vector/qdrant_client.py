"""
ELEPHANT — Qdrant Vector Memory Client
Handles all vector storage and semantic retrieval operations.
Used exclusively by the Memory Agent — no other agent calls this directly.
"""
from __future__ import annotations
import logging
from typing import Any
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue, ScoredPoint,
)

logger = logging.getLogger(__name__)

COLLECTION_CONFIGS = {
    "research":     VectorParams(size=768, distance=Distance.COSINE),
    "conversations": VectorParams(size=768, distance=Distance.COSINE),
    "drafts":       VectorParams(size=768, distance=Distance.COSINE),
    "strategic":    VectorParams(size=768, distance=Distance.COSINE),
    "documents":    VectorParams(size=768, distance=Distance.COSINE),
}


class QdrantMemoryClient:
    """
    Thin async wrapper around Qdrant.
    All methods are called by Memory Agent only.
    """

    def __init__(self, url: str = "http://qdrant:6333"):
        self._client = AsyncQdrantClient(url=url)

    async def ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        existing = {c.name for c in await self._client.get_collections()}
        for name, params in COLLECTION_CONFIGS.items():
            if name not in existing:
                await self._client.create_collection(
                    collection_name=name,
                    vectors_config=params,
                )
                logger.info("qdrant_collection_created", extra={"collection": name})

    async def upsert(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Insert or update a vector point."""
        point = PointStruct(id=point_id, vector=vector, payload=payload)
        await self._client.upsert(collection_name=collection, points=[point])
        logger.debug("qdrant_upserted", extra={"collection": collection, "id": point_id})

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 12,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredPoint]:
        """Semantic similarity search."""
        qdrant_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            qdrant_filter = Filter(must=conditions)

        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        logger.debug("qdrant_search", extra={"collection": collection, "results": len(results)})
        return results

    async def delete(self, collection: str, point_id: str) -> None:
        """Delete a vector point by ID (requires user confirmation in design)."""
        from qdrant_client.models import PointIdsList
        await self._client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=[point_id]),
        )
        logger.info("qdrant_deleted", extra={"collection": collection, "id": point_id})
