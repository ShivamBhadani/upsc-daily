"""Background threads so the window never blocks on network or model calls."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from pathlib import Path

from ..config import Settings
from ..generator import Generator
from ..models import Article, MainsQuestion, Question
from ..sources import Collector
from ..storage import Store
from ..webexport import build as build_site


class FetchWorker(QThread):
    """Collects today's current affairs from every configured feed."""

    progress = Signal(str, int)
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings

    def run(self) -> None:
        try:
            articles = Collector(self.settings).collect(
                lambda msg, pct: self.progress.emit(msg, pct)
            )
            self.done.emit(articles)
        except Exception as exc:                       # noqa: BLE001 - surfaced in UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class GenerateWorker(QThread):
    """Turns collected articles into a UPSC-style paper."""

    progress = Signal(str, int)
    done = Signal(list, list, str)
    failed = Signal(str)

    def __init__(self, settings: Settings, articles: list[Article]) -> None:
        super().__init__()
        self.settings = settings
        self.articles = articles

    def run(self) -> None:
        try:
            questions, mains, backend = Generator(self.settings).generate(
                self.articles, lambda msg, pct: self.progress.emit(msg, pct)
            )
            self.done.emit(questions, mains, backend)
        except Exception as exc:                       # noqa: BLE001 - surfaced in UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class PublishWorker(QThread):
    """Renders the public static site from everything stored so far."""

    progress = Signal(str, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, out_dir: Path) -> None:
        super().__init__()
        self.out_dir = out_dir

    def run(self) -> None:
        try:
            self.progress.emit(f"Building the site into {self.out_dir}", 30)
            summary = build_site(Store(), self.out_dir)
            self.done.emit(summary)
        except Exception as exc:                       # noqa: BLE001 - surfaced in UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
