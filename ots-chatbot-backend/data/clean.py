"""Clean, de-identify, deduplicate, and chunk data/raw/ into data/processed/chunks.jsonl.

Run from the repository root: python ots-chatbot-backend/data/clean.py
"""
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.redact import redact_identifiers

DATA = Path(__file__).resolve().parent
RAW = DATA / "raw"
PROCESSED = DATA / "processed" / "chunks.jsonl"
OTS_SITE = "https://www.iit.edu"
TICKETS_URL = "huggingface.co/datasets/Tobi-Bueck/customer-support-tickets"
IT_SUPPORT_URL = "huggingface.co/datasets/benjaminmacklin/IT_Support"
MIN_WORDS, MAX_WORDS = 100, 300
# Sections like "Please select the links below" carry no answer and crowd out real steps.
MIN_SECTION_WORDS = 12
# Keep public ticket data to problems a student could plausibly bring to OTS.
STUDENT_TOPICS = re.compile(
    r"wi-?fi|wireless|network|internet|vpn|print|outlook|e-?mail|teams|zoom|password|log ?in|sign ?in|"
    r"mfa|two-factor|authenticat|laptop|browser|office|onedrive|account|software|install|update|antivirus|phishing",
    re.I,
)
# Enterprise administration tickets are outside a student help desk's self-service scope.
ADMIN_TOPICS = re.compile(
    r"server|domain|group policy|gpo|active directory|sql|exchange|sharepoint|azure|intune|sccm|powershell|"
    r"hyper-v|vmware|dns|dhcp|raid|firewall rule|certificate|kerberos|ldap|radius|tenant|registry|driver",
    re.I,
)
MAX_PER_DATASET = 3000  # Keep generic ticket chunks from drowning out OTS pages.


def student_relevant(text: str) -> bool:
    return bool(STUDENT_TOPICS.search(text)) and not ADMIN_TOPICS.search(text)


def clean_text(text: str, public: bool = False) -> str:
    # Public OTS pages list official contact addresses; only masks student identifiers there.
    text = re.sub(r"\b[Aa]\d{8}\b", "[student ID omitted]", text) if public else redact_identifiers(text)
    text = re.sub(r"<(?:name|tel_num|email|acc_num|address)>", "", text)  # Dataset placeholders.
    return re.sub(r"\s+", " ", text).strip()


def window(paragraphs: list[str]) -> list[str]:
    """Merge short paragraphs and split long ones so chunks land near 100-300 words."""
    chunks, current = [], []
    for paragraph in paragraphs:
        words = paragraph.split()
        while len(words) > MAX_WORDS:
            if current:
                chunks.append(" ".join(current))
                current = []
            chunks.append(" ".join(words[:MAX_WORDS]))
            words = words[MAX_WORDS:]
        if current and len(current) + len(words) > MAX_WORDS:
            chunks.append(" ".join(current))
            current = []
        current += words
        if len(current) >= MIN_WORDS:
            chunks.append(" ".join(current))
            current = []
    if current:
        if chunks and len(current) < MIN_WORDS // 2 and len(chunks[-1].split()) + len(current) <= MAX_WORDS + MIN_WORDS // 2:
            chunks[-1] += " " + " ".join(current)
        else:
            chunks.append(" ".join(current))
    return chunks


def pdf_sections(path: Path) -> tuple[str, list[str]]:
    """OTS step-by-step PDFs: the first two lines name the guide and device; blocks are blank-line separated."""
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    text = re.sub(r"(?m)^\s*(?:Updated\b.*|\d+ \| Page\s*)$", "", text)
    blocks = [re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n", text)]
    blocks = [block for block in blocks if block]
    steps = next((i for i, block in enumerate(blocks) if re.match(r"1\.", block)), min(2, len(blocks)))
    title = " - ".join(blocks[:steps]) or path.stem
    return title, blocks[steps:]


def ots_chunks() -> list[dict]:
    rows = []
    for pdf in sorted((RAW / "ots").glob("*.pdf")):
        title, paragraphs = pdf_sections(pdf)
        url = OTS_SITE + "/" + pdf.name.replace("__", "/")
        for text in window(paragraphs):
            rows.append({"text": f"{title}\n{clean_text(text, public=True)}", "source": f"OTS: {title}", "url": url, "kind": "ots"})
    for page in sorted((RAW / "ots").glob("*.html")):
        main = BeautifulSoup(page.read_text(), "html.parser").find(id="main-content")
        if main is None:
            continue
        for tag in main(["script", "style", "nav"]):
            tag.decompose()
        title = main.find("h1").get_text(" ", strip=True) if main.find("h1") else page.stem
        sections, heading, paragraphs = [], title, []
        for element in main.find_all(["h2", "h3", "h4", "p", "li"]):
            if element.find_parent("li") or any("breadcrumb" in " ".join(parent.get("class") or []) for parent in element.parents):
                continue
            text = element.get_text(" ", strip=True)
            if not text or text in {"Home", "Office of Technology Services"}:
                continue
            if element.name in {"h2", "h3", "h4"}:
                if paragraphs:
                    sections.append((heading, paragraphs))
                heading, paragraphs = text, []
            else:
                paragraphs.append(text)
        if paragraphs:
            sections.append((heading, paragraphs))
        url = OTS_SITE + "/" + page.stem.replace("__", "/")
        for heading, paragraphs in sections:
            if sum(len(paragraph.split()) for paragraph in paragraphs) < MIN_SECTION_WORDS:
                continue
            label = title if heading == title else f"{title}: {heading}"
            for text in window(paragraphs):
                rows.append({"text": f"{label}\n{clean_text(text, public=True)}", "source": f"OTS: {label}", "url": url, "kind": "ots"})
    return rows


def ticket_chunks() -> list[dict]:
    rows = []
    path = RAW / "tickets.csv"
    if path.exists():
        with path.open(newline="") as handle:
            for ticket in csv.DictReader(handle):
                if ticket["language"] != "en" or ticket["queue"] not in {"IT Support", "Technical Support"}:
                    continue
                question = clean_text(f"{ticket['subject']}. {ticket['body']}")
                if not student_relevant(question) or not ticket["answer"].strip():
                    continue
                rows.append({"text": f"Issue: {question}\nResolution: {clean_text(ticket['answer'])}",
                             "source": "Public IT ticket dataset", "url": TICKETS_URL, "kind": "ticket"})
    for name in ("it_support_troubleshooting.jsonl", "it_support_steps.jsonl"):
        path = RAW / name
        if not path.exists():
            continue
        kept = []
        for line in path.read_text().splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue  # Malformed upstream line.
            if not student_relevant(item.get("instruction", "")):
                continue
            kept.append({"text": f"Issue: {clean_text(item['instruction'])}\nResolution: {clean_text(item['output'])}",
                         "source": "Public IT support dataset", "url": IT_SUPPORT_URL, "kind": "ticket"})
        # Deterministic sample: the same raw files always produce the same index.
        kept.sort(key=lambda row: hashlib.sha1(row["text"].encode()).hexdigest())
        rows += kept[:MAX_PER_DATASET]
    return rows


def deduplicate(rows: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for row in rows:
        key = hashlib.sha1(re.sub(r"\W+", " ", row["text"].lower()).strip().encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        unique.append({"id": key[:16], **row})
    return unique


def main() -> None:
    rows = deduplicate(ots_chunks() + ticket_chunks())
    if not rows:
        sys.exit("No raw data found. Run data/fetch_datasets.py first.")
    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    with PROCESSED.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    counts = {kind: sum(row["kind"] == kind for row in rows) for kind in ("ots", "ticket")}
    print(f"wrote {len(rows)} chunks to {PROCESSED} ({counts})")


if __name__ == "__main__":
    main()
