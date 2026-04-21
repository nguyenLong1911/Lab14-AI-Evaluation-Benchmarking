"""
Index và query chunks từ knowledge_base lên Weaviate Cloud.

Cách dùng:
    python data/weaviate_store.py index   # Tạo collection và upload toàn bộ chunks
    python data/weaviate_store.py query "Hit Rate là gì?"
    python data/weaviate_store.py delete  # Xoá collection (để re-index)

Yêu cầu biến môi trường trong .env:
    WEAVIATE_URL      - URL cluster Weaviate Cloud (ví dụ: https://xxx.weaviate.network)
    WEAVIATE_API_KEY  - API key từ Weaviate Cloud Dashboard
"""

import json
import os
import sys
from pathlib import Path

import weaviate
from dotenv import load_dotenv
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery

load_dotenv(Path(__file__).parent.parent / ".env")

WEAVIATE_URL = os.environ["WEAVIATE_URL"]
WEAVIATE_API_KEY = os.environ["WEAVIATE_API_KEY"]

COLLECTION_NAME = "KnowledgeChunk"
CHUNKS_FILE = Path(__file__).parent / "chunks.jsonl"


def get_client() -> weaviate.WeaviateClient:
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=WEAVIATE_URL,
        auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
    )


# ---------------------------------------------------------------------------
# INDEX
# ---------------------------------------------------------------------------

def index(client: weaviate.WeaviateClient) -> None:
    # Tạo collection nếu chưa tồn tại
    if client.collections.exists(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' already exists. Use 'delete' first to re-index.")
        return

    collection = client.collections.create(
        name=COLLECTION_NAME,
        vectorizer_config=Configure.Vectorizer.text2vec_weaviate(),
        properties=[
            Property(name="chunk_id", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="heading",  data_type=DataType.TEXT),
            Property(name="content",  data_type=DataType.TEXT),
        ],
    )
    print(f"Created collection '{COLLECTION_NAME}'.")

    chunks = [json.loads(line) for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]

    with collection.batch.fixed_size(batch_size=50) as batch:
        for chunk in chunks:
            batch.add_object({
                "chunk_id": chunk["chunk_id"],
                "heading":  chunk["heading"],
                "content":  chunk["content"],
            })

    print(f"Indexed {len(chunks)} chunks into '{COLLECTION_NAME}'.")


# ---------------------------------------------------------------------------
# QUERY
# ---------------------------------------------------------------------------

def query(client: weaviate.WeaviateClient, query_text: str, limit: int = 3) -> None:
    collection = client.collections.use(COLLECTION_NAME)

    response = collection.query.near_text(
        query=query_text,
        limit=limit,
        return_metadata=MetadataQuery(distance=True),
    )

    print(f"\nTop {limit} results for: \"{query_text}\"\n" + "-" * 60)
    for i, obj in enumerate(response.objects, 1):
        dist = obj.metadata.distance
        print(f"[{i}] {obj.properties['heading']}  (distance: {dist:.4f})")
        print(f"    {obj.properties['content'][:200].replace(chr(10), ' ')}...")
        print()


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

def delete(client: weaviate.WeaviateClient) -> None:
    if not client.collections.exists(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' does not exist.")
        return
    client.collections.delete(COLLECTION_NAME)
    print(f"Deleted collection '{COLLECTION_NAME}'.")


# ---------------------------------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------------------------------

COMMANDS = {"index": index, "delete": delete}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in (*COMMANDS, "query"):
        print("Usage:")
        print("  python data/weaviate_store.py index")
        print("  python data/weaviate_store.py query \"<search text>\"")
        print("  python data/weaviate_store.py delete")
        sys.exit(1)

    cmd = sys.argv[1]
    client = get_client()
    try:
        print(f"Connected to Weaviate Cloud: {client.is_ready()}")
        if cmd == "query":
            if len(sys.argv) < 3:
                print("Provide a query string: python data/weaviate_store.py query \"<text>\"")
                sys.exit(1)
            query(client, " ".join(sys.argv[2:]))
        else:
            COMMANDS[cmd](client)
    finally:
        client.close()
