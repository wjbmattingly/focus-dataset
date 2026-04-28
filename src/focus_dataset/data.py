"""Scan the corrected dots.ocr export and align it with the source images.

The corrected export is a flat directory with two files per page:

    <page_name>.json
    <page_name>_metadata.json   # has folder_name, file_path, is_validated

The image directory mirrors the original on-disk layout used by the
correction tool. The image for a page lives at:

    <images_dir> / <folder_name> / <page_name>_original.png

(or one further level down if the metadata's `file_path` includes a
sub-folder, e.g. `Index 0/Index 03/Index 03_page_001.json`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


_PAGE_NUM_RE = re.compile(r"_page_(\d+)$")


@dataclass
class PageRecord:
    """One page in the corrected dataset, joined to its source image."""

    document_id: str           # logical document, e.g. "Issue 01", "Other Doc/Briefing 8"
    document_name: str         # human label, e.g. "Issue 01"
    page_id: str               # canonical page id, e.g. "Issue 1_page_001"
    page_number: int           # 1-based page number within the document (assigned at grouping)
    is_validated: bool
    layout_path: Path          # corrected layout JSON
    metadata_path: Path        # _metadata.json sidecar
    image_path: Path           # *_original.png in the images dir
    annotated_path: Path | None  # *_annotated.png if present
    relative_path: str         # file_path from metadata, e.g. "Issue 01/Issue 1_page_001.json"


@dataclass
class DocumentRecord:
    """A logical document (issue, briefing, sermon, index volume)."""

    document_id: str
    document_name: str
    parent_folder: str | None     # for Index 0/Index 03 -> "Index 0"
    pages: list[PageRecord] = field(default_factory=list)

    @property
    def num_pages(self) -> int:
        return len(self.pages)


def _page_sort_key(page_id: str) -> tuple:
    """Sort key that handles every observed naming convention.

    Examples (all sort in correct page order):
      - "Issue 1_page_001", "Issue 1_page_002", ..., "Issue 1_page_011"
      - "I1001_page_001", "I1002_page_001", ..., "I1020_page_001"
      - "I87a01_page_001", "I87a03_page_001", "I87a04_page_001"
      - "Sermon 0101_page_001", "Sermon 0102_page_001"
    """
    # Pull the trailing 3-digit page number from "_page_NNN".
    m = _PAGE_NUM_RE.search(page_id)
    trailing = int(m.group(1)) if m else 0
    head = _PAGE_NUM_RE.sub("", page_id)
    # Find the last run of digits in the head; that is usually the page number
    # for the I10NN / Sermon 0101 / I87aNN naming styles.
    head_digits = re.findall(r"\d+", head)
    last_head_num = int(head_digits[-1]) if head_digits else 0
    return (trailing if trailing > 1 else 0, last_head_num, page_id)


def _document_id_from_relpath(rel_path: str, folder_name: str) -> tuple[str, str | None]:
    """Return (document_id, parent_folder).

    For paths like ``Index 0/Index 03/Index 03_page_001.json`` we want
    ``document_id="Index 0/Index 03"`` and ``parent_folder="Index 0"``.

    For flat paths like ``Issue 01/Issue 1_page_001.json`` we want
    ``document_id="Issue 01"`` and ``parent_folder=None``.
    """
    parts = rel_path.split("/")
    if len(parts) >= 3:
        parent = parts[0]
        return f"{parent}/{folder_name}", parent
    return folder_name, None


def _load_metadata(metadata_path: Path) -> dict[str, Any]:
    with metadata_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_image_path(images_dir: Path, rel_path: str, page_id: str, suffix: str) -> Path:
    """Resolve to an `_original.png` (or `_annotated.png`) in the images dir.

    `rel_path` is the metadata's file_path (e.g. ``Issue 10/I1001_page_001.json``).
    The image lives in the same directory, with the page_id prefix.
    """
    rel_dir = Path(rel_path).parent
    return images_dir / rel_dir / f"{page_id}{suffix}"


def iter_page_records(corrected_dir: Path, images_dir: Path) -> Iterator[PageRecord]:
    """Yield one PageRecord per corrected page found in `corrected_dir`."""
    for meta_path in sorted(corrected_dir.glob("*_metadata.json")):
        meta = _load_metadata(meta_path)
        page_id: str = meta["page_name"]
        folder_name: str = meta["folder_name"]
        rel_path: str = meta["file_path"]
        is_validated: bool = bool(meta.get("is_validated", False))

        layout_path = corrected_dir / f"{page_id}.json"
        if not layout_path.is_file():
            continue

        document_id, parent_folder = _document_id_from_relpath(rel_path, folder_name)

        original_image = _resolve_image_path(images_dir, rel_path, page_id, "_original.png")
        annotated_image = _resolve_image_path(images_dir, rel_path, page_id, "_annotated.png")

        if not original_image.is_file():
            continue

        yield PageRecord(
            document_id=document_id,
            document_name=folder_name,
            page_id=page_id,
            page_number=0,  # assigned after grouping & sorting
            is_validated=is_validated,
            layout_path=layout_path,
            metadata_path=meta_path,
            image_path=original_image,
            annotated_path=annotated_image if annotated_image.is_file() else None,
            relative_path=rel_path,
        )


def group_into_documents(pages: list[PageRecord]) -> list[DocumentRecord]:
    """Group page records into their parent documents, sorted by page_id."""
    by_doc: dict[str, DocumentRecord] = {}
    for page in pages:
        doc = by_doc.get(page.document_id)
        if doc is None:
            parent = page.document_id.split("/", 1)[0] if "/" in page.document_id else None
            doc = DocumentRecord(
                document_id=page.document_id,
                document_name=page.document_name,
                parent_folder=parent,
            )
            by_doc[page.document_id] = doc
        doc.pages.append(page)

    for doc in by_doc.values():
        doc.pages.sort(key=lambda p: _page_sort_key(p.page_id))
        for idx, page in enumerate(doc.pages, start=1):
            page.page_number = idx

    return sorted(by_doc.values(), key=lambda d: d.document_id)


def load_layout(page: PageRecord) -> list[dict[str, Any]]:
    """Load the corrected layout JSON for a page."""
    with page.layout_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
