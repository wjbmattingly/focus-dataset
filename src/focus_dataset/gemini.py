"""Thin wrapper around google-genai for issue-level article extraction."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

from .data import DocumentRecord, load_layout
from .schema import IssueExtraction


MODEL_NAME = "gemini-3.1-flash-lite-preview"


SYSTEM_INSTRUCTION = """You are an archival NLP assistant working on the FOCUS bulletin published by the International Defence & Aid Fund for Southern Africa (1975-1990s).

You will receive the dots.ocr layout JSON for every page of a single issue, in
reading order. Each block has:
  - bbox: [x1, y1, x2, y2]
  - category: Title, Section-header, Text, List-item, Footnote, Picture, Page-footer, Page-header, Caption, Table, ...
  - reading_order: integer order on the page (lower = earlier)
  - text: present for all categories that contain text

Your job is to reconstruct the editorial structure of the issue:

1. Group the text blocks into a contiguous sequence of sections covering the entire
   issue. There must be no gaps. Use these section types:
     - "front_matter": masthead, cover, table of contents, editorial colophon, distribution box, etc.
     - "article": each editorial article or news report.
     - "end_matter": subscription forms, donation appeals, address blocks, back-cover credits.
2. Articles may span multiple pages. Merge continuations from later pages into the same
   article, dropping running headers/footers/page numbers.
3. The body must be the reflowed prose in correct reading order, using the
   `reading_order` field for ordering within a page and the natural page sequence
   across pages. Preserve paragraph breaks with blank lines. Do not invent text.
4. For each section list every PERSON, PLACE (city, town, country, region) and
   ORGANIZATION (political party, government body, NGO, court, military unit,
   newspaper, prison, etc.) that is mentioned in that section. For each
   mention, emit an Entity object with two fields:
     - `name`: the SURFACE FORM exactly as it appears in the text. We want to
       capture variance, so if the same person/place/org appears under several
       different surface forms inside one section ("Mr. Vorster", "B. J. Vorster",
       "the Prime Minister"; "South Africa", "the Republic"; "African National
       Congress", "ANC"), emit one Entity per DISTINCT surface form within the
       section. Do not invent surface forms that do not appear in the text.
     - `canonical`: a STANDARDIZED form that disambiguates this entity. Always
       supply it when you can resolve the reference confidently. Conventions:
         * People — full given name + surname when known, e.g. "B. J. Vorster",
           "Nelson Mandela", "Steve Biko". Strip honorifics (Mr., Mrs., Dr.,
           Rev.). For people known only by surname or initials, use the most
           complete form available in this issue or in well-known historical
           record.
         * Places — full conventional English name, e.g. "South Africa", "Cape
           Town", "Robben Island", "Pretoria Central Prison".
         * Organizations — full official name with the acronym in parentheses
           if both are common, e.g. "African National Congress (ANC)", "South
           African Students Organisation (SASO)", "Pan-Africanist Congress
           (PAC)". Newspapers as "Rand Daily Mail", courts as "Supreme Court of
           South Africa".
       Leave `canonical` null ONLY when you genuinely cannot resolve the
       reference (e.g. an unnamed witness or a vague phrase like "police").
       Multiple Entity objects that refer to the same real-world person/place/
       organization MUST share the same `canonical` string. Within one section,
       deduplicate by (surface form, canonical) — i.e. don't list the exact
       same surface form twice, but DO list distinct surface forms separately.
   Do NOT include cited sources like "(RDM 27.8.75)" or "(Star 4.10.75)"
   unless the publication is itself a subject of the article.
5. Give every section a stable lowercase slug-ish `section_id` unique within the
   issue.
6. The top-level `issue_title` MUST follow the strict schema "MONTH YEAR" —
   uppercase English month name plus 4-digit year, e.g. "NOVEMBER 1975",
   "JANUARY 1976", "JULY 1976". Do NOT include the issue number ("No 5",
   "NO1—", "No. 10") in `issue_title`; the issue number lives in `issue_id`.
   If the cover shows a season instead of a month, use "SPRING 1977",
   "SUMMER 1977", "AUTUMN 1977" or "WINTER 1977". Set `issue_title` to null
   only when the cover/masthead shows no date at all.
7. Always respond with JSON matching the provided schema. Do not include any
   prose outside the JSON.
"""


def _build_layout_payload(doc: DocumentRecord) -> dict[str, Any]:
    """Build a compact JSON payload describing the entire issue's layout."""
    pages: list[dict[str, Any]] = []
    for page in doc.pages:
        layout = load_layout(page)
        compact_blocks: list[dict[str, Any]] = []
        for block in layout:
            entry: dict[str, Any] = {
                "category": block.get("category"),
                "reading_order": block.get("reading_order"),
                "bbox": block.get("bbox"),
            }
            if "text" in block and block["text"]:
                entry["text"] = block["text"]
            if "group_id" in block:
                entry["group_id"] = block["group_id"]
            compact_blocks.append(entry)
        pages.append(
            {
                "page_number": page.page_number,
                "page_id": page.page_id,
                "blocks": compact_blocks,
            }
        )
    return {
        "issue_id": doc.document_id,
        "issue_name": doc.document_name,
        "num_pages": doc.num_pages,
        "pages": pages,
    }


def _make_client(api_key: str | None = None) -> genai.Client:
    if api_key is None:
        load_dotenv()
        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to .env or pass it explicitly."
        )
    return genai.Client(api_key=api_key)


def extract_issue(
    doc: DocumentRecord,
    *,
    client: genai.Client | None = None,
    model: str = MODEL_NAME,
    debug_dir: Path | None = None,
    max_attempts: int = 3,
) -> IssueExtraction:
    """Run Gemini on a full issue's layout and return the parsed extraction."""
    client = client or _make_client()

    payload = _build_layout_payload(doc)
    user_text = (
        "Here is the layout JSON for one issue of FOCUS. Extract the section "
        "structure as instructed.\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    )

    config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=IssueExtraction,
        temperature=0.1,
    )

    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_text,
                config=config,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt == max_attempts:
                raise
            time.sleep(2 * attempt)
    else:  # pragma: no cover
        raise RuntimeError(f"Gemini call failed: {last_err}")

    raw_text = response.text or ""
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        slug = doc.document_id.replace("/", "__")
        (debug_dir / f"{slug}.input.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (debug_dir / f"{slug}.output.json").write_text(raw_text, encoding="utf-8")

    parsed = response.parsed
    if isinstance(parsed, IssueExtraction):
        extraction = parsed
    else:
        extraction = IssueExtraction.model_validate_json(raw_text)

    extraction = extraction.model_copy(update={"issue_id": doc.document_id})
    return extraction
