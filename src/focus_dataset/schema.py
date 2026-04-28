"""Pydantic models for the structured article output produced by Gemini."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SectionType = Literal["front_matter", "article", "end_matter"]


class Entity(BaseModel):
    """A named entity found in the text."""

    name: str = Field(..., description="The surface form as it appears in the article.")
    canonical: str | None = Field(
        None,
        description=(
            "An optional canonical / disambiguated form, e.g. 'Nelson Mandela' "
            "for 'Mr. Mandela'. Leave null if the surface form is already canonical."
        ),
    )


class Section(BaseModel):
    """One contiguous section in an issue."""

    section_id: str = Field(
        ...,
        description=(
            "Stable lowercase slug-ish id unique within the issue, e.g. "
            "'detentions-in-south-africa' or 'masthead'."
        ),
    )
    section_type: SectionType
    title: str = Field(
        ...,
        description=(
            "Human-readable title. For front/end matter use a descriptive label "
            "such as 'Masthead', 'Table of Contents', 'Subscription form'."
        ),
    )
    summary: str = Field(
        ...,
        description="One- to three-sentence neutral summary of this section.",
    )
    body: str = Field(
        ...,
        description=(
            "Full reflowed body text of this section, in reading order, joined "
            "across pages where the section spans multiple pages. Preserve "
            "paragraph breaks with blank lines."
        ),
    )
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)
    people: list[Entity] = Field(default_factory=list)
    places: list[Entity] = Field(default_factory=list)
    organizations: list[Entity] = Field(default_factory=list)


class IssueExtraction(BaseModel):
    """The structured extraction of an entire issue."""

    issue_id: str
    issue_title: str | None = Field(
        None,
        description="The masthead/cover title of the issue if visible, e.g. 'NO 10 SPRING 1977'.",
    )
    issue_summary: str = Field(
        ...,
        description="Short paragraph summarizing the contents of this issue.",
    )
    sections: list[Section]


# JSON schema we send to Gemini (drops top-level issue_id which we set ourselves).
GEMINI_RESPONSE_SCHEMA = IssueExtraction.model_json_schema()
