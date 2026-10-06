"""Minimal ChromaDB setup: one sample OTS document, chunked and queryable."""
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

DB_PATH = Path(__file__).resolve().parents[1] / ".chroma"
# CoreML crashes on this model on some Macs; CPU execution is slower but reliable.
EMBEDDING_FUNCTION = ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])

SAMPLE_DOCUMENT = """
Illinois Tech Wi-Fi Connection Guide

If your device will not connect to the eduroam Wi-Fi network, first confirm that
Wi-Fi is turned on and airplane mode is off. Forget the eduroam network in your
device's Wi-Fi settings, then reconnect and sign in again with your Illinois Tech
username and password.

Make sure you are within range of a campus access point; signal strength is
weaker in basements and some residence hall rooms. If reconnecting does not
work, restart your device and try again.

Devices older than five years may not support the encryption eduroam requires
and may need a software update. Students who still cannot connect after these
steps should contact the OTS Support Desk with the exact error message and the
device type.
""".strip()

CHUNKS = [chunk.strip() for chunk in SAMPLE_DOCUMENT.split("\n\n") if chunk.strip()]


def build_collection() -> chromadb.api.models.Collection.Collection:
    client = chromadb.PersistentClient(path=str(DB_PATH), settings=chromadb.Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection("ots_knowledge_base", embedding_function=EMBEDDING_FUNCTION)
    collection.upsert(
        ids=[f"wifi-guide-{i}" for i in range(len(CHUNKS))],
        documents=CHUNKS,
        metadatas=[{"source": "Wi-Fi Connection Guide"} for _ in CHUNKS],
    )
    return collection


def run_test_query(collection, query: str, n_results: int = 2):
    return collection.query(query_texts=[query], n_results=n_results)


def retrieve(query: str, n_results: int = 2) -> list[str]:
    """Reusable by the LLM step: just the matched chunk text, no scores."""
    results = run_test_query(build_collection(), query, n_results)
    return results["documents"][0]


if __name__ == "__main__":
    collection = build_collection()
    query = "My laptop won't connect to the campus Wi-Fi"
    results = run_test_query(collection, query)

    print(f"Query: {query}\n")
    for doc, distance, meta in zip(
        results["documents"][0], results["distances"][0], results["metadatas"][0]
    ):
        print(f"- ({meta['source']}, distance={distance:.4f}) {doc}")
