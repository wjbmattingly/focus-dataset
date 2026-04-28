"""Rewrite ``issue_title`` to the strict ``MONTH YEAR`` schema.

We started life with whatever Gemini happened to copy off the masthead — values
like ``"NO1—NOVEMBER 1975"``, ``"No 3 March 1976"``, or ``None`` if the cover
was hard to read. Everything downstream wants a clean date, so this script:

1. Walks every issue JSON in ``output/processed/`` and ``docs/src/content/issues/``.
2. Tries to derive a ``MONTH YEAR`` value from the existing title. When that
   fails (e.g. Issues 02 and 05 came back null because their masthead block
   confused the model), it falls back to a hard-coded override map.
3. Writes the file back in place if the title changed.

Future Gemini calls now bake the schema into the system prompt + Pydantic
description, so this script is mostly a one-shot fix-up for the issues we have
already extracted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "output" / "processed"
CONTENT_DIR = ROOT / "docs" / "src" / "content" / "issues"

MONTHS = {
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
}
SEASONS = {"SPRING", "SUMMER", "AUTUMN", "FALL", "WINTER"}
TOKEN_RE = re.compile(r"[A-Za-z]+|\d{4}")

# Issues whose masthead Gemini couldn't read cleanly. Verified against the
# original page-001 OCR / images:
#   - Issue 02 cover: "No 2 January 1976"  -> /Users/wjm55/Downloads/focus_output/Issue 02
#   - Issue 05 cover: "No 5 July 1976"     -> /Users/wjm55/Downloads/focus_output/Issue 05
HARDCODED_TITLES: dict[str, str] = {
    "Issue 01": "NOVEMBER 1975",
    "Issue 02": "JANUARY 1976",
    "Issue 03": "MARCH 1976",
    "Issue 04": "MAY 1976",
    "Issue 05": "JULY 1976",
}


def normalize_title(raw: str | None) -> str | None:
    """Try to extract a 'MONTH YEAR' string from whatever Gemini gave us."""
    if not raw:
        return None
    tokens = [t.upper() for t in TOKEN_RE.findall(raw)]
    month: str | None = None
    year: str | None = None
    for tok in tokens:
        if month is None and (tok in MONTHS or tok in SEASONS):
            month = "AUTUMN" if tok == "FALL" else tok
        elif year is None and tok.isdigit() and len(tok) == 4:
            year = tok
    if month and year:
        return f"{month} {year}"
    return None


def fix_payload(payload: dict, issue_id: str) -> bool:
    """Mutate ``payload['issue_title']`` in place. Return True if changed."""
    current = payload.get("issue_title")
    new = normalize_title(current) or HARDCODED_TITLES.get(issue_id)
    if new is None:
        return False
    if current == new:
        return False
    payload["issue_title"] = new
    return True


def fix_file(path: Path, issue_id_key: str) -> tuple[bool, str | None, str | None]:
    payload = json.loads(path.read_text())
    issue_id = payload.get(issue_id_key) or path.stem.replace("-", " ").replace("_", " ")
    before = payload.get("issue_title")
    changed = fix_payload(payload, issue_id)
    if changed:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed, before, payload.get("issue_title")


def main() -> None:
    print(f"== {PROCESSED_DIR} ==")
    for path in sorted(PROCESSED_DIR.glob("*.json")):
        changed, before, after = fix_file(path, "issue_id")
        flag = "WRITE" if changed else "skip "
        print(f"  [{flag}] {path.name:25s} {before!r:35s} -> {after!r}")

    print(f"== {CONTENT_DIR} ==")
    for path in sorted(CONTENT_DIR.glob("*.json")):
        changed, before, after = fix_file(path, "issue_id")
        flag = "WRITE" if changed else "skip "
        print(f"  [{flag}] {path.name:25s} {before!r:35s} -> {after!r}")


if __name__ == "__main__":
    main()
