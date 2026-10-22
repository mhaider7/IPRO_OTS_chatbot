import json
from pathlib import Path
import re

import pytest

from embeddings.build_index import DB_PATH, build
from retrieval.retriever import Chunk, expand_query, has_good_match, retrieve, source_labels

ROWS = [
    {"id": "wifi", "text": "Connect to the IIT-Secure wireless network with your Illinois Tech username and password.",
     "source": "OTS: Getting Connected", "url": "https://www.iit.edu/ots/access/getting-connected", "kind": "ots"},
    {"id": "vpn", "text": "Install Cisco AnyConnect to use the VPN from off campus.",
     "source": "OTS: VPN/Remote Access", "url": "https://www.iit.edu/ots/access/vpn-remote-access", "kind": "ots"},
    {"id": "print", "text": "Issue: Printer queue stuck. Resolution: Clear the print queue and restart the spooler.",
     "source": "Public IT ticket dataset", "url": "huggingface.co/datasets/Tobi-Bueck/customer-support-tickets", "kind": "ticket"},
    {"id": "phish", "text": "Report phishing emails with the Phish Alert Button in Outlook.",
     "source": "OTS: How to Report a Phishing Attempt", "url": "https://www.iit.edu/ots/cybersecurity/how-report-phishing-attempt", "kind": "ots"},
]


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    path = tmp_path_factory.mktemp("chroma")
    build(ROWS, path)
    return path


def test_returns_top_k_with_sources(index):
    chunks = retrieve("How do I connect to wifi on campus?", k=2, path=index)
    assert len(chunks) == 2 and chunks[0].url.endswith("getting-connected")
    assert all(isinstance(chunk, Chunk) and chunk.source for chunk in chunks)


def test_rebuild_replaces_collection(index):
    build(ROWS[:1], index)
    try:
        assert {chunk.source for chunk in retrieve("vpn", k=3, path=index)} == {"OTS: Getting Connected"}
    finally:
        build(ROWS, index)


def test_ots_pages_preferred_over_closer_tickets(index):
    chunks = retrieve("printer queue stuck", k=3, path=index)
    assert chunks[0].kind == "ticket" or chunks[0].distance <= 0.52  # Tickets only when no OTS page matches.
    assert {chunk.kind for chunk in retrieve("how do I get on the wifi", k=2, path=index)} == {"ots"}


def test_query_expansion_adds_campus_terms():
    assert "IIT-Secure" in expand_query("wifi not working")
    assert "Okta Verify" in expand_query("not getting the push")
    assert expand_query("what is the weather") == "what is the weather"


def test_thresholds_are_stricter_for_tickets_and_labels_dedupe():
    near = Chunk("a", "OTS: A", "https://www.iit.edu/ots/a", "ots", 0.5)
    ticket = Chunk("b", "Public IT ticket dataset", None, "ticket", 0.5)
    assert has_good_match([ticket, near]) and not has_good_match([ticket])
    assert source_labels([near, near, ticket]) == ["https://www.iit.edu/ots/a", "Public IT ticket dataset"]


@pytest.mark.index
@pytest.mark.skipif(not DB_PATH.exists(), reason="Run embeddings/build_index.py to evaluate the real knowledge base.")
def test_eval_set_against_real_index():
    """Guide acceptance: relevant chunks with sources for at least 10 sample questions."""
    cases = json.loads((Path(__file__).parent / "fixtures" / "retrieval_eval.json").read_text())
    hits = 0
    for case in cases["answerable"]:
        chunks = retrieve(case["question"])
        hits += has_good_match(chunks) and any(chunk.url and re.search(case["expect"], chunk.url) for chunk in chunks)
    assert hits >= max(10, len(cases["answerable"]) - 1)
    for question in cases["unanswerable"]:
        assert not has_good_match(retrieve(question)), question
