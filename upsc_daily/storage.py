"""SQLite persistence for articles, generated questions and quiz attempts."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Iterable

from .config import DB_PATH, DATA_DIR
from .models import Article, MainsQuestion, Question

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    source TEXT,
    published TEXT,
    summary TEXT,
    body TEXT,
    subject TEXT,
    fetched_on TEXT
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stem TEXT NOT NULL,
    statements TEXT,
    pairs TEXT,
    options TEXT NOT NULL,
    answer_index INTEGER NOT NULL,
    explanation TEXT,
    qtype TEXT,
    subject TEXT,
    difficulty TEXT,
    source_url TEXT,
    source_title TEXT,
    pyq_link TEXT,
    origin TEXT,
    for_date TEXT
);
CREATE TABLE IF NOT EXISTS mains_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    gs_paper TEXT,
    marks INTEGER,
    directive TEXT,
    hints TEXT,
    source_url TEXT,
    source_title TEXT,
    for_date TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER,
    chosen INTEGER,
    correct INTEGER,
    attempted_on TEXT
);
CREATE INDEX IF NOT EXISTS idx_q_date ON questions(for_date);
CREATE INDEX IF NOT EXISTS idx_a_date ON articles(fetched_on);
"""


class Store:
    """Thin wrapper over a single SQLite file."""

    def __init__(self, path=DB_PATH) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- articles ----------
    def save_articles(self, articles: Iterable[Article]) -> int:
        new = 0
        for a in articles:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO articles"
                " (title, url, source, published, summary, body, subject, fetched_on)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (a.title, a.url, a.source, a.published, a.summary, a.body, a.subject, a.fetched_on),
            )
            if cur.rowcount:
                new += 1
        self.conn.commit()
        return new

    def articles_for(self, day: str | None = None) -> list[Article]:
        day = day or date.today().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE fetched_on = ? ORDER BY id DESC", (day,)
        ).fetchall()
        return [self._article(r) for r in rows]

    def recent_articles(self, limit: int = 200) -> list[Article]:
        rows = self.conn.execute(
            "SELECT * FROM articles ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._article(r) for r in rows]

    @staticmethod
    def _article(r: sqlite3.Row) -> Article:
        return Article(
            id=r["id"], title=r["title"], url=r["url"], source=r["source"],
            published=r["published"], summary=r["summary"] or "", body=r["body"] or "",
            subject=r["subject"] or "Mixed", fetched_on=r["fetched_on"],
        )

    # ---------- prelims questions ----------
    def save_questions(self, questions: Iterable[Question]) -> None:
        for q in questions:
            cur = self.conn.execute(
                "INSERT INTO questions (stem, statements, pairs, options, answer_index,"
                " explanation, qtype, subject, difficulty, source_url, source_title,"
                " pyq_link, origin, for_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    q.stem, json.dumps(q.statements), json.dumps(q.pairs),
                    json.dumps(q.options), q.answer_index, q.explanation, q.qtype,
                    q.subject, q.difficulty, q.source_url, q.source_title, q.pyq_link,
                    q.origin, q.for_date,
                ),
            )
            q.id = cur.lastrowid
        self.conn.commit()

    def questions_for(self, day: str | None = None) -> list[Question]:
        day = day or date.today().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM questions WHERE for_date = ? ORDER BY id", (day,)
        ).fetchall()
        return [self._question(r) for r in rows]

    def question_dates(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT for_date FROM questions ORDER BY for_date DESC"
        ).fetchall()
        return [r["for_date"] for r in rows]

    @staticmethod
    def _question(r: sqlite3.Row) -> Question:
        return Question(
            id=r["id"], stem=r["stem"], statements=json.loads(r["statements"] or "[]"),
            pairs=json.loads(r["pairs"] or "[]"), options=json.loads(r["options"]),
            answer_index=r["answer_index"], explanation=r["explanation"] or "",
            qtype=r["qtype"] or "statements", subject=r["subject"] or "Mixed",
            difficulty=r["difficulty"] or "Medium", source_url=r["source_url"] or "",
            source_title=r["source_title"] or "", pyq_link=r["pyq_link"] or "",
            origin=r["origin"] or "llm", for_date=r["for_date"],
        )

    # ---------- mains questions ----------
    def save_mains(self, items: Iterable[MainsQuestion]) -> None:
        for m in items:
            cur = self.conn.execute(
                "INSERT INTO mains_questions (question, gs_paper, marks, directive, hints,"
                " source_url, source_title, for_date) VALUES (?,?,?,?,?,?,?,?)",
                (m.question, m.gs_paper, m.marks, m.directive, json.dumps(m.hints),
                 m.source_url, m.source_title, m.for_date),
            )
            m.id = cur.lastrowid
        self.conn.commit()

    def mains_for(self, day: str | None = None) -> list[MainsQuestion]:
        day = day or date.today().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM mains_questions WHERE for_date = ? ORDER BY id", (day,)
        ).fetchall()
        return [
            MainsQuestion(
                id=r["id"], question=r["question"], gs_paper=r["gs_paper"] or "GS-II",
                marks=r["marks"] or 15, directive=r["directive"] or "Discuss",
                hints=json.loads(r["hints"] or "[]"), source_url=r["source_url"] or "",
                source_title=r["source_title"] or "", for_date=r["for_date"],
            )
            for r in rows
        ]

    def clear_day(self, day: str) -> None:
        self.conn.execute("DELETE FROM questions WHERE for_date = ?", (day,))
        self.conn.execute("DELETE FROM mains_questions WHERE for_date = ?", (day,))
        self.conn.commit()

    # ---------- attempts / stats ----------
    def record_attempt(self, question_id: int | None, chosen: int, correct: bool) -> None:
        if question_id is None:
            return
        self.conn.execute(
            "INSERT INTO attempts (question_id, chosen, correct, attempted_on) VALUES (?,?,?,?)",
            (question_id, chosen, int(correct), date.today().isoformat()),
        )
        self.conn.commit()

    def subject_accuracy(self) -> list[tuple[str, int, int]]:
        rows = self.conn.execute(
            "SELECT q.subject AS subject, COUNT(*) AS n, SUM(a.correct) AS ok"
            " FROM attempts a JOIN questions q ON q.id = a.question_id"
            " GROUP BY q.subject ORDER BY n DESC"
        ).fetchall()
        return [(r["subject"] or "Mixed", r["n"], r["ok"] or 0) for r in rows]

    def totals(self) -> tuple[int, int, int]:
        arts = self.conn.execute("SELECT COUNT(*) c FROM articles").fetchone()["c"]
        qs = self.conn.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"]
        att = self.conn.execute("SELECT COUNT(*) c FROM attempts").fetchone()["c"]
        return arts, qs, att
