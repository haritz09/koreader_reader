"""PostgreSQL persistence for embeddings and community indexes."""

import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.knowledge import EVENT_NODE_TYPE, LOCATION_NODE_TYPE
from db.models.book import Book
from db.models.chunk import ChunkRecord
from db.models.knowledge import EntityRecord, EventRecord, FactRecord, LocationRecord
from rag.adapters.persistence.models import (
    RagCommunityMemberRecord,
    RagCommunityRecord,
    RagCommunityRunRecord,
    RagEmbeddingRecord,
    RagIndexStateRecord,
)
from rag.domain.clustering import (
    ClusterEntityMention,
    ClusterFact,
    ClusterGraph,
    ClusterNamedMention,
    ClusterSources,
    CommunityTree,
)
from rag.domain.embeddings import EmbeddingSource, EmbeddingSourceType
from rag.domain.status import RAG_INDEX_CURRENT_STATUSES, RagIndexStatus


class PostgresRagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_graph_revision(self, book_id: str) -> int:
        result = await self._session.execute(
            select(Book.graph_revision).where(Book.id == book_id)
        )
        return int(result.scalar_one_or_none() or 0)

    async def get_embedding_sources(self, book_id: str) -> list[EmbeddingSource]:
        sources = [
            *await self._chunk_sources(book_id),
            *await self._entity_sources(book_id),
            *await self._fact_sources(book_id),
            *await self._event_sources(book_id),
            *await self._location_sources(book_id),
        ]
        sources.sort(
            key=lambda source: (
                source.source_type.value,
                source.reading_position,
                source.source_id,
            )
        )
        return sources

    async def _chunk_sources(self, book_id: str) -> list[EmbeddingSource]:
        chunks = await self._session.execute(
            select(
                ChunkRecord.id,
                ChunkRecord.text,
                ChunkRecord.start_pctg,
            )
            .where(ChunkRecord.book_id == book_id)
            .order_by(ChunkRecord.chunk_index, ChunkRecord.id)
        )
        return [
            EmbeddingSource(
                source_type=EmbeddingSourceType.CHUNK,
                source_id=chunk_id,
                chunk_id=chunk_id,
                reading_position=position,
                text=text,
            )
            for chunk_id, text, position in chunks.all()
        ]

    async def _entity_sources(self, book_id: str) -> list[EmbeddingSource]:
        entities = await self._session.execute(
            select(
                EntityRecord.id,
                EntityRecord.chunk_id,
                EntityRecord.name,
                EntityRecord.entity_type,
                EntityRecord.description,
                EntityRecord.aliases,
                EntityRecord.reading_position,
            )
            .where(EntityRecord.book_id == book_id)
            .order_by(EntityRecord.reading_position, EntityRecord.id)
        )
        return [
            EmbeddingSource(
                source_type=EmbeddingSourceType.ENTITY,
                source_id=entity_id,
                chunk_id=chunk_id,
                reading_position=position,
                text="\n".join(
                    part
                    for part in (
                        f"{name} ({entity_type})",
                        description,
                        *(aliases or ()),
                    )
                    if part
                ),
            )
            for entity_id, chunk_id, name, entity_type, description, aliases, position in (
                entities.all()
            )
        ]

    async def _fact_sources(self, book_id: str) -> list[EmbeddingSource]:
        facts = await self._session.execute(
            select(
                FactRecord.id,
                FactRecord.chunk_id,
                FactRecord.statement,
                FactRecord.reading_position,
            )
            .where(FactRecord.book_id == book_id)
            .order_by(FactRecord.reading_position, FactRecord.id)
        )
        return [
            EmbeddingSource(
                source_type=EmbeddingSourceType.FACT,
                source_id=fact_id,
                chunk_id=chunk_id,
                reading_position=position,
                text=statement,
            )
            for fact_id, chunk_id, statement, position in facts.all()
        ]

    async def _event_sources(self, book_id: str) -> list[EmbeddingSource]:
        events = await self._session.execute(
            select(
                EventRecord.id,
                EventRecord.chunk_id,
                EventRecord.name,
                EventRecord.description,
                EventRecord.reading_position,
            )
            .where(EventRecord.book_id == book_id)
            .order_by(EventRecord.reading_position, EventRecord.id)
        )
        return [
            EmbeddingSource(
                source_type=EmbeddingSourceType.EVENT,
                source_id=event_id,
                chunk_id=chunk_id,
                reading_position=position,
                text="\n".join(part for part in (name, description) if part),
            )
            for event_id, chunk_id, name, description, position in events.all()
        ]

    async def _location_sources(self, book_id: str) -> list[EmbeddingSource]:
        locations = await self._session.execute(
            select(
                LocationRecord.id,
                LocationRecord.chunk_id,
                LocationRecord.name,
                LocationRecord.description,
                LocationRecord.reading_position,
            )
            .where(LocationRecord.book_id == book_id)
            .order_by(LocationRecord.reading_position, LocationRecord.id)
        )
        return [
            EmbeddingSource(
                source_type=EmbeddingSourceType.LOCATION,
                source_id=location_id,
                chunk_id=chunk_id,
                reading_position=position,
                text="\n".join(part for part in (name, description) if part),
            )
            for location_id, chunk_id, name, description, position in locations.all()
        ]

    async def get_existing_hashes(
        self,
        book_id: str,
        model: str,
    ) -> Mapping[tuple[str, str], str]:
        result = await self._session.execute(
            select(
                RagEmbeddingRecord.source_type,
                RagEmbeddingRecord.source_id,
                RagEmbeddingRecord.content_hash,
            )
            .where(RagEmbeddingRecord.book_id == book_id)
            .where(RagEmbeddingRecord.model == model)
        )
        return {
            (source_type, source_id): content_hash
            for source_type, source_id, content_hash in result.all()
        }

    async def upsert_embeddings(
        self,
        book_id: str,
        model: str,
        rows: Sequence[tuple[EmbeddingSource, str, list[float]]],
    ) -> None:
        if not rows:
            return
        statement = pg_insert(RagEmbeddingRecord).values(
            [
                {
                    "id": str(uuid.uuid4()),
                    "book_id": book_id,
                    "source_type": source.source_type.value,
                    "source_id": source.source_id,
                    "chunk_id": source.chunk_id,
                    "reading_position": source.reading_position,
                    "model": model,
                    "content_hash": digest,
                    "embedding": vector,
                }
                for source, digest, vector in rows
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                RagEmbeddingRecord.book_id,
                RagEmbeddingRecord.source_type,
                RagEmbeddingRecord.source_id,
                RagEmbeddingRecord.model,
            ],
            set_={
                "chunk_id": statement.excluded.chunk_id,
                "reading_position": statement.excluded.reading_position,
                "content_hash": statement.excluded.content_hash,
                "embedding": statement.excluded.embedding,
            },
        )
        await self._session.execute(statement)
        await self._session.commit()

    async def get_cluster_sources(self, book_id: str) -> ClusterSources:
        entity_mentions: list[ClusterEntityMention] = []
        entities = await self._session.execute(
            select(
                EntityRecord.id,
                EntityRecord.canonical_id,
                EntityRecord.name,
                EntityRecord.entity_type,
                EntityRecord.aliases,
                EntityRecord.reading_position,
                EntityRecord.chunk_id,
            )
            .where(EntityRecord.book_id == book_id)
            .order_by(EntityRecord.reading_position, EntityRecord.id)
        )
        for (
            entity_id,
            canonical_id,
            name,
            entity_type,
            aliases,
            position,
            chunk_id,
        ) in entities.all():
            entity_mentions.append(
                ClusterEntityMention(
                    entity_id=entity_id,
                    canonical_id=canonical_id or entity_id,
                    name=name,
                    entity_type=entity_type,
                    aliases=tuple(aliases or ()),
                    reading_position=position,
                    chunk_id=chunk_id,
                )
            )

        named_mentions: list[ClusterNamedMention] = []
        events = await self._session.execute(
            select(
                EventRecord.id,
                EventRecord.name,
                EventRecord.reading_position,
                EventRecord.chunk_id,
            )
            .where(EventRecord.book_id == book_id)
            .order_by(EventRecord.reading_position, EventRecord.id)
        )
        for event_id, name, position, chunk_id in events.all():
            named_mentions.append(
                ClusterNamedMention(
                    mention_id=event_id,
                    name=name,
                    node_type=EVENT_NODE_TYPE,
                    reading_position=position,
                    chunk_id=chunk_id,
                )
            )

        locations = await self._session.execute(
            select(
                LocationRecord.id,
                LocationRecord.name,
                LocationRecord.reading_position,
                LocationRecord.chunk_id,
            )
            .where(LocationRecord.book_id == book_id)
            .order_by(LocationRecord.reading_position, LocationRecord.id)
        )
        for location_id, name, position, chunk_id in locations.all():
            named_mentions.append(
                ClusterNamedMention(
                    mention_id=location_id,
                    name=name,
                    node_type=LOCATION_NODE_TYPE,
                    reading_position=position,
                    chunk_id=chunk_id,
                )
            )

        facts: list[ClusterFact] = []
        fact_rows = await self._session.execute(
            select(FactRecord.subject, FactRecord.object)
            .where(FactRecord.book_id == book_id)
            .order_by(FactRecord.reading_position, FactRecord.id)
        )
        for subject, object_ in fact_rows.all():
            facts.append(
                ClusterFact(
                    subject=subject,
                    object=object_,
                )
            )

        named_mentions.sort(
            key=lambda mention: (mention.reading_position, mention.mention_id)
        )
        return ClusterSources(
            entity_mentions=tuple(entity_mentions),
            named_mentions=tuple(named_mentions),
            facts=tuple(facts),
        )

    async def save_community_run(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
        graph: ClusterGraph,
        tree: CommunityTree,
        status: RagIndexStatus,
        error: str | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        state = await self._session.get(RagIndexStateRecord, book_id)
        self._session.add(
            RagCommunityRunRecord(
                id=run_id,
                book_id=book_id,
                graph_revision=graph_revision,
                algorithm=tree.algorithm,
                parameters=tree.parameters,
                node_count=tree.node_count,
                edge_count=tree.edge_count,
                modularity=tree.modularity,
            )
        )
        await self._session.flush()
        await self._session.execute(
            delete(RagCommunityRunRecord)
            .where(RagCommunityRunRecord.book_id == book_id)
            .where(RagCommunityRunRecord.id != run_id)
        )

        node_types = {node.node_id: node.node_type for node in graph.nodes}
        node_weights = {node.node_id: float(node.mention_count) for node in graph.nodes}
        node_positions = {node.node_id: node.reading_position for node in graph.nodes}

        by_level: dict[int, list] = defaultdict(list)
        for community in tree.communities:
            by_level[community.level].append(community)
        for level in sorted(by_level):
            for community in by_level[level]:
                self._session.add(
                    RagCommunityRecord(
                        id=community.community_id,
                        run_id=run_id,
                        book_id=book_id,
                        parent_id=community.parent_id,
                        level=community.level,
                        seed_node_id=community.seed_node_id,
                        signature_hash=community.signature_hash,
                        first_seen_position=community.first_seen_position,
                        member_count=len(community.member_ids),
                        internal_weight=community.internal_weight,
                    )
                )
            await self._session.flush()

        for community in tree.communities:
            for node_id in community.member_ids:
                self._session.add(
                    RagCommunityMemberRecord(
                        community_id=community.community_id,
                        node_id=node_id,
                        node_type=node_types.get(node_id, "other"),
                        weight=node_weights.get(node_id, 1.0),
                        first_seen_position=node_positions.get(
                            node_id, community.first_seen_position
                        ),
                    )
                )

        if state is None:
            state = RagIndexStateRecord(
                book_id=book_id,
                rag_revision=1,
                status=status.value,
                graph_revision=graph_revision,
                current_run_id=run_id,
                embedding_model=embedding_model,
                error=error,
            )
            self._session.add(state)
        else:
            state.rag_revision += 1
            state.status = status.value
            state.graph_revision = graph_revision
            state.current_run_id = run_id
            state.embedding_model = embedding_model
            state.error = error
            state.updated_at = datetime.now(UTC)

        await self._session.commit()
        return run_id

    async def claim_build(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
        stale_after_seconds: int,
    ) -> bool:
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=max(0, stale_after_seconds))
        statement = pg_insert(RagIndexStateRecord).values(
            book_id=book_id,
            rag_revision=0,
            status=RagIndexStatus.BUILDING.value,
            graph_revision=graph_revision,
            current_run_id=None,
            embedding_model=embedding_model,
            error=None,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[RagIndexStateRecord.book_id],
            set_={
                "status": RagIndexStatus.BUILDING.value,
                "graph_revision": graph_revision,
                "embedding_model": embedding_model,
                "error": None,
                "updated_at": now,
            },
            where=or_(
                RagIndexStateRecord.status != RagIndexStatus.BUILDING.value,
                RagIndexStateRecord.graph_revision != graph_revision,
                RagIndexStateRecord.embedding_model != embedding_model,
                RagIndexStateRecord.updated_at < stale_before,
            ),
        ).returning(RagIndexStateRecord.book_id)
        result = await self._session.execute(statement)
        await self._session.commit()
        return result.scalar_one_or_none() is not None

    async def mark_pending(self, book_id: str, error: str | None = None) -> None:
        state = await self._session.get(RagIndexStateRecord, book_id)
        if state is None:
            self._session.add(
                RagIndexStateRecord(
                    book_id=book_id,
                    rag_revision=0,
                    status=RagIndexStatus.PENDING.value,
                    graph_revision=0,
                    current_run_id=None,
                    embedding_model="",
                    error=error,
                )
            )
        else:
            state.status = RagIndexStatus.PENDING.value
            state.error = error
            state.updated_at = datetime.now(UTC)
        await self._session.commit()

    async def mark_failed(self, book_id: str, error: str) -> None:
        state = await self._session.get(RagIndexStateRecord, book_id)
        if state is None:
            self._session.add(
                RagIndexStateRecord(
                    book_id=book_id,
                    rag_revision=0,
                    status=RagIndexStatus.FAILED.value,
                    graph_revision=0,
                    current_run_id=None,
                    embedding_model="",
                    error=error,
                )
            )
        else:
            state.status = RagIndexStatus.FAILED.value
            state.error = error
            state.updated_at = datetime.now(UTC)
        await self._session.commit()

    async def needs_build(
        self,
        book_id: str,
        graph_revision: int,
        embedding_model: str,
        stale_after_seconds: int,
    ) -> bool:
        state = await self._session.get(RagIndexStateRecord, book_id)
        if state is None:
            return True
        if (
            state.graph_revision != graph_revision
            or state.embedding_model != embedding_model
        ):
            return True
        if state.status == RagIndexStatus.BUILDING.value:
            stale_before = datetime.now(UTC) - timedelta(
                seconds=max(0, stale_after_seconds)
            )
            return state.updated_at < stale_before
        return state.status not in {
            status.value for status in RAG_INDEX_CURRENT_STATUSES
        }

    async def delete_by_book(self, book_id: str) -> None:
        await self._session.execute(
            delete(RagIndexStateRecord).where(RagIndexStateRecord.book_id == book_id)
        )
        await self._session.execute(
            delete(RagEmbeddingRecord).where(RagEmbeddingRecord.book_id == book_id)
        )
        await self._session.execute(
            delete(RagCommunityRunRecord).where(RagCommunityRunRecord.book_id == book_id)
        )
        await self._session.commit()
