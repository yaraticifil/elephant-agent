"""
ELEPHANT — Neo4j Knowledge Graph Client
Handles entity relationship storage and graph traversal.
Used exclusively by the Memory Agent — no other agent calls this directly.
"""
from __future__ import annotations
import logging
from typing import Any
from neo4j import AsyncGraphDatabase, AsyncDriver

logger = logging.getLogger(__name__)


class Neo4jMemoryClient:
    """
    Thin async wrapper around Neo4j.
    All Cypher operations run through this client, called by Memory Agent only.
    """

    def __init__(self, uri: str = "bolt://neo4j:7687", user: str = "neo4j", password: str = ""):
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self) -> None:
        await self._driver.close()

    async def ensure_constraints(self) -> None:
        """Create uniqueness constraints for core entity types."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Task) REQUIRE t.task_id IS UNIQUE",
        ]
        async with self._driver.session() as session:
            for query in constraints:
                await session.run(query)
        logger.info("neo4j_constraints_created")

    async def upsert_entity(
        self, entity_id: str, entity_type: str, properties: dict[str, Any]
    ) -> None:
        """Merge (upsert) an entity node."""
        query = (
            f"MERGE (e:{entity_type} {{entity_id: $entity_id}}) "
            f"SET e += $properties"
        )
        async with self._driver.session() as session:
            await session.run(query, entity_id=entity_id, properties=properties)
        logger.debug("neo4j_entity_upserted", extra={"type": entity_type, "id": entity_id})

    async def create_relationship(
        self,
        from_id: str,
        from_type: str,
        rel_type: str,
        to_id: str,
        to_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Create a directed relationship between two entities."""
        query = (
            f"MATCH (a:{from_type} {{entity_id: $from_id}}) "
            f"MATCH (b:{to_type} {{entity_id: $to_id}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r += $props"
        )
        async with self._driver.session() as session:
            await session.run(query, from_id=from_id, to_id=to_id, props=properties or {})
        logger.debug("neo4j_relationship_created", extra={
            "from": from_id, "rel": rel_type, "to": to_id
        })

    async def traverse(
        self,
        start_entity_id: str,
        start_type: str = "Entity",
        depth: int = 2,
    ) -> list[dict]:
        """Graph traversal from a starting entity up to `depth` hops."""
        query = (
            f"MATCH (start:{start_type} {{entity_id: $start_id}})-[r*1..{depth}]-(related) "
            f"RETURN related, r"
        )
        results = []
        async with self._driver.session() as session:
            result = await session.run(query, start_id=start_entity_id)
            async for record in result:
                results.append(dict(record["related"]))
        logger.debug("neo4j_traversal", extra={"start": start_entity_id, "depth": depth, "found": len(results)})
        return results

    async def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Run arbitrary read-only Cypher queries."""
        results = []
        async with self._driver.session() as session:
            result = await session.run(cypher, **(params or {}))
            async for record in result:
                results.append(dict(record))
        return results
