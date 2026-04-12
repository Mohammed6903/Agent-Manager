"""Qdrant vector database service — collection management and upsert/query."""
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FilterSelector,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchAny,
    MatchValue,
)
from ..config import settings

COLLECTION = "agent_memory"
VECTOR_SIZE = 1536  # text-embedding-3-small dimensions

def get_client() -> QdrantClient:
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

def ensure_collection():
    """Create collection if it doesn't exist. Safe to call on every startup."""
    client = get_client()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        print(f"[qdrant] Created collection '{COLLECTION}'")
    else:
        print(f"[qdrant] Collection '{COLLECTION}' already exists")

_UPSERT_CHUNK_SIZE = 100  # Qdrant recommended batch size


def upsert_points(points: list[PointStruct]) -> None:
    """Upsert points into the collection in chunks of 100.

    Qdrant recommends batches of ~100 points for optimal performance.
    """
    client = get_client()
    for i in range(0, len(points), _UPSERT_CHUNK_SIZE):
        client.upsert(collection_name=COLLECTION, points=points[i : i + _UPSERT_CHUNK_SIZE])

def search(
    agent_id: str,
    query_vector: list[float],
    source: str | None = None,
    top_k: int = 10,
) -> list[dict]:
    """Semantic search scoped to a specific agent."""
    client = get_client()

    must_conditions = [
        FieldCondition(key="agent_id", match=MatchValue(value=agent_id))
    ]
    if source:
        must_conditions.append(
            FieldCondition(key="source", match=MatchValue(value=source))
        )

    response = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        query_filter=Filter(must=must_conditions),  # type: ignore[arg-type]
        limit=top_k,
        with_payload=True,
    )
    return [
        {"score": r.score, **(r.payload or {})}
        for r in response.points
    ]


def search_third_party(
    agent_id: str,
    query_vector: list[float],
    top_k: int = 3,
) -> list[dict]:
    """Unified semantic search across ALL third-party sources for an agent.

    The old ``context_injection_service`` ran N parallel searches, one
    per connected integration (gmail + drive + slack + ...) with a top-k
    per source and a global char cap. That scaled linearly with the
    number of integrations and produced unsustainable prompt bloat on
    agents with 5+ sources.

    This function runs ONE query and returns the top-k chunks across
    the entire third-party corpus for this agent, regardless of source.
    Cost is constant: 1 embedding (paid by the caller) + 1 Qdrant query.

    Critically, this explicitly excludes ``source="manual_context"`` via
    a ``must_not`` filter so the third-party auto-inject block doesn't
    double-count chunks that the manual-context auto-inject is already
    handling.
    """
    client = get_client()
    response = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        query_filter=Filter(
            must=[
                FieldCondition(key="agent_id", match=MatchValue(value=agent_id)),
            ],
            must_not=[
                FieldCondition(
                    key="source",
                    match=MatchValue(value=MANUAL_CONTEXT_SOURCE),
                ),
            ],
        ),
        limit=top_k,
        with_payload=True,
    )
    return [
        {"score": r.score, **(r.payload or {})}
        for r in response.points
    ]


def list_payloads_for_agent_source(
    agent_id: str,
    source: str,
    limit: int = 2000,
) -> list[dict]:
    """Return payloads for a given agent and source using scroll pagination."""
    client = get_client()
    query_filter = Filter(
        must=[
            FieldCondition(key="agent_id", match=MatchValue(value=agent_id)),
            FieldCondition(key="source", match=MatchValue(value=source)),
        ]
    )

    payloads: list[dict] = []
    offset = None
    page_size = 200

    while len(payloads) < limit:
        points, next_offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=query_filter,
            limit=min(page_size, limit - len(payloads)),
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        if not points:
            break

        for point in points:
            payload = point.payload or {}
            if isinstance(payload, dict):
                payloads.append(payload)

        if next_offset is None:
            break
        offset = next_offset

    return payloads


# ── Manual context helpers ─────────────────────────────────────────────────
# Manual contexts (GlobalContext) are NOT scoped by agent_id the way
# third-party sources are — they're global documents that can be assigned
# to multiple agents via the agent_contexts junction table. So their
# Qdrant points use ``source="manual_context"`` + ``context_id`` for
# filtering instead of ``agent_id``. The caller (manual_context_service)
# resolves "which contexts does this agent have" from Postgres first,
# then passes the resulting id list to search_manual_context.


MANUAL_CONTEXT_SOURCE = "manual_context"


def search_manual_context(
    context_ids: list[str],
    query_vector: list[float],
    top_k: int = 5,
) -> list[dict]:
    """Semantic search across manual-context chunks filtered by context id.

    Returns raw payloads (with ``score``) for the top-k matching chunks
    across the given set of context ids. Empty list if ``context_ids`` is
    empty (Qdrant won't error but we skip the round trip).
    """
    if not context_ids:
        return []
    client = get_client()
    response = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        query_filter=Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value=MANUAL_CONTEXT_SOURCE)),
                FieldCondition(key="context_id", match=MatchAny(any=context_ids)),
            ]
        ),
        limit=top_k,
        with_payload=True,
    )
    return [
        {"score": r.score, **(r.payload or {})}
        for r in response.points
    ]


def delete_points_for_context(context_id: str) -> int:
    """Delete all manual-context chunks for a single context_id.

    Called on GlobalContext update (to clear old chunks before reindexing)
    and on delete. Returns the count of matched points before deletion.
    """
    client = get_client()
    query_filter = Filter(
        must=[
            FieldCondition(key="source", match=MatchValue(value=MANUAL_CONTEXT_SOURCE)),
            FieldCondition(key="context_id", match=MatchValue(value=context_id)),
        ]
    )
    matched = client.count(
        collection_name=COLLECTION,
        count_filter=query_filter,
        exact=True,
    ).count
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(filter=query_filter),
    )
    return matched


def delete_points_for_agent_source(agent_id: str, source: str) -> int:
    """Delete all points for a given agent and source.

    Returns:
        Number of points matched by the filter before deletion.
    """
    client = get_client()
    query_filter = Filter(
        must=[
            FieldCondition(key="agent_id", match=MatchValue(value=agent_id)),
            FieldCondition(key="source", match=MatchValue(value=source)),
        ]
    )

    matched = client.count(
        collection_name=COLLECTION,
        count_filter=query_filter,
        exact=True,
    ).count

    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(filter=query_filter),
    )
    return matched