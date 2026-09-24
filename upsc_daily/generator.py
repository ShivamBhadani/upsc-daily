"""Question generation.

Three backends, tried in this order when `backend` is "auto":

1. ``api``     — Anthropic Messages API using the key in ANTHROPIC_API_KEY.
2. ``cli``     — the local ``claude`` command line, so no API key is needed.
3. ``offline`` — a template engine that mutates article sentences into MCQs.
                 Lower quality, always available, and clearly labelled as such.

Every backend is driven by the same PYQ style model in :mod:`upsc_daily.pyq`,
so the resulting paper keeps the same shape whichever one runs.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
from collections import Counter
from datetime import date
from typing import Callable

import requests

from . import pyq
from .config import Settings
from .models import Article, MainsQuestion, Question

Progress = Callable[[str, int], None]

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

JSON_SCHEMA = """Return ONE JSON object and nothing else. No markdown fence, no commentary.

{
  "questions": [
    {
      "qtype": "one of: how_many_statements | statements_which_correct | statements_three | pairs_matched | best_describes | statement_i_ii | context_application | sequence_odd",
      "stem": "the question stem, ending with the actual interrogative line",
      "statements": ["statement 1", "statement 2", "statement 3"],
      "pairs": [["left item", "right item"], ["left item", "right item"]],
      "options": ["option a", "option b", "option c", "option d"],
      "answer_index": 0,
      "explanation": "2-4 sentences: why the key is right AND why each wrong statement/pair is wrong",
      "subject": "Polity & Governance | Economy | Environment & Ecology | Science & Technology | History, Art & Culture | Geography | International Relations | Social Issues & Schemes",
      "difficulty": "Easy | Medium | Hard",
      "pyq_link": "one line naming the static syllabus concept this tests and a similar past-year question, if any",
      "source_title": "headline of the article this came from"
    }
  ],
  "mains": [
    {
      "question": "the full answer-writing question, 1-2 sentences",
      "gs_paper": "GS-I | GS-II | GS-III | GS-IV",
      "marks": 15,
      "directive": "Examine | Critically analyse | Discuss | Evaluate | Comment | Elucidate",
      "hints": ["dimension to cover", "dimension to cover", "dimension to cover"],
      "source_title": "headline of the article this came from"
    }
  ]
}

Rules for the JSON: `statements` is [] for formats that use none; `pairs` is []
except for pairs_matched, where each entry is [left, right]. `options` always has
exactly 4 entries. `answer_index` is 0-based and must point at the genuinely
correct option."""


class GenerationError(RuntimeError):
    """Raised when no backend could produce questions."""


# --------------------------------------------------------------------------- #
# prompt construction
# --------------------------------------------------------------------------- #

def _digest(articles: list[Article], per_article_chars: int = 1600) -> str:
    out = []
    for i, a in enumerate(articles, 1):
        out.append(
            f"--- ARTICLE {i} ---\n"
            f"HEADLINE: {a.title}\n"
            f"SOURCE: {a.source} ({a.published})\n"
            f"LIKELY SUBJECT: {a.subject}\n"
            f"URL: {a.url}\n"
            f"TEXT: {a.text(per_article_chars)}\n"
        )
    return "\n".join(out)


def build_prompt(articles: list[Article], n_prelims: int, n_mains: int) -> str:
    fmt_plan = Counter(pyq.target_format_plan(n_prelims))
    subj_plan = Counter(pyq.target_subject_plan(n_prelims))
    fmt_line = ", ".join(f"{k} x{v}" for k, v in fmt_plan.items() if v)
    subj_line = ", ".join(f"{k} x{v}" for k, v in subj_plan.items() if v)

    return f"""You are a question setter for the UPSC Civil Services Examination. You have
studied the previous year papers closely and reproduce their style exactly.

{pyq.style_guide()}

==================== TODAY'S CURRENT AFFAIRS ====================
{_digest(articles)}
=================================================================

TASK
Set {n_prelims} Prelims MCQs and {n_mains} Mains answer-writing questions from the
material above.

Aim for this format mix: {fmt_line}.
Aim for this subject mix (skip a subject if today's news does not support it, and
redistribute to the subjects it does support): {subj_line}.

Non-negotiables:
- Use the news only as the trigger. The thing being tested must be a static
  syllabus concept the news exposes — the institution, the law, the ecology, the
  economics, the geography behind the headline.
- Never ask for a date, a headline detail, or who said what, unless it carries
  syllabus weight.
- Statements must be short, factual and independently checkable.
- Distractors must be near-misses: the neighbouring ministry, the sister scheme,
  the similar-sounding index, the adjacent year.
- The correct option must be genuinely correct against the article text. If the
  article does not support a fact, do not assert it.
- Vary which option letter is the key across the set.
- Spread questions across many different articles; do not mine one article for
  more than three questions.

{JSON_SCHEMA}"""


# --------------------------------------------------------------------------- #
# response parsing
# --------------------------------------------------------------------------- #

def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise GenerationError("model returned no JSON object")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise GenerationError(f"malformed JSON from model: {exc}") from exc
    raise GenerationError("unterminated JSON object from model")


def _to_questions(payload: dict, articles: list[Article], origin: str) -> tuple[list[Question], list[MainsQuestion]]:
    by_title = {a.title.lower(): a for a in articles}

    def match(title: str) -> Article | None:
        if not title:
            return None
        t = title.lower().strip()
        if t in by_title:
            return by_title[t]
        for k, v in by_title.items():
            if t[:40] and t[:40] in k:
                return v
        return None

    today = date.today().isoformat()
    questions: list[Question] = []
    for raw in payload.get("questions", []):
        opts = [str(o) for o in raw.get("options", [])]
        if len(opts) != 4:
            continue
        try:
            idx = int(raw.get("answer_index", 0))
        except (TypeError, ValueError):
            continue
        if not 0 <= idx <= 3:
            continue
        art = match(str(raw.get("source_title", "")))
        questions.append(Question(
            stem=str(raw.get("stem", "")).strip(),
            statements=[str(s) for s in raw.get("statements", []) or []],
            pairs=[[str(p[0]), str(p[1])] for p in raw.get("pairs", []) or [] if len(p) >= 2],
            options=opts,
            answer_index=idx,
            explanation=str(raw.get("explanation", "")).strip(),
            qtype=str(raw.get("qtype", "statements_which_correct")),
            subject=str(raw.get("subject", "Mixed")),
            difficulty=str(raw.get("difficulty", "Medium")),
            source_url=art.url if art else "",
            source_title=art.title if art else str(raw.get("source_title", "")),
            pyq_link=str(raw.get("pyq_link", "")),
            origin=origin,
            for_date=today,
        ))

    mains: list[MainsQuestion] = []
    for raw in payload.get("mains", []):
        art = match(str(raw.get("source_title", "")))
        try:
            marks = int(raw.get("marks", 15))
        except (TypeError, ValueError):
            marks = 15
        mains.append(MainsQuestion(
            question=str(raw.get("question", "")).strip(),
            gs_paper=str(raw.get("gs_paper", "GS-II")),
            marks=marks,
            directive=str(raw.get("directive", "Discuss")),
            hints=[str(h) for h in raw.get("hints", []) or []],
            source_url=art.url if art else "",
            source_title=art.title if art else str(raw.get("source_title", "")),
            for_date=today,
        ))
    return [q for q in questions if q.stem], [m for m in mains if m.question]


# --------------------------------------------------------------------------- #
# backends
# --------------------------------------------------------------------------- #

def api_available(settings: Settings) -> bool:
    return bool(settings.api_key())


def cli_available() -> bool:
    return shutil.which("claude") is not None


def call_api(prompt: str, settings: Settings) -> str:
    key = settings.api_key()
    if not key:
        raise GenerationError(f"{settings.api_key_env} is not set")
    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": settings.model,
            "max_tokens": 16000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=600,
    )
    if resp.status_code != 200:
        raise GenerationError(f"API {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def call_cli(prompt: str, settings: Settings) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise GenerationError("claude CLI not found on PATH")
    env = dict(os.environ)
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    try:
        proc = subprocess.run(
            [exe, "-p", "--output-format", "text", "--model", settings.model],
            input=prompt, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=900, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise GenerationError("claude CLI timed out") from exc
    if proc.returncode != 0:
        # The CLI reports some failures (expired OAuth, for one) on stdout, so read both.
        detail = ((proc.stderr or "") + " " + (proc.stdout or "")).strip()[:300] or "no output"
        if "authenticate" in detail.lower() or "oauth" in detail.lower():
            raise GenerationError(
                "claude CLI is signed out — run `claude` once in a terminal to sign in "
                f"again, then retry. ({detail})")
        raise GenerationError(f"claude CLI failed: {detail}")
    if not proc.stdout.strip():
        raise GenerationError("claude CLI returned nothing")
    return proc.stdout


# --------------------------------------------------------------------------- #
# offline template backend
# --------------------------------------------------------------------------- #

_STOP = {
    "The", "This", "That", "These", "Those", "India", "It", "He", "She", "They",
    "In", "On", "At", "But", "And", "For", "With", "While", "However", "According",
    "Mr", "Ms", "Dr", "New", "A", "An",
}
_ORG_RE = re.compile(r"\b(?:Ministry of [A-Z][a-z]+(?: [A-Z][a-z]+)*|[A-Z]{3,6})\b")
_NUM_RE = re.compile(r"\b\d[\d,.]*\b")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if 60 <= len(p.strip()) <= 260]


def _key_term(article: Article) -> str:
    """Pick the most question-worthy proper noun phrase from the headline."""
    words = re.findall(r"\b[A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+){0,3}\b", article.title)
    cands = [w for w in words if w.split()[0] not in _STOP and len(w) >= 3]
    if cands:
        return max(cands, key=len)
    return article.title.split(",")[0][:60]


def _falsify(sentence: str, pool: list[str], rng: random.Random) -> str:
    """Turn a true sentence into a near-miss false one."""
    nums = _NUM_RE.findall(sentence)
    if nums and rng.random() < 0.5:
        target = rng.choice(nums)
        try:
            base = float(target.replace(",", ""))
            shifted = base * rng.choice([1.5, 2.0, 0.5, 0.25])
            new = f"{shifted:,.0f}" if base >= 10 else f"{shifted:.1f}"
        except ValueError:
            new = target
        return sentence.replace(target, new, 1)

    orgs = _ORG_RE.findall(sentence)
    others = [o for o in pool if o not in orgs]
    if orgs and others:
        return sentence.replace(rng.choice(orgs), rng.choice(others), 1)

    for verb, neg in ((" is ", " is not "), (" was ", " was not "),
                      (" has ", " has not "), (" will ", " will not "),
                      (" are ", " are not ")):
        if verb in sentence:
            return sentence.replace(verb, neg, 1)
    return "It is " + sentence[0].lower() + sentence[1:] if sentence else sentence


def generate_offline(articles: list[Article], n_prelims: int, n_mains: int,
                     progress: Progress | None = None) -> tuple[list[Question], list[MainsQuestion]]:
    """Build questions by mutating article sentences. Draft quality by design."""
    rng = random.Random(date.today().toordinal())
    today = date.today().isoformat()

    usable = [a for a in articles if len(a.text()) > 300]
    rng.shuffle(usable)
    if not usable:
        raise GenerationError("no article had enough text to build questions from")

    org_pool = sorted({o for a in usable for o in _ORG_RE.findall(a.text())})
    if len(org_pool) < 4:
        org_pool += ["NITI Aayog", "Ministry of Finance", "RBI", "Ministry of Home Affairs"]

    fmt_plan = pyq.target_format_plan(n_prelims)
    rng.shuffle(fmt_plan)

    questions: list[Question] = []
    i = 0
    attempts = 0
    budget = n_prelims * 8 + 60
    while len(questions) < n_prelims and attempts < budget:
        art = usable[i % len(usable)]
        i += 1
        attempts += 1
        sents = _sentences(art.text())
        if len(sents) < 2:
            continue
        term = _key_term(art)
        fmt = fmt_plan[len(questions) % len(fmt_plan)]
        q = None

        if fmt == "best_describes":
            correct = sents[0]
            pool = [s for a in usable if a is not art for s in _sentences(a.text())[:1]]
            if len(pool) < 3:
                continue
            distractors = rng.sample(pool, 3)
            opts = distractors + [correct]
            rng.shuffle(opts)
            q = Question(
                stem=f"With reference to '{term}', which one of the following statements is correct?",
                options=[o[:220] for o in opts],
                answer_index=opts.index(correct),
                explanation=f"Drawn from the report: {correct}",
                qtype="best_describes", subject=art.subject,
            )

        elif fmt in ("how_many_statements", "statements_three"):
            picks = sents[:4] if len(sents) >= 4 else sents[:3]
            n_true = rng.randint(1, len(picks))
            flags = [True] * n_true + [False] * (len(picks) - n_true)
            rng.shuffle(flags)
            stmts = [s if keep else _falsify(s, org_pool, rng) for s, keep in zip(picks, flags)]
            opts = ["Only one", "Only two", "Only three", "All four"][:len(picks)]
            while len(opts) < 4:
                opts.append("None")
            q = Question(
                stem=f"With reference to '{term}', consider the following statements. "
                     f"How many of the above statements are correct?",
                statements=[s[:220] for s in stmts],
                options=opts,
                answer_index=min(n_true - 1, 3),
                explanation="Statements marked false were altered from the source report "
                            "(a figure, an institution or a negation was changed).",
                qtype="how_many_statements", subject=art.subject,
            )

        else:  # statements_which_correct
            s1, s2 = sents[0], sents[1]
            keep1, keep2 = rng.choice([(True, True), (True, False), (False, True), (False, False)])
            st = [s1 if keep1 else _falsify(s1, org_pool, rng),
                  s2 if keep2 else _falsify(s2, org_pool, rng)]
            key = {(True, True): 2, (True, False): 0, (False, True): 1, (False, False): 3}[(keep1, keep2)]
            q = Question(
                stem=f"With reference to '{term}', consider the following statements. "
                     f"Which of the statements given above is/are correct?",
                statements=[s[:220] for s in st],
                options=["1 only", "2 only", "Both 1 and 2", "Neither 1 nor 2"],
                answer_index=key,
                explanation="Statements marked false were altered from the source report "
                            "(a figure, an institution or a negation was changed).",
                qtype="statements_which_correct", subject=art.subject,
            )

        if q:
            q.source_url, q.source_title = art.url, art.title
            q.origin = "offline"
            q.for_date = today
            q.pyq_link = ("Offline draft — verify against the source before treating "
                          "the key as authoritative.")
            questions.append(q)
            if progress:
                progress(f"Drafted {len(questions)}/{n_prelims}", int(len(questions) / n_prelims * 100))

    mains: list[MainsQuestion] = []
    for art in usable[:n_mains]:
        directive = rng.choice(pyq.MAINS_DIRECTIVES)
        paper = {"Economy": "GS-III", "Environment & Ecology": "GS-III",
                 "Science & Technology": "GS-III", "Polity & Governance": "GS-II",
                 "International Relations": "GS-II", "Social Issues & Schemes": "GS-II",
                 "Geography": "GS-I", "History, Art & Culture": "GS-I"}.get(art.subject, "GS-II")
        mains.append(MainsQuestion(
            question=f"{directive} the significance and challenges of the issue raised by "
                     f"'{_key_term(art)}' for India. (250 words)",
            gs_paper=paper, marks=15, directive=directive,
            hints=["Context from the news", "Constitutional / policy framework",
                   "Challenges", "Way forward"],
            source_url=art.url, source_title=art.title, for_date=today,
        ))
    return questions, mains


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #

class Generator:
    """Picks a backend and turns today's articles into a question paper."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available_backends(self) -> list[str]:
        out = []
        if api_available(self.settings):
            out.append("api")
        if cli_available():
            out.append("cli")
        out.append("offline")
        return out

    def _order(self) -> list[str]:
        want = self.settings.backend
        if want != "auto":
            return [want]
        return self.available_backends()

    def generate(self, articles: list[Article], progress: Progress | None = None
                 ) -> tuple[list[Question], list[MainsQuestion], str]:
        n_p = max(self.settings.prelims_count, 20)
        n_m = self.settings.mains_count
        errors: list[str] = []

        for backend in self._order():
            try:
                if backend == "offline":
                    if progress:
                        progress("Building questions offline from article text", 10)
                    qs, ms = generate_offline(articles, n_p, n_m, progress)
                    return qs, ms, "offline"

                caller = call_api if backend == "api" else call_cli
                label = "Anthropic API" if backend == "api" else "claude CLI"
                batches = self._batches(articles, n_p, n_m)
                all_q: list[Question] = []
                all_m: list[MainsQuestion] = []
                for bi, (chunk, want_p, want_m) in enumerate(batches, 1):
                    if progress:
                        progress(
                            f"{label}: setting batch {bi}/{len(batches)} "
                            f"({want_p} MCQs from {len(chunk)} articles)",
                            int((bi - 1) / len(batches) * 95) + 5,
                        )
                    text = caller(build_prompt(chunk, want_p, want_m), self.settings)
                    qs, ms = _to_questions(_extract_json(text), chunk, backend)
                    all_q.extend(qs)
                    all_m.extend(ms)
                if len(all_q) < 5:
                    raise GenerationError(f"{label} returned only {len(all_q)} usable questions")
                if progress:
                    progress(f"{label}: {len(all_q)} questions ready", 100)
                return all_q[:max(n_p, len(all_q))], all_m, backend
            except (GenerationError, requests.RequestException) as exc:
                errors.append(f"{backend}: {exc}")
                if progress:
                    progress(f"{backend} unavailable ({exc}); trying next backend", 5)

        raise GenerationError(" | ".join(errors) or "no backend available")

    @staticmethod
    def _batches(articles: list[Article], n_prelims: int, n_mains: int
                 ) -> list[tuple[list[Article], int, int]]:
        """Split the work so each model call sees a digestible slice of the news."""
        pool = [a for a in articles if len(a.text()) > 200] or articles
        pool = pool[:40]
        per_batch_q = 7
        n_batches = max(1, -(-n_prelims // per_batch_q))
        size = max(4, -(-len(pool) // n_batches))
        out: list[tuple[list[Article], int, int]] = []
        left_q, left_m = n_prelims, n_mains
        for i in range(n_batches):
            chunk = pool[i * size:(i + 1) * size]
            if not chunk:
                break
            want_q = min(per_batch_q, left_q) if i < n_batches - 1 else left_q
            want_m = -(-left_m // (n_batches - i)) if n_batches - i else left_m
            out.append((chunk, max(want_q, 1), max(want_m, 0)))
            left_q -= want_q
            left_m -= want_m
        return out
