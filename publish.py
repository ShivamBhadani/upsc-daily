"""Collect today's news, set the paper, build the public site, push it live.

Typical use, once a day:

    python publish.py                 # fetch + generate + build + commit + push
    python publish.py --no-push       # everything except the push
    python publish.py --rebuild-only  # re-render the site from what is already stored
    python publish.py --date 2026-09-24 --regenerate   # redo one day's questions

The site is plain static files, so whatever serves `docs/` — GitHub Pages,
Netlify, S3, nginx — needs no backend and no API key of its own.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from upsc_daily import webexport
from upsc_daily.config import Settings
from upsc_daily.generator import Generator, GenerationError
from upsc_daily.sources import Collector
from upsc_daily.storage import Store

# Headlines carry ₹, — and the like; a cp1252 console would otherwise kill the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - older or redirected streams
        pass

ROOT = Path(__file__).parent
DEFAULT_OUT = ROOT / "docs"   # GitHub Pages serves /docs with no extra setup


def say(msg: str) -> None:
    _out(f"[publish] {msg}")


def _out(text: str) -> None:
    """Print without ever letting the console's encoding abort the run."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", "ascii") or "ascii"
        print(text.encode(enc, "replace").decode(enc, "replace"), flush=True)


def step(message: str, pct: int) -> None:
    _out(f"          {pct:3d}%  {message[:80]}")


def collect(settings: Settings, store: Store) -> int:
    say("collecting current affairs…")
    articles = Collector(settings).collect(step)
    new = store.save_articles(articles)
    say(f"{len(articles)} items ({new} new)")
    return len(articles)


def generate(settings: Settings, store: Store, day: str) -> int:
    articles = store.articles_for(day)
    if not articles:
        say(f"no articles stored for {day}; nothing to set questions from")
        return 0
    say(f"setting questions from {len(articles)} articles…")
    try:
        questions, mains, backend = Generator(settings).generate(articles, step)
    except GenerationError as exc:
        say(f"generation failed: {exc}")
        return 0
    store.clear_day(day)
    store.save_questions(questions)
    store.save_mains(mains)
    say(f"{len(questions)} Prelims and {len(mains)} Mains questions set via {backend}")
    if backend == "offline":
        say("WARNING: no model backend was reachable — these are template drafts. "
            "Check them before publishing, or rerun once `claude` is available.")
    return len(questions)


def build(out: Path) -> dict:
    say(f"building the site into {out}…")
    summary = webexport.build(Store(), out)
    say(f"{summary['days']} papers · {summary['prelims']} Prelims questions · "
        f"{summary['mains']} Mains questions")
    return summary


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc


def push(out: Path, message: str, branch: str | None = None) -> None:
    """Commit the built site and push it to the configured remote."""
    if not (ROOT / ".git").exists():
        say("this folder is not a git repository yet — see UPSC_DAILY_HOSTING.md")
        return
    remote = git("remote", check=False)
    if not remote.stdout.strip():
        say("no git remote configured — see UPSC_DAILY_HOSTING.md")
        return

    git("add", "--all", str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out))
    staged = git("diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        say("site unchanged, nothing to push")
        return

    git("commit", "-m", message)
    current = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    target = branch or current
    say(f"pushing {target} to origin…")
    git("push", "origin", f"{current}:{target}")
    say("pushed — the live site updates in a minute or two")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="site output folder")
    ap.add_argument("--date", default=date.today().isoformat(), help="day to work on")
    ap.add_argument("--no-fetch", action="store_true", help="skip collecting news")
    ap.add_argument("--no-generate", action="store_true", help="skip setting questions")
    ap.add_argument("--regenerate", action="store_true",
                    help="set questions again even if this day already has a paper")
    ap.add_argument("--rebuild-only", action="store_true",
                    help="only re-render the site from the stored database")
    ap.add_argument("--no-push", action="store_true", help="build but do not commit or push")
    ap.add_argument("--branch", help="branch to push to (default: the current branch)")
    ap.add_argument("--backend", choices=["auto", "api", "cli", "offline"],
                    help="override the question-setting backend for this run")
    ap.add_argument("--prelims", type=int, help="number of Prelims questions (minimum 20)")
    args = ap.parse_args(argv)

    settings = Settings.load()
    if args.backend:
        settings.backend = args.backend
    if args.prelims:
        settings.prelims_count = max(args.prelims, 20)
    store = Store()
    day = args.date

    if args.rebuild_only:
        build(args.out)
        if not args.no_push:
            push(args.out, f"Rebuild site ({day})", args.branch)
        return 0

    if not args.no_fetch:
        collect(settings, store)

    existing = store.questions_for(day)
    if args.no_generate:
        say("skipping generation")
    elif existing and not args.regenerate:
        say(f"{day} already has {len(existing)} questions — pass --regenerate to redo them")
    else:
        if not generate(settings, store, day):
            say("no questions were produced; the site keeps its previous papers")

    build(args.out)
    if not args.no_push:
        n = len(store.questions_for(day))
        push(args.out, f"Paper for {day} ({n} Prelims questions)", args.branch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
