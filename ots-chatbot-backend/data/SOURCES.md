# Knowledge base sources

`fetch_datasets.py` downloads these into `data/raw/`. Nothing downloaded is committed.

| Source | Use in Hawk | License / terms | Pinned revision |
| --- | --- | --- | --- |
| Public Illinois Tech OTS pages and step-by-step PDFs listed in [`ots_pages.txt`](ots_pages.txt) | `kind="ots"`: cited with their iit.edu URL and ranked first | Public university web content; indexed for this course project only, not redistributed | Fetched at build time |
| [Tobi-Bueck/customer-support-tickets](https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets) (`dataset-tickets-multi-lang-4-20k.csv`, English, IT/Technical Support queues) | `kind="ticket"`: general IT guidance | CC BY-NC 4.0 (non-commercial, attribution) | `ddf1c81a5475992c4fa6752bf1e8b4e31f07bbeb` |
| [benjaminmacklin/IT_Support](https://huggingface.co/datasets/benjaminmacklin/IT_Support) (`B_troubleshooting.jsonl`, `C_steps.jsonl`) | `kind="ticket"`: general IT guidance | MIT | `f03a2444e16787e72ff03f1d46f11ec03bca06b9` |

`clean.py` keeps English, student-relevant issues and drops enterprise administration topics such as servers and Group Policy. It masks emails, A-numbers, and labeled passwords or codes, removes the datasets' `<name>`-style placeholders, and deduplicates on normalized text. It keeps at most 3,000 chunks per IT_Support file. OTS pages are split by heading into chunks of about 100–300 words.

To add an OTS page, add its path to `ots_pages.txt`, run the three build steps in the backend README, and add a question for it to `tests/fixtures/retrieval_eval.json`.
