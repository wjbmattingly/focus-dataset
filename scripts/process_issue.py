"""Run gemini-3.1-flash-lite-preview on a single issue and print/save the result.

Usage:
    python scripts/process_issue.py --issue "Issue 01"
    python scripts/process_issue.py --issue "Issue 10"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from focus_dataset.data import (  # noqa: E402
    group_into_documents,
    iter_page_records,
)
from focus_dataset.gemini import extract_issue  # noqa: E402


DEFAULT_CORRECTED = Path.home() / "Downloads" / "entire_project_2026-03-24T152159"
DEFAULT_IMAGES = Path.home() / "Downloads" / "focus_output"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True, help="document_id, e.g. 'Issue 01'.")
    parser.add_argument("--corrected-dir", type=Path, default=DEFAULT_CORRECTED)
    parser.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "output" / "processed",
        help="Where to write the extraction JSON + Gemini debug payloads.",
    )
    args = parser.parse_args()

    pages = list(iter_page_records(args.corrected_dir, args.images_dir))
    docs = {d.document_id: d for d in group_into_documents(pages)}

    if args.issue not in docs:
        candidates = "\n  ".join(sorted(docs)[:30])
        raise SystemExit(
            f"No document with id {args.issue!r}.\nFirst few candidates:\n  {candidates}\n..."
        )

    doc = docs[args.issue]
    print(f"Processing {doc.document_id}: {doc.num_pages} pages")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = args.out_dir / "_debug"
    extraction = extract_issue(doc, debug_dir=debug_dir)

    slug = doc.document_id.replace("/", "__")
    out_path = args.out_dir / f"{slug}.json"
    out_path.write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")

    counts = {"front_matter": 0, "article": 0, "end_matter": 0}
    total_people = 0
    total_places = 0
    total_orgs = 0
    for s in extraction.sections:
        counts[s.section_type] = counts.get(s.section_type, 0) + 1
        total_people += len(s.people)
        total_places += len(s.places)
        total_orgs += len(s.organizations)

    print(json.dumps({
        "issue_id": extraction.issue_id,
        "issue_title": extraction.issue_title,
        "section_counts": counts,
        "total_people_mentions": total_people,
        "total_places_mentions": total_places,
        "total_organizations_mentions": total_orgs,
    }, indent=2))


if __name__ == "__main__":
    main()
