"""Canonical legend for source abbreviations used in FOCUS bulletins.

Most FOCUS issues print a "Sources and abbreviations" block on the inside back
cover that defines every short-form citation used in the body text, e.g.::

    BBC - British Broadcasting Corporation Survey of World Broadcasts;
    GN  - Guardian, London;
    RDM - Rand Daily Mail, Johannesburg;
    ...

The legend evolved over time as papers were founded, closed, or renamed (Post
Johannesburg disappears after 1981, the Weekly Mail appears in the mid-80s,
etc.). The mapping below is the *union* of every back-cover legend observed
across Issues 2-93 plus the Briefings/Fact Papers, so a single table is
sufficient to resolve any abbreviation to a canonical publication.

We use this table for two things:

1. It is embedded in the Gemini system prompt so the model can disambiguate
   abbreviations consistently even on issues where the back-cover legend was
   not OCR'd cleanly.
2. Downstream tooling (e.g. the website) can show the canonical name when
   rendering a citation chip.
"""

from __future__ import annotations


# (abbreviation, canonical full name)
#
# Keep abbreviations *as printed* in the originals. Several abbreviations
# changed punctuation over time (e.g. "S. Exp" vs "S Exp") - we include both
# forms so the model can canonicalize either. The canonical names use the
# most common spelling observed in the legends.
SOURCE_LEGEND: list[tuple[str, str]] = [
    # --- South African newspapers ---
    ("BBC", "British Broadcasting Corporation Survey/Summary of World Broadcasts, London"),
    ("Cit", "The Citizen, Johannesburg"),
    ("Citizen", "The Citizen, Johannesburg"),
    ("CH", "Cape Herald"),
    ("CP", "City Press, Johannesburg"),
    ("CT", "Cape Times, Cape Town"),
    ("DD", "Daily Dispatch, East London"),
    ("DN", "Daily News, Durban"),
    ("EP", "Evening Post, Port Elizabeth"),
    ("EPH", "Eastern Province Herald, Port Elizabeth"),
    ("FM", "Financial Mail, Johannesburg"),
    ("NM", "Natal Mercury, Durban"),
    ("NW", "Natal Witness, Pietermaritzburg"),
    ("Post", "Post, Johannesburg"),
    ("RDM", "Rand Daily Mail, Johannesburg"),
    ("S", "Sowetan, Johannesburg"),
    ("S. Exp", "Sunday Express, Johannesburg"),
    ("S Exp", "Sunday Express, Johannesburg"),
    ("SP", "Sunday Post, Johannesburg"),
    ("S Star", "Sunday Star, Johannesburg"),
    ("ST", "Sunday Times, Johannesburg"),
    ("Star", "The Star, Johannesburg"),
    ("S Trib", "Sunday Tribune, Durban"),
    ("S. Trib.", "Sunday Tribune, Durban"),
    ("W", "The World, Johannesburg"),
    ("World", "The World, Johannesburg"),
    ("WM", "Weekly Mail, Johannesburg"),
    # --- South African government / institutional sources ---
    ("Debates", "House of Assembly / Parliamentary Debates, Cape Town (Hansard)"),
    ("GG", "Government Gazette, Pretoria"),
    ("SAIRR", "South African Institute of Race Relations"),
    ("HRC", "Human Rights Commission, Johannesburg"),
    # --- Namibia ---
    ("Nam", "The Namibian, Windhoek"),
    ("NCC", "Namibia Communications Centre, London"),
    ("TN", "Times of Namibia, Windhoek"),
    ("WA", "Windhoek Advertiser, Windhoek"),
    ("WO", "Windhoek Observer, Windhoek"),
    # --- Rhodesia / Zimbabwe ---
    ("RH", "Rhodesia Herald, Salisbury"),
    ("SM", "Sunday Mail, Salisbury"),
    ("ZT", "Zimbabwe Times, Salisbury"),
    ("ZPV", "Zimbabwe People's Voice, Lusaka"),
    # --- UK / international ---
    ("FT", "Financial Times, London"),
    ("GN", "The Guardian, London"),
    ("MS", "Morning Star, London"),
    ("Obs", "The Observer, London"),
    ("Tel", "Daily Telegraph, London"),
    ("T", "The Times, London"),
    ("Times", "The Times, London"),
    ("SS", "Southscan, London"),
    ("LWI", "Lutheran World Federation Information bulletin, Geneva"),
    ("SNS", "Solidarity News Service, Gaborone"),
    ("Africa", "'Africa' monthly, London"),
    # --- Internal cross-references ---
    # Articles routinely cite earlier issues of FOCUS itself ("see FOCUS 67 p.3").
    # We treat these as a single canonical source so the user can browse all
    # back-references in one place.
    ("FOCUS", "FOCUS bulletin (IDAF)"),
]


def legend_table() -> str:
    """Render the legend as a compact bullet list suitable for an LLM prompt."""
    return "\n".join(f"  - {abbr}: {full}" for abbr, full in SOURCE_LEGEND)


# Lookup map (abbreviation -> canonical). The first entry wins for duplicates,
# which is fine because duplicates point to the same publication.
SOURCE_CANONICAL: dict[str, str] = {}
for _abbr, _full in SOURCE_LEGEND:
    SOURCE_CANONICAL.setdefault(_abbr, _full)
