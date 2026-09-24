"""Export a day's paper to Markdown or a printable HTML file."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from . import pyq
from .config import EXPORT_DIR
from .models import Article, MainsQuestion, Question

_LETTERS = "abcd"


def to_markdown(day: str, questions: list[Question], mains: list[MainsQuestion],
                articles: list[Article]) -> str:
    lines: list[str] = [f"# UPSC Daily — {day}", ""]
    lines.append(f"*{len(questions)} Prelims MCQs and {len(mains)} Mains questions "
                 f"from {len(articles)} current-affairs items.*")
    lines.append("")
    lines.append("## Prelims")
    lines.append("")
    for i, q in enumerate(questions, 1):
        lines.append(f"**Q{i}. {q.stem}**  ")
        lines.append(f"<sub>{q.subject} · {q.difficulty} · {q.qtype}</sub>")
        lines.append("")
        for j, s in enumerate(q.statements, 1):
            lines.append(f"{j}. {s}")
        if q.statements:
            lines.append("")
        tail = pyq.closing_line(q.qtype, q.stem)
        if q.pairs:
            lines.append("| | |")
            lines.append("|---|---|")
            for left, right in q.pairs:
                lines.append(f"| {left} | {right} |")
            lines.append("")
        if tail and (q.statements or q.pairs):
            lines.append(f"*{tail}*")
            lines.append("")
        for j, opt in enumerate(q.options):
            lines.append(f"({_LETTERS[j]}) {opt}")
        lines.append("")
    lines.append("## Answer key")
    lines.append("")
    for i, q in enumerate(questions, 1):
        lines.append(f"**Q{i}: ({_LETTERS[q.answer_index]})** — {q.explanation}")
        if q.pyq_link:
            lines.append(f"  *Syllabus link:* {q.pyq_link}")
        if q.source_url:
            lines.append(f"  *Source:* [{q.source_title or 'article'}]({q.source_url})")
        lines.append("")
    if mains:
        lines.append("## Mains")
        lines.append("")
        for i, m in enumerate(mains, 1):
            lines.append(f"**{i}. [{m.gs_paper} · {m.marks} marks]** {m.question}")
            for h in m.hints:
                lines.append(f"   - {h}")
            lines.append("")
    if articles:
        lines.append("## Sources covered")
        lines.append("")
        for a in articles:
            lines.append(f"- [{a.title}]({a.url}) — {a.source}")
    return "\n".join(lines)


def to_html(day: str, questions: list[Question], mains: list[MainsQuestion],
            articles: list[Article]) -> str:
    def esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))

    def href(url: str) -> str:
        """Only ordinary web links reach an href; the URLs come from model output."""
        url = (url or "").strip()
        return esc(url) if url.lower().startswith(("http://", "https://")) else ""

    body: list[str] = []
    for i, q in enumerate(questions, 1):
        body.append('<div class="q">')
        body.append(f'<div class="meta">Q{i} &middot; {esc(q.subject)} &middot; {esc(q.difficulty)}</div>')
        body.append(f"<p class='stem'>{esc(q.stem)}</p>")
        if q.statements:
            body.append("<ol class='st'>" + "".join(f"<li>{esc(s)}</li>" for s in q.statements) + "</ol>")
        if q.pairs:
            body.append("<table>" + "".join(
                f"<tr><td>{esc(l)}</td><td>{esc(r)}</td></tr>" for l, r in q.pairs) + "</table>")
        tail = pyq.closing_line(q.qtype, q.stem)
        if tail and (q.statements or q.pairs):
            body.append(f"<p class='stem'>{esc(tail)}</p>")
        body.append("<ol class='op' type='a'>" + "".join(f"<li>{esc(o)}</li>" for o in q.options) + "</ol>")
        body.append(f"<details><summary>Answer</summary><p><b>({_LETTERS[q.answer_index]})</b> "
                    f"{esc(q.explanation)}</p>"
                    + (f"<p class='link'>{esc(q.pyq_link)}</p>" if q.pyq_link else "")
                    + (f'<p><a href="{href(q.source_url)}" target="_blank" '
                       f'rel="noopener noreferrer">{esc(q.source_title or "source")}</a></p>'
                       if href(q.source_url) else "")
                    + "</details>")
        body.append("</div>")

    for i, m in enumerate(mains, 1):
        body.append(
            f"<div class='q mains'><div class='meta'>Mains {i} &middot; {esc(m.gs_paper)} "
            f"&middot; {m.marks} marks</div><p class='stem'>{esc(m.question)}</p>"
            + ("<ul>" + "".join(f"<li>{esc(h)}</li>" for h in m.hints) + "</ul>" if m.hints else "")
            + "</div>"
        )

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>UPSC Daily — {day}</title><style>
body{{font-family:Georgia,'Times New Roman',serif;max-width:820px;margin:40px auto;padding:0 24px;
color:#1c1c1e;line-height:1.6}}
h1{{font-size:28px;border-bottom:3px solid #b8860b;padding-bottom:8px}}
.q{{margin:28px 0;padding:18px 20px;border:1px solid #e2e2e2;border-radius:10px;
page-break-inside:avoid}}
.q.mains{{background:#fbf7ee}}
.meta{{font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.08em;text-transform:uppercase;
color:#8a6d1f;margin-bottom:8px}}
.stem{{font-weight:600;margin:6px 0 12px}}
ol.st li{{margin:4px 0}}
ol.op{{margin-top:12px}} ol.op li{{margin:6px 0}}
table{{border-collapse:collapse;margin:10px 0}} td{{border:1px solid #ddd;padding:6px 12px}}
details{{margin-top:12px;font-size:15px}} summary{{cursor:pointer;color:#8a6d1f;font-weight:600}}
.link{{color:#555;font-style:italic}}
a{{color:#245}}
@media print{{details[open]{{display:block}} .q{{border-color:#bbb}}}}
</style></head><body>
<h1>UPSC Daily — {day}</h1>
<p><i>{len(questions)} Prelims MCQs, {len(mains)} Mains questions, from
{len(articles)} current-affairs items.</i></p>
{''.join(body)}
</body></html>"""


def write(day: str | None, questions: list[Question], mains: list[MainsQuestion],
          articles: list[Article], fmt: str = "md", path: Path | None = None) -> Path:
    day = day or date.today().isoformat()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    target = path or EXPORT_DIR / f"upsc-daily-{day}.{fmt}"
    text = to_markdown(day, questions, mains, articles) if fmt == "md" \
        else to_html(day, questions, mains, articles)
    target.write_text(text, encoding="utf-8")
    return target
