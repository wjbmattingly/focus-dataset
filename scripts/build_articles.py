"""Build & optionally push the `bitter-aloe/focus-processed-articles` dataset.

One row per document (issue / briefing / sermon / index volume):
  - issue_id, issue_name, parent_folder, num_pages
  - page_images: Sequence(Image)  -- all original page renders, in order
  - page_ids: Sequence(string)
  - layouts:   Sequence(string)   -- per-page corrected layout JSON (string-encoded)
  - is_validated: bool            -- true iff every page is validated
  - issue_title (string, optional from Gemini)
  - issue_summary (string)
  - sections: Sequence(struct)    -- the structured Gemini extraction
  - sections_json: string         -- raw JSON of the IssueExtraction (for round-trip)

Run `process_issue.py` first if you only want to test on one issue. This script
processes every document, caching Gemini outputs in `output/processed/`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datasets import Dataset, Features, Image, Sequence, Value  # noqa: E402
from tqdm import tqdm  # noqa: E402

from focus_dataset.data import (  # noqa: E402
    DocumentRecord,
    group_into_documents,
    iter_page_records,
    load_layout,
)
from focus_dataset.gemini import extract_issue  # noqa: E402
from focus_dataset.schema import IssueExtraction  # noqa: E402


HF_REPO_ID = "bitter-aloe/focus-processed-articles"


def _slug(document_id: str) -> str:
    return document_id.replace("/", "__")


def _entity_struct() -> dict:
    return {"name": Value("string"), "canonical": Value("string")}


def _section_features() -> dict:
    return {
        "section_id": Value("string"),
        "section_type": Value("string"),
        "title": Value("string"),
        "summary": Value("string"),
        "body": Value("string"),
        "page_start": Value("int32"),
        "page_end": Value("int32"),
        "people": Sequence(_entity_struct()),
        "places": Sequence(_entity_struct()),
        "organizations": Sequence(_entity_struct()),
    }


def _build_features() -> Features:
    return Features(
        {
            "issue_id": Value("string"),
            "issue_name": Value("string"),
            "parent_folder": Value("string"),
            "num_pages": Value("int32"),
            "is_validated": Value("bool"),
            "page_ids": Sequence(Value("string")),
            "layouts": Sequence(Value("string")),
            "page_images": Sequence(Image()),
            "issue_title": Value("string"),
            "issue_summary": Value("string"),
            "sections": Sequence(_section_features()),
            "sections_json": Value("string"),
        }
    )


def _row_for(doc: DocumentRecord, extraction: IssueExtraction) -> dict:
    layouts = [json.dumps(load_layout(p), ensure_ascii=False) for p in doc.pages]
    page_images = [str(p.image_path) for p in doc.pages]
    return {
        "issue_id": doc.document_id,
        "issue_name": doc.document_name,
        "parent_folder": doc.parent_folder,
        "num_pages": doc.num_pages,
        "is_validated": all(p.is_validated for p in doc.pages),
        "page_ids": [p.page_id for p in doc.pages],
        "layouts": layouts,
        "page_images": page_images,
        "issue_title": extraction.issue_title,
        "issue_summary": extraction.issue_summary,
        "sections": [s.model_dump() for s in extraction.sections],
        "sections_json": extraction.model_dump_json(),
    }


def _load_cached(path: Path) -> IssueExtraction | None:
    if not path.is_file():
        return None
    try:
        return IssueExtraction.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def process_documents(
    docs: list[DocumentRecord],
    cache_dir: Path,
    *,
    skip_existing: bool = True,
    sleep_between: float = 0.0,
) -> dict[str, IssueExtraction]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = cache_dir / "_debug"
    out: dict[str, IssueExtraction] = {}

    for doc in tqdm(docs, desc="extracting"):
        cache_path = cache_dir / f"{_slug(doc.document_id)}.json"
        if skip_existing:
            cached = _load_cached(cache_path)
            if cached is not None:
                out[doc.document_id] = cached
                continue
        extraction = extract_issue(doc, debug_dir=debug_dir)
        cache_path.write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
        out[doc.document_id] = extraction
        if sleep_between:
            time.sleep(sleep_between)
    return out


_README = """\
---
license: cc-by-nc-4.0
task_categories:
- text-classification
- summarization
- token-classification
language:
- en
tags:
- ner
- historical-documents
- southern-africa
- human-rights
- articles
size_categories:
- n<1K
---

# focus-processed-articles

Issue-level structured extraction of *FOCUS on Political Repression in Southern
Africa*, the news bulletin of the International Defence & Aid Fund.

For each document (issue, briefing, sermon, index volume) the corrected
dots.ocr layout from
[`bitter-aloe/focus-raw-ocr`](https://huggingface.co/datasets/bitter-aloe/focus-raw-ocr)
is reorganized by Gemini 3.1 Flash Lite Preview into a sequence of editorial
sections (front matter, articles, end matter), with per-section lists of every
mentioned person, place, and organization.

## Schema

| field            | type                  | description |
|------------------|-----------------------|-------------|
| `issue_id`       | string                | Stable document id, e.g. `Issue 01`. |
| `issue_name`     | string                | Human label, e.g. `Issue 01`. |
| `parent_folder`  | string \\| null        | Parent folder if any (e.g. `Index 0`, `Other Doc`). |
| `num_pages`      | int32                 | Number of pages in the issue. |
| `is_validated`   | bool                  | True iff every page was human-validated. |
| `page_ids`       | sequence<string>      | Canonical page ids, in reading order. |
| `layouts`        | sequence<string>      | Per-page dots.ocr layout JSON (string-encoded). |
| `page_images`    | sequence<Image>       | Original page renders, in reading order. |
| `issue_title`    | string \\| null        | Title from the masthead, if any. |
| `issue_summary`  | string                | Short summary of the issue. |
| `sections`       | sequence<Section>     | The structured extraction; see below. |
| `sections_json`  | string                | Raw JSON of the full extraction. |

### Section

```
section_id     : string
section_type   : "front_matter" | "article" | "end_matter"
title          : string
summary        : string
body           : string  (reflowed text, paragraphs separated by blank lines)
page_start     : int32
page_end       : int32
people         : [ { name: string, canonical: string|null } ]
places         : [ { name: string, canonical: string|null } ]
organizations  : [ { name: string, canonical: string|null } ]
```

## Extraction model

```
gemini-3.1-flash-lite-preview
```

The model is fed the entire issue's corrected layout JSON in one prompt and is
asked to return JSON conforming to the schema above. No images are sent.

## License & terms

Released by The Bitter Aloe Project under CC-BY-NC-4.0 for non-commercial
research use. The underlying *FOCUS* publication is © the International
Defence & Aid Fund and its successors.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corrected-dir", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "output" / "processed",
        help="Where Gemini extractions are cached as JSON.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "output" / "focus-processed-articles",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="If set, only process these document_ids.",
    )
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--repo-id", default=HF_REPO_ID)
    parser.add_argument("--private", action="store_true")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Optional delay between Gemini calls.",
    )
    args = parser.parse_args()

    pages = list(iter_page_records(args.corrected_dir, args.images_dir))
    docs = group_into_documents(pages)
    if args.only:
        only = set(args.only)
        docs = [d for d in docs if d.document_id in only]
    print(f"Processing {len(docs)} documents.")

    extractions = process_documents(docs, args.cache_dir, sleep_between=args.sleep)

    rows = []
    for doc in docs:
        if doc.document_id not in extractions:
            continue
        rows.append(_row_for(doc, extractions[doc.document_id]))

    ds = Dataset.from_list(rows, features=_build_features())
    print(ds)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ds.save_to_disk(str(args.out_dir))
    readme_path = args.out_dir / "README.md"
    readme_path.write_text(_README, encoding="utf-8")
    print(f"Saved to {args.out_dir}")

    if args.push:
        from huggingface_hub import HfApi

        api = HfApi()
        print(f"Ensuring dataset repo {args.repo_id} exists ...")
        api.create_repo(
            repo_id=args.repo_id,
            repo_type="dataset",
            private=args.private,
            exist_ok=True,
        )
        print(f"Pushing to {args.repo_id} ...")
        ds.push_to_hub(args.repo_id, private=args.private)
        api.upload_file(
            path_or_fileobj=readme_path,
            path_in_repo="README.md",
            repo_id=args.repo_id,
            repo_type="dataset",
        )
        print("Done.")


if __name__ == "__main__":
    main()
