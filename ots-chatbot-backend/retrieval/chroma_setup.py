"""ChromaDB setup: build a per-department collection and retrieve chunks."""
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

DB_PATH = Path(__file__).resolve().parents[1] / ".chroma"
# CoreML crashes on this model on some Macs; CPU is slower but reliable.
EMBEDDING_FUNCTION = ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])


def build_collection(dept: str, chunks: list[str]) -> chromadb.api.models.Collection.Collection:
    client = chromadb.PersistentClient(
        path=str(DB_PATH),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        f"{dept}_knowledge_base",
        embedding_function=EMBEDDING_FUNCTION,
    )
    if chunks:
        collection.upsert(
            ids=[f"{dept}-{i}" for i in range(len(chunks))],
            documents=chunks,
            metadatas=[{"dept": dept} for _ in chunks],
        )
    return collection


def retrieve(collection: chromadb.api.models.Collection.Collection, query: str, n_results: int = 3) -> list[str]:
    results = collection.query(query_texts=[query], n_results=n_results)
    return results["documents"][0]
