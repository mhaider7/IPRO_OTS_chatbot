"""Vector search over the OTS knowledge base built by embeddings/build_index.py."""
from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import re

from embeddings.build_index import COLLECTION, DB_PATH, embedding_function, open_client

# Cosine distance: 0 is identical, larger is less related. Tuned on tests/fixtures/retrieval_eval.json,
# where casual student questions land at or below ~0.47 and off-topic questions at or above ~0.58.
MAX_DISTANCE = float(os.getenv("HAWK_RETRIEVAL_MAX_DISTANCE", "0.52"))
# Generic public tickets are not Illinois Tech procedures, so they must match more closely.
TICKET_MAX_DISTANCE = float(os.getenv("HAWK_TICKET_MAX_DISTANCE", "0.45"))

# Students write "wifi" and "okta not working"; OTS pages say "wireless", "IIT-Secure", and
# "multifactor authentication". The small embedding model misses those links, so add the campus terms.
EXPANSIONS = (
    (r"wi-?fi|wireless|internet|eduroam|dorm|residence hall|connection|\bnetwork\b", "Wi-Fi wireless network IIT-Secure connecting"),
    (r"ps[45]|xbox|nintendo|console|roku|smart tv|chromecast|alexa|gaming", "IIT-IoT gaming console device registration wireless"),
    (r"password|log ?in|sign ?in|locked out|portal", "Illinois Tech account password log-in portal"),
    (r"okta|mfa|2fa|two.?factor|multi.?factor|duo|push|text code|verification code|authenticat", "Okta Verify multifactor authentication MFA"),
    (r"vpn|remote access|off.?campus", "VPN Cisco AnyConnect remote access"),
    (r"phish|suspicious|scam|spam", "phishing report suspicious email"),
    (r"print", "printing print computer lab"),
    (r"help ?desk|support desk|contact ots|\bhours\b|where is ots|call ots", "OTS Support Desk location hours contact"),
    (r"e-?mail|outlook|inbox", "student email Outlook Microsoft 365"),
    (r"\boffice\b|\bword\b|excel|powerpoint|teams|onedrive|microsoft", "Microsoft 365 apps download"),
    (r"\blab\b|labs|vcl|virtual computer", "computer labs Virtual Computer Lab VCL"),
    (r"\brent\b|borrow|checkout|projector", "equipment rental checkout"),
)


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str
    url: str | None
    kind: str  # "ots" (verified Illinois Tech page) or "ticket" (general public dataset)
    distance: float


class IndexMissing(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _collection(path: str):
    client = open_client(Path(path))
    try:
        return client.get_collection(COLLECTION, embedding_function=embedding_function())
    except Exception as exc:
        raise IndexMissing("Knowledge base not built. Run embeddings/build_index.py.") from exc


def expand_query(query: str) -> str:
    extra = [terms for pattern, terms in EXPANSIONS if re.search(pattern, query, re.I)]
    return f"{query} | {' '.join(extra)}" if extra else query


def _search(query: str, k: int, kind: str, path: Path) -> list[Chunk]:
    def run():
        return _collection(str(path)).query(query_texts=[query], n_results=k, where={"kind": kind})
    try:
        results = run()
    except IndexMissing:
        raise
    except Exception:
        # build_index.py recreates the collection, which invalidates a cached handle in a running server.
        _collection.cache_clear()
        try:
            results = run()
        except IndexMissing:
            raise
        except Exception:
            return []  # For example, no chunks of this kind in the index.
    return [
        Chunk(text=text, source=meta["source"], url=meta.get("url") or None, kind=meta["kind"], distance=distance)
        for text, meta, distance in zip(results["documents"][0], results["metadatas"][0], results["distances"][0])
    ]


def retrieve(query: str, k: int = 3, path: Path = DB_PATH) -> list[Chunk]:
    """OTS pages when one matches; otherwise the closest material of either kind."""
    ots = _search(expand_query(query), k, "ots", path)
    if ots and ots[0].distance <= MAX_DISTANCE:
        return ots
    return sorted(ots + _search(query, k, "ticket", path), key=lambda chunk: chunk.distance)[:k]


def is_good(chunk: Chunk) -> bool:
    return chunk.distance <= (MAX_DISTANCE if chunk.kind == "ots" else TICKET_MAX_DISTANCE)


def has_good_match(chunks: list[Chunk]) -> bool:
    return any(is_good(chunk) for chunk in chunks)


def source_labels(chunks: list[Chunk]) -> list[str]:
    """Deduplicated citations for the frontend, which renders only https URLs as links."""
    labels = []
    for chunk in chunks:
        label = chunk.url or chunk.source
        if label not in labels:
            labels.append(label)
    return labels
