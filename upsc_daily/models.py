"""Plain data objects shared between the scraper, generator, storage and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Article:
    """One current-affairs item pulled from a feed."""

    title: str
    url: str
    source: str
    published: str
    summary: str = ""
    body: str = ""
    subject: str = "Mixed"
    fetched_on: str = field(default_factory=lambda: date.today().isoformat())
    id: int | None = None

    def text(self, limit: int = 4000) -> str:
        combined = (self.body or self.summary or "").strip()
        return combined[:limit]


@dataclass
class Question:
    """A UPSC Prelims style MCQ."""

    stem: str
    options: list[str]
    answer_index: int
    explanation: str = ""
    statements: list[str] = field(default_factory=list)
    pairs: list[list[str]] = field(default_factory=list)
    qtype: str = "statements"
    subject: str = "Mixed"
    difficulty: str = "Medium"
    source_url: str = ""
    source_title: str = ""
    pyq_link: str = ""
    origin: str = "llm"
    for_date: str = field(default_factory=lambda: date.today().isoformat())
    id: int | None = None

    @property
    def answer_letter(self) -> str:
        return "abcd"[self.answer_index].upper() if 0 <= self.answer_index < 4 else "?"


@dataclass
class MainsQuestion:
    """A GS Mains answer-writing prompt."""

    question: str
    gs_paper: str = "GS-II"
    marks: int = 15
    directive: str = "Discuss"
    hints: list[str] = field(default_factory=list)
    source_url: str = ""
    source_title: str = ""
    for_date: str = field(default_factory=lambda: date.today().isoformat())
    id: int | None = None
