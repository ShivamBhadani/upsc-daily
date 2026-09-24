"""Build the public static site from the local database.

The site is a single-page app plus one JSON file per day, so it can be served by
any static host (GitHub Pages, Netlify, S3, a plain nginx root) with no backend.
Everything the desktop app shows is carried over: the paper, quiz mode with UPSC
marking, Mains, the news that triggered each question, the PYQ style model, and
progress — which lives in each visitor's own browser, exactly as the desktop
database is local to one machine.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from . import export, pyq
from .models import Article, MainsQuestion, Question
from .storage import Store

WEB_DIR = Path(__file__).parent / "web"

SITE_TITLE = "UPSC Daily"
SITE_TAGLINE = "Current affairs, set as Prelims questions — every day"


def _format_name(qtype: str) -> str:
    fmt = pyq.FORMAT_BY_KEY.get(qtype)
    return fmt.name if fmt else qtype


def _question_json(q: Question, index: int, day: str) -> dict:
    return {
        "id": f"{day}#{index}",
        "n": index,
        "stem": q.stem,
        "closing": pyq.closing_line(q.qtype, q.stem) if (q.statements or q.pairs) else "",
        "statements": q.statements,
        "pairs": q.pairs,
        "options": q.options,
        "answer": q.answer_index,
        "explanation": q.explanation,
        "qtype": q.qtype,
        "qtypeName": _format_name(q.qtype),
        "subject": q.subject,
        "difficulty": q.difficulty,
        "sourceUrl": q.source_url,
        "sourceTitle": q.source_title,
        "pyqLink": q.pyq_link,
        "origin": q.origin,
    }


def _mains_json(m: MainsQuestion, index: int) -> dict:
    return {
        "n": index,
        "question": m.question,
        "gsPaper": m.gs_paper,
        "marks": m.marks,
        "directive": m.directive,
        "hints": m.hints,
        "sourceUrl": m.source_url,
        "sourceTitle": m.source_title,
    }


def _article_json(a: Article) -> dict:
    return {
        "title": a.title,
        "url": a.url,
        "source": a.source,
        "published": a.published,
        "summary": (a.summary or a.body)[:400],
        "subject": a.subject,
    }


def _stamp_assets(html: str, versions: dict[str, str]) -> str:
    """Point asset references at a content-hashed URL so updates are never cached over."""
    def sub(match: re.Match) -> str:
        name = match.group(1)
        version = versions.get(name)
        return f"assets/{name}?v={version}" if version else match.group(0)

    return re.sub(r"assets/([A-Za-z0-9_.-]+)", sub, html)


def day_payload(store: Store, day: str) -> dict:
    """Everything the site needs to render one day's paper."""
    questions = store.questions_for(day)
    mains = store.mains_for(day)
    articles = store.articles_for(day)
    return {
        "date": day,
        "counts": {
            "prelims": len(questions),
            "mains": len(mains),
            "articles": len(articles),
        },
        "origins": sorted({q.origin for q in questions}),
        "subjectCounts": dict(Counter(q.subject for q in questions)),
        "formatCounts": dict(Counter(_format_name(q.qtype) for q in questions)),
        "questions": [_question_json(q, i, day) for i, q in enumerate(questions, 1)],
        "mains": [_mains_json(m, i) for i, m in enumerate(mains, 1)],
        "articles": [_article_json(a) for a in articles],
    }


def style_payload() -> dict:
    """The PYQ pattern model, rendered on the site's style page."""
    return {
        "formats": [
            {
                "key": f.key,
                "name": f.name,
                "share": f.share,
                "options": f.options,
                "blueprint": f.blueprint,
                "exemplar": f.exemplar,
            }
            for f in pyq.FORMATS
        ],
        "subjectWeights": pyq.SUBJECT_WEIGHTS,
        "trends": pyq.TRENDS,
        "mainsDirectives": pyq.MAINS_DIRECTIVES,
        "mainsPapers": pyq.MAINS_PAPERS,
    }


def build(store: Store, out_dir: Path, days: list[str] | None = None,
          stamp: str | None = None) -> dict:
    """Write the whole static site into `out_dir`. Returns a small summary."""
    out_dir = Path(out_dir)
    data_dir = out_dir / "data"
    papers_dir = out_dir / "papers"
    for d in (out_dir, data_dir, papers_dir, out_dir / "assets"):
        d.mkdir(parents=True, exist_ok=True)

    days = days or store.question_dates()
    days = sorted({d for d in days}, reverse=True)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d %H:%M")

    index_days = []
    for day in days:
        payload = day_payload(store, day)
        if not payload["questions"]:
            continue
        (data_dir / f"{day}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        # A printable, JavaScript-free copy of the same paper.
        export.write(day, store.questions_for(day), store.mains_for(day),
                     store.articles_for(day), fmt="html",
                     path=papers_dir / f"{day}.html")

        index_days.append({
            "date": day,
            "prelims": payload["counts"]["prelims"],
            "mains": payload["counts"]["mains"],
            "articles": payload["counts"]["articles"],
            "subjects": payload["subjectCounts"],
        })

    totals = {
        "days": len(index_days),
        "prelims": sum(d["prelims"] for d in index_days),
        "mains": sum(d["mains"] for d in index_days),
        "articles": sum(d["articles"] for d in index_days),
    }
    subject_totals: Counter = Counter()
    for d in index_days:
        subject_totals.update(d["subjects"])

    (data_dir / "index.json").write_text(json.dumps({
        "title": SITE_TITLE,
        "tagline": SITE_TAGLINE,
        "generatedAt": stamp,
        "latest": index_days[0]["date"] if index_days else None,
        "days": index_days,
        "totals": totals,
        "subjectTotals": dict(subject_totals),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    (data_dir / "style.json").write_text(
        json.dumps(style_payload(), ensure_ascii=False, indent=1), encoding="utf-8")

    # Static shell. The stylesheet and script are stamped with a hash of their own
    # contents, so a CDN that caches them forever still serves the new ones the
    # moment they change — and keeps serving from cache when they have not.
    assets: dict[str, str] = {}
    for src in (WEB_DIR / "assets").glob("*"):
        if not src.is_file():
            continue
        raw = src.read_bytes()
        shutil.copyfile(src, out_dir / "assets" / src.name)
        assets[src.name] = hashlib.sha1(raw).hexdigest()[:10]

    for name in ("index.html", "404.html"):
        src = WEB_DIR / name
        if src.exists():
            (out_dir / name).write_text(_stamp_assets(src.read_text(encoding="utf-8"), assets),
                                        encoding="utf-8")
    for name in ("robots.txt", ".nojekyll"):
        src = WEB_DIR / name
        if src.exists():
            shutil.copyfile(src, out_dir / name)

    # A no-JavaScript entry point, and what the 404 page and <noscript> link to.
    if index_days:
        latest = index_days[0]["date"]
        shutil.copyfile(papers_dir / f"{latest}.html", out_dir / "latest.html")

    return {"days": len(index_days), "out": str(out_dir), **totals}


def build_from_db(out_dir: Path, days: list[str] | None = None) -> dict:
    return build(Store(), out_dir, days)


if __name__ == "__main__":  # pragma: no cover - manual use
    print(build_from_db(Path("site")))
