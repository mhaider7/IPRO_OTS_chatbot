"""Download pinned public datasets and public OTS pages into data/raw/ (gitignored).

Run from the repository root: python ots-chatbot-backend/data/fetch_datasets.py
"""
from pathlib import Path
import sys
import time

import httpx

DATA = Path(__file__).resolve().parent
RAW = DATA / "raw"
HF = "https://huggingface.co/datasets"
# Pinned revisions keep rebuilds reproducible; licenses are recorded in data/SOURCES.md.
DATASETS = {
    "tickets.csv": f"{HF}/Tobi-Bueck/customer-support-tickets/resolve/ddf1c81a5475992c4fa6752bf1e8b4e31f07bbeb/dataset-tickets-multi-lang-4-20k.csv",
    "it_support_troubleshooting.jsonl": f"{HF}/benjaminmacklin/IT_Support/resolve/f03a2444e16787e72ff03f1d46f11ec03bca06b9/B_troubleshooting.jsonl",
    "it_support_steps.jsonl": f"{HF}/benjaminmacklin/IT_Support/resolve/f03a2444e16787e72ff03f1d46f11ec03bca06b9/C_steps.jsonl",
}
OTS_SITE = "https://www.iit.edu"


def ots_paths() -> list[str]:
    lines = (DATA / "ots_pages.txt").read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def main() -> None:
    (RAW / "ots").mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=60, headers={"User-Agent": "Hawk-IPRO-indexer/0.1"}) as client:
        for name, url in DATASETS.items():
            target = RAW / name
            if target.exists():
                print(f"keep {name}")
                continue
            response = client.get(url)
            response.raise_for_status()
            target.write_bytes(response.content)
            print(f"saved {name} ({len(response.content) // 1024} KB)")
        for path in ots_paths():
            suffix = "" if path.endswith(".pdf") else ".html"
            target = RAW / "ots" / (path.strip("/").replace("/", "__") + suffix)
            response = client.get(OTS_SITE + path)
            if response.status_code != 200:
                print(f"skip {path}: HTTP {response.status_code}", file=sys.stderr)
                continue
            target.write_bytes(response.content)
            print(f"saved {path}")
            time.sleep(0.5)  # Be polite to the university web server.


if __name__ == "__main__":
    main()
