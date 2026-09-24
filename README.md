# UPSC Daily

A desktop app that collects the day's current affairs and sets a UPSC-style question
paper from them: at least 20 Prelims MCQs plus Mains answer-writing questions, framed
against a pattern model distilled from previous year papers.

Two ways to use it: a desktop app for setting and reviewing the paper, and a public
static site so other people can practise from it.

```bash
python run_upsc_daily.py     # the desktop app
python publish.py            # collect, set the paper, build the site, push it live
```

The site it builds lands in `docs/`, ready for GitHub Pages — see [HOSTING.md](HOSTING.md).

## What it does

1. **Fetch news** — pulls every configured RSS feed (PIB, The Hindu, Indian Express
   Explained, Down To Earth, Mint, Economic Times), follows each link and extracts the
   article text. Items are de-duplicated and tagged with a likely UPSC subject.
2. **Generate paper** — sets at least 20 Prelims MCQs and the configured number of
   Mains questions, spread across the PYQ format mix and subject weightage.
3. **Practise** — read the paper with click-to-answer options and explanations, or use
   **Quiz mode** for a timed run with real UPSC marking (+2 correct, −0.66 wrong).
4. **Track** — subject-wise accuracy accumulates across every attempt.
5. **Export** — Markdown, or a printable HTML paper with a collapsible answer key.

## The PYQ style model

`upsc_daily/pyq.py` holds the whole style model, and the app shows it on the
**PYQ style model** page. It encodes:

| Format | Share | Shape |
|---|---|---|
| Statement counting | 22% | "How many of the above statements are correct?" — Only one / Only two / … |
| Which statement(s) is/are correct | 20% | 1 only / 2 only / Both / Neither |
| Three-statement combination | 12% | 1 and 2 only / 2 and 3 only / … |
| Correctly matched pairs | 12% | "How many of the pairs are correctly matched?" |
| Best describes the term | 12% | Four full-sentence definitions, one precisely right |
| Statement-I / Statement-II | 8% | Truth of both, plus whether II explains I |
| Implication / application | 8% | Policy change → most likely consequence |
| Sequence / odd-one-out | 6% | Chronological or "which is not…" |

Subject weightage targets Economy 16, Polity 15, Environment 15, History/Culture 13,
Science & Tech 12, Geography 11, Social Issues 10, IR 8 (percent).

The framing rules matter as much as the shapes: the news is only the trigger and the
syllabus supplies the answer; statements stay short and independently checkable;
distractors are near-misses (the neighbouring ministry, the sister scheme, the
similar-sounding index); and there is no "None of the above". The same model is
injected into the model prompt and drives the offline fallback, so a day's paper looks
like a UPSC paper rather than a news quiz.

## Question-setting backends

Tried in this order when the backend is set to *Auto*:

| Backend | Requirement | Quality |
|---|---|---|
| `api` | `ANTHROPIC_API_KEY` in the environment | Best |
| `cli` | the `claude` command on PATH | Best — no API key needed |
| `offline` | nothing | Draft only, clearly labelled in the UI |

The offline engine mutates real article sentences into statement sets. It follows the
PYQ formats, but the wording and keys are drafts — every offline question is badged
*offline draft* and links back to its source so it can be checked.

## The public site

`publish.py` renders every stored paper into `docs/`: a single-page app plus one JSON
file per day, and a printable HTML copy of each paper. It needs no backend and no API
key on the hosting side, so it can be served free from GitHub Pages, Netlify, S3 or any
web root.

Visitors get the whole thing — the paper with click-to-answer explanations, timed quiz
mode with UPSC marking, Mains questions, the news behind every question, the archive of
past days, the PYQ style model, and their own subject-wise accuracy kept in their own
browser. Keys A–D or 1–4 mark an option during a test; light and dark themes follow the
visitor's system setting. Assets are content-hashed, so an update is never served stale
from a CDN cache.

## Layout

```
run_upsc_daily.py          launcher
upsc_daily/
  config.py                paths, feeds, user settings (JSON)
  models.py                Article, Question, MainsQuestion
  sources.py               RSS parsing, full-text extraction, subject tagging
  pyq.py                   the PYQ pattern/trend model
  generator.py             prompt building, three backends, response parsing
  storage.py               SQLite: articles, questions, attempts
  export.py                Markdown and printable HTML
  app.py                   entry point
  webexport.py             renders the public static site
  web/                     the site's shell: index.html, app.css, app.js
  ui/
    theme.py               palette and stylesheet
    widgets.py             cards, chips, stat bars
    workers.py             fetch and generate threads
    main_window.py         the eight pages
```

Data (database, settings, exports) lives in `%LOCALAPPDATA%\UPSCDaily` — outside the
repository, so only the built site is ever published.

Hosting, the daily publish command and the scheduler entry: [HOSTING.md](HOSTING.md).

## Requirements

Python 3.11+, `PySide6`, `requests`, `beautifulsoup4`. No feed library is needed — RSS
and Atom are parsed with the standard library.

```bash
pip install PySide6 requests beautifulsoup4
```
