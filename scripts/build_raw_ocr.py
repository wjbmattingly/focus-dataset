"""Build & optionally push the `bitter-aloe/focus-raw-ocr` dataset.

One row per page:
  - image (PIL)
  - document_id, document_name, parent_folder
  - page_id, page_number
  - is_validated
  - layout (JSON-encoded list of dots.ocr blocks - the corrected version)
  - markdown (concatenated text in reading order, for easy preview)

Parquet is the on-disk format; image bytes are inlined.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datasets import Dataset, Features, Image, Value  # noqa: E402
from tqdm import tqdm  # noqa: E402

from focus_dataset.data import (  # noqa: E402
    PageRecord,
    group_into_documents,
    iter_page_records,
    load_layout,
)


HF_REPO_ID = "bitter-aloe/focus-raw-ocr"


def _layout_to_markdown(layout: list[dict]) -> str:
    """Flatten the layout into reading-order markdown text for previews."""
    blocks = [b for b in layout if "text" in b and b["text"]]
    blocks.sort(key=lambda b: (b.get("reading_order", 0), b.get("bbox", [0])[1]))

    lines: list[str] = []
    for block in blocks:
        category = block.get("category") or "Text"
        text = block["text"].strip()
        if not text:
            continue
        if category in ("Title", "Section-header"):
            lines.append(f"## {text}")
        elif category == "List-item":
            lines.append(f"- {text}")
        elif category == "Footnote":
            lines.append(f"> {text}")
        elif category == "Caption":
            lines.append(f"*{text}*")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


def _record_to_row(page: PageRecord) -> dict:
    layout = load_layout(page)
    return {
        "image": str(page.image_path),
        "document_id": page.document_id,
        "document_name": page.document_name,
        "parent_folder": page.document_id.split("/", 1)[0] if "/" in page.document_id else None,
        "page_id": page.page_id,
        "page_number": page.page_number,
        "is_validated": page.is_validated,
        "source_path": page.relative_path,
        "layout": json.dumps(layout, ensure_ascii=False),
        "markdown": _layout_to_markdown(layout),
    }


def build_dataset(corrected_dir: Path, images_dir: Path) -> Dataset:
    rows: list[dict] = []
    raw_pages = list(iter_page_records(corrected_dir, images_dir))
    docs = group_into_documents(raw_pages)
    pages = [p for d in docs for p in d.pages]
    print(f"Found {len(pages)} pages across {len(docs)} documents.")
    for page in tqdm(pages, desc="building rows"):
        rows.append(_record_to_row(page))

    features = Features(
        {
            "image": Image(),
            "document_id": Value("string"),
            "document_name": Value("string"),
            "parent_folder": Value("string"),
            "page_id": Value("string"),
            "page_number": Value("int32"),
            "is_validated": Value("bool"),
            "source_path": Value("string"),
            "layout": Value("string"),
            "markdown": Value("string"),
        }
    )
    ds = Dataset.from_list(rows, features=features)
    return ds


_README = """\
---
license: cc-by-nc-4.0
task_categories:
- image-to-text
- object-detection
language:
- en
tags:
- ocr
- layout
- historical-documents
- southern-africa
- human-rights
size_categories:
- 1K<n<10K
---

# focus-raw-ocr

Page-level corrected dots.ocr output for the *FOCUS on Political Repression in
Southern Africa* news bulletin, published by the International Defence & Aid
Fund from 1975 onwards.

Each row is one page of one document, joined to its rendered page image and the
manually-validated dots.ocr layout JSON (bounding boxes + categories + text +
reading order).

## Schema

| field            | type    | description |
|------------------|---------|-------------|
| `image`          | Image   | Original page render (PNG). |
| `document_id`    | string  | Stable document id (e.g. `Issue 01`, `Other Doc/Briefing 8`, `Index 0/Index 03`). |
| `document_name`  | string  | Human-readable document label. |
| `parent_folder`  | string  | Parent folder if any (e.g. `Index 0`, `Other Doc`), else null. |
| `page_id`        | string  | Canonical page id (e.g. `Issue 1_page_001`, `I1001_page_001`). |
| `page_number`    | int32   | 1-based page number within the document. |
| `is_validated`   | bool    | Whether a human reviewed this page. |
| `source_path`    | string  | Relative path of the JSON in the correction tool's project. |
| `layout`         | string  | JSON-encoded list of dots.ocr blocks (`bbox`, `category`, `text`, `reading_order`, optional `group_id`). |
| `markdown`       | string  | Reflowed markdown preview of the page in reading order. |

## Citation

If you use this dataset, please cite The Bitter Aloe Project:

```
@misc{bitter_aloe_focus_raw_ocr,
  title  = {focus-raw-ocr: Corrected dots.ocr layouts for the FOCUS bulletin},
  author = {The Bitter Aloe Project},
  year   = {2026},
  url    = {https://huggingface.co/datasets/bitter-aloe/focus-raw-ocr}
}
```

## License & terms

The code and structured annotations in this dataset are released by The Bitter
Aloe Project under CC-BY-NC-4.0 for non-commercial research use. The underlying
*FOCUS* publication is © the International Defence & Aid Fund and its
successors; please consult the original rightsholders for any commercial reuse
of the page imagery or transcribed text.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corrected-dir",
        type=Path,
        required=True,
        help="Directory with corrected JSON + _metadata.json sidecars.",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        required=True,
        help="Directory containing the per-folder original PNG renders.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "output" / "focus-raw-ocr",
        help="Where to save the parquet shards locally.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push to the Hugging Face hub at bitter-aloe/focus-raw-ocr.",
    )
    parser.add_argument(
        "--repo-id",
        default=HF_REPO_ID,
        help="Override the destination repo id.",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Create as a private dataset.",
    )
    args = parser.parse_args()

    ds = build_dataset(args.corrected_dir, args.images_dir)
    print(ds)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ds.save_to_disk(str(args.out_dir))
    print(f"Saved local dataset to {args.out_dir}")

    readme_path = args.out_dir / "README.md"
    readme_path.write_text(_README, encoding="utf-8")

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
