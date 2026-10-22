"""Rebuild the ChromaDB collection from data/processed/chunks.jsonl.

Run from the repository root: python ots-chatbot-backend/embeddings/build_index.py
"""
import json
from pathlib import Path
import sys

import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

BACKEND = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND / "embeddings" / "chroma_db"
CHUNKS = BACKEND / "data" / "processed" / "chunks.jsonl"
COLLECTION = "ots_knowledge_base"
BATCH = 256


def embedding_function():
    # CoreML crashes on this model on some Macs; CPU execution is slower but reliable.
    return ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])


def open_client(path: Path = DB_PATH):
    return chromadb.PersistentClient(path=str(path), settings=chromadb.Settings(anonymized_telemetry=False))


def build(rows: list[dict], path: Path = DB_PATH):
    """Drop and recreate the collection so a rebuild never keeps stale chunks."""
    client = open_client(path)
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass  # First build: nothing to delete.
    collection = client.create_collection(COLLECTION, embedding_function=embedding_function(), metadata={"hnsw:space": "cosine"})
    for start in range(0, len(rows), BATCH):
        batch = rows[start:start + BATCH]
        collection.add(
            ids=[row["id"] for row in batch],
            documents=[row["text"] for row in batch],
            metadatas=[{"source": row["source"], "url": row.get("url") or "", "kind": row["kind"]} for row in batch],
        )
        print(f"indexed {min(start + BATCH, len(rows))}/{len(rows)}", end="\r")
    print()
    return collection


def main() -> None:
    if not CHUNKS.exists():
        sys.exit("Missing data/processed/chunks.jsonl. Run data/fetch_datasets.py and data/clean.py first.")
    rows = [json.loads(line) for line in CHUNKS.read_text().splitlines() if line.strip()]
    build(rows)
    print(f"built {COLLECTION} with {len(rows)} chunks in {DB_PATH}")


if __name__ == "__main__":
    main()
