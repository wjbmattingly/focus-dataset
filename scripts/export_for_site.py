"""Export processed issues into the Astro site under docs/.

For every cached extraction in `output/processed/<slug>.json`, this script:
  1. Writes a single content JSON to `docs/src/content/issues/<slug>.json`
     containing the issue metadata, all sections, and a list of pages with
     their image paths.
  2. Downscales each page render to a webp and writes it to
     `docs/public/page-images/<slug>/<page_id>.webp`.

After running, `cd docs && npm run dev` will load the issues automatically.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402
from tqdm import tqdm  # noqa: E402

from focus_dataset.data import (  # noqa: E402
    DocumentRecord,
    group_into_documents,
    iter_page_records,
)
from focus_dataset.schema import IssueExtraction  # noqa: E402


SITE_ROOT = ROOT / "docs"
CONTENT_DIR = SITE_ROOT / "src" / "content" / "issues"
IMAGE_DIR = SITE_ROOT / "public" / "page-images"


def _slug(document_id: str) -> str:
    """File-system-safe slug for a document id."""
    s = document_id.replace("/", "__").replace(" ", "-")
    s = re.sub(r"[^A-Za-z0-9_\-.]+", "", s)
    return s


def _section_url_slug(section_id: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", section_id.lower()).strip("-")
    return s or "section"


def _resize_image(src: Path, dst: Path, max_width: int, quality: int) -> tuple[int, int]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = img.convert("RGB")
        w, h = img.size
        if w > max_width:
            new_h = round(h * max_width / w)
            img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)
        img.save(dst, "WEBP", quality=quality, method=6)
        return img.size


def _safe_page_name(page_id: str) -> str:
    """URL- and filesystem-safe variant of a page id."""
    s = page_id.replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9_\-.]+", "", s)
    return s


def _site_image_path(slug: str, page_id: str) -> str:
    return f"/page-images/{slug}/{_safe_page_name(page_id)}.webp"


def export_issue(
    doc: DocumentRecord,
    extraction: IssueExtraction,
    *,
    max_width: int,
    quality: int,
    skip_images: bool,
) -> Path:
    slug = _slug(doc.document_id)
    dst_dir = IMAGE_DIR / slug
    pages: list[dict] = []
    for page in tqdm(doc.pages, desc=f"  images {slug}", leave=False):
        out_image = dst_dir / f"{_safe_page_name(page.page_id)}.webp"
        if skip_images and out_image.is_file():
            with Image.open(out_image) as img:
                w, h = img.size
        else:
            w, h = _resize_image(page.image_path, out_image, max_width, quality)
        pages.append(
            {
                "page_id": page.page_id,
                "page_number": page.page_number,
                "image": _site_image_path(slug, page.page_id),
                "width": w,
                "height": h,
            }
        )

    sections = []
    for section in extraction.sections:
        d = section.model_dump()
        d["url_slug"] = _section_url_slug(section.section_id)
        sections.append(d)

    payload = {
        "issue_id": doc.document_id,
        "issue_name": doc.document_name,
        "parent_folder": doc.parent_folder,
        "issue_title": extraction.issue_title,
        "issue_summary": extraction.issue_summary,
        "num_pages": doc.num_pages,
        "is_validated": all(p.is_validated for p in doc.pages),
        "pages": pages,
        "sections": sections,
    }

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CONTENT_DIR / f"{slug}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corrected-dir",
        type=Path,
        default=Path.home() / "Downloads" / "entire_project_2026-03-24T152159",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path.home() / "Downloads" / "focus_output",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "output" / "processed",
        help="Where Gemini extraction JSON files live.",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="If set, only export these document_ids.",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=1100,
        help="Resize page images so their width is at most this many px.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=78,
        help="WebP quality (1-100).",
    )
    parser.add_argument(
        "--rebuild-images",
        action="store_true",
        help="Force re-encoding of page images even when the webp already exists.",
    )
    args = parser.parse_args()

    pages = list(iter_page_records(args.corrected_dir, args.images_dir))
    docs = {d.document_id: d for d in group_into_documents(pages)}

    extraction_files = sorted(args.cache_dir.glob("*.json"))
    extraction_files = [p for p in extraction_files if not p.name.startswith("_")]

    selected = set(args.only) if args.only else None
    n = 0
    for path in extraction_files:
        try:
            extraction = IssueExtraction.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! skipping {path.name}: {exc}")
            continue
        doc_id = extraction.issue_id
        if selected and doc_id not in selected:
            continue
        if doc_id not in docs:
            print(f"  ! no document data for {doc_id!r}")
            continue
        out = export_issue(
            docs[doc_id],
            extraction,
            max_width=args.max_width,
            quality=args.quality,
            skip_images=not args.rebuild_images,
        )
        print(f"  + {out.relative_to(ROOT)}")
        n += 1

    print(f"Exported {n} issue(s) to {CONTENT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
