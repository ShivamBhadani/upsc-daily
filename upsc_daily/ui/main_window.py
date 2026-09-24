"""The main application window."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import export, pyq
from ..config import EXPORT_DIR, Settings
from ..generator import Generator
from ..models import Article, MainsQuestion, Question
from ..storage import Store
from . import theme
from .widgets import ArticleCard, Card, MainsCard, QuestionCard, StatBar, chip, muted
from .workers import FetchWorker, GenerateWorker, PublishWorker

PAGES = [
    ("Today", "◉"),
    ("Current affairs", "▤"),
    ("Prelims paper", "☷"),
    ("Quiz mode", "⏱"),
    ("Mains", "✎"),
    ("PYQ style model", "⚖"),
    ("Progress", "◴"),
    ("Sources", "⚙"),
]


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def scroll_page() -> tuple[QScrollArea, QVBoxLayout]:
    area = QScrollArea()
    area.setWidgetResizable(True)
    # Word-wrapped labels otherwise widen the viewport instead of wrapping.
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(26, 22, 26, 26)
    lay.setSpacing(14)
    area.setWidget(inner)
    return area, lay


class StatTile(Card):
    def __init__(self, value: str, label: str, color: str) -> None:
        super().__init__()
        self.box.setSpacing(2)
        self.value = QLabel(value)
        self.value.setStyleSheet(f"font-size:30px;font-weight:800;color:{color};")
        self.box.addWidget(self.value)
        self.box.addWidget(muted(label))
        self.setMinimumWidth(150)

    def set_value(self, v: str) -> None:
        self.value.setText(v)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self.store = Store()
        self.day = date.today().isoformat()
        self.articles: list[Article] = self.store.articles_for(self.day)
        self.questions: list[Question] = self.store.questions_for(self.day)
        self.mains: list[MainsQuestion] = self.store.mains_for(self.day)
        self.fetcher: FetchWorker | None = None
        self.generator: GenerateWorker | None = None
        self.publisher: PublishWorker | None = None
        self.site_dir = Path(__file__).resolve().parents[2] / "docs"

        self.setWindowTitle("UPSC Daily — current affairs to Prelims-style questions")
        self.resize(1280, 880)
        self.setStyleSheet(theme.STYLESHEET)
        self._build()
        self._refresh_all()

    # ----------------------------------------------------------------- layout
    def _build(self) -> None:
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._sidebar())

        right = QWidget()
        col = QVBoxLayout(right)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._header())
        self.stack = QStackedWidget()
        col.addWidget(self.stack, 1)
        row.addWidget(right, 1)

        self.page_today = self._page_today()
        self.page_news, self.news_lay = self._page_news()
        self.page_prelims, self.prelims_lay = self._page_prelims()
        self.page_quiz = self._page_quiz()
        self.page_mains, self.mains_lay = scroll_page()
        self.page_style = self._page_style()
        self.page_progress, self.progress_lay = scroll_page()
        self.page_sources = self._page_sources()

        for w in (self.page_today, self.page_news, self.page_prelims, self.page_quiz,
                  self.page_mains, self.page_style, self.page_progress, self.page_sources):
            self.stack.addWidget(w)

        self.setCentralWidget(root)
        self._goto(0)

    def _sidebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(232)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        brand = QLabel("UPSC Daily")
        brand.setObjectName("Brand")
        sub = QLabel("current affairs engine")
        sub.setObjectName("BrandSub")
        lay.addWidget(brand)
        lay.addWidget(sub)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, (name, glyph) in enumerate(PAGES):
            btn = QPushButton(f"  {glyph}   {name}")
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self.nav_group.addButton(btn, i)
            lay.addWidget(btn)
        self.nav_group.idClicked.connect(self._goto)

        lay.addStretch(1)
        self.backend_label = QLabel()
        self.backend_label.setObjectName("SidebarFoot")
        self.backend_label.setWordWrap(True)
        lay.addWidget(self.backend_label)
        return bar

    def _header(self) -> QWidget:
        head = QWidget()
        head.setObjectName("Header")
        head.setFixedHeight(84)
        lay = QHBoxLayout(head)
        lay.setContentsMargins(26, 14, 26, 14)
        lay.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.page_title = QLabel("Today")
        self.page_title.setObjectName("PageTitle")
        self.page_sub = QLabel()
        self.page_sub.setObjectName("PageSub")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_sub)
        lay.addLayout(titles)
        lay.addStretch(1)

        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status.setMinimumWidth(280)
        lay.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setFixedWidth(150)
        self.bar.setTextVisible(False)
        self.bar.setVisible(False)
        lay.addWidget(self.bar)

        self.btn_fetch = QPushButton("Fetch news")
        self.btn_fetch.setObjectName("Ghost")
        self.btn_fetch.clicked.connect(self.fetch_news)
        lay.addWidget(self.btn_fetch)

        self.btn_gen = QPushButton("Generate paper")
        self.btn_gen.setObjectName("Primary")
        self.btn_gen.clicked.connect(self.generate_paper)
        lay.addWidget(self.btn_gen)

        self.btn_publish = QPushButton("Publish site")
        self.btn_publish.setObjectName("Ghost")
        self.btn_publish.setToolTip("Rebuild the public website from every paper stored here")
        self.btn_publish.clicked.connect(self.publish_site)
        lay.addWidget(self.btn_publish)
        return head

    # ---------------------------------------------------------------- publish
    def publish_site(self) -> None:
        if self.publisher and self.publisher.isRunning():
            return
        self._busy(True, "Building the public site…")
        self.publisher = PublishWorker(self.site_dir)
        self.publisher.progress.connect(self._on_progress)
        self.publisher.done.connect(self._on_published)
        self.publisher.failed.connect(self._on_failed)
        self.publisher.start()

    def _on_published(self, summary: dict) -> None:
        self._busy(False, f"Site built: {summary['days']} papers in {summary['out']}")
        box = QMessageBox(self)
        box.setWindowTitle("Site built")
        box.setText(f"{summary['days']} papers, {summary['prelims']} Prelims questions and "
                    f"{summary['mains']} Mains questions were written to:\n{summary['out']}")
        box.setInformativeText("Commit and push that folder to publish it. "
                               "See UPSC_DAILY_HOSTING.md for the one-time setup.")
        open_btn = box.addButton("Open folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.site_dir)))

    # ------------------------------------------------------------- today page
    def _page_today(self) -> QWidget:
        page, lay = scroll_page()

        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.tile_articles = StatTile("0", "articles collected today", theme.BLUE)
        self.tile_questions = StatTile("0", "Prelims MCQs ready", theme.ACCENT)
        self.tile_mains = StatTile("0", "Mains questions", theme.GREEN)
        self.tile_attempts = StatTile("0", "questions attempted (all time)", theme.MUTED)
        for t in (self.tile_articles, self.tile_questions, self.tile_mains, self.tile_attempts):
            tiles.addWidget(t)
        lay.addLayout(tiles)

        flow = Card()
        step_title = QLabel("Daily routine")
        step_title.setObjectName("CardTitle")
        flow.box.addWidget(step_title)
        for n, text in enumerate([
            "Fetch news — pulls every configured feed, follows each link and extracts "
            "the article text.",
            "Generate paper — sets at least 20 Prelims MCQs plus Mains questions in the "
            "PYQ format mix and subject weightage.",
            "Prelims paper — read and self-check, or switch to Quiz mode for a timed "
            "run with UPSC negative marking.",
            "Progress — subject-wise accuracy across every attempt, so weak areas surface.",
        ], 1):
            row = QLabel(f"<b style='color:{theme.ACCENT}'>{n}.</b> {text}")
            row.setWordWrap(True)
            flow.box.addWidget(row)
        lay.addWidget(flow)

        self.today_summary = Card()
        lay.addWidget(self.today_summary)

        history = Card()
        h_title = QLabel("Past papers")
        h_title.setObjectName("CardTitle")
        history.box.addWidget(h_title)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(190)
        self.history_list.itemDoubleClicked.connect(self._load_history_day)
        history.box.addWidget(self.history_list)
        history.box.addWidget(muted("Double-click a date to load that day's paper."))
        lay.addWidget(history)

        lay.addStretch(1)
        return page

    # -------------------------------------------------------------- news page
    def _page_news(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        filters = QWidget()
        frow = QHBoxLayout(filters)
        frow.setContentsMargins(26, 14, 26, 6)
        self.news_search = QLineEdit()
        self.news_search.setPlaceholderText("Search headlines and text…")
        self.news_search.textChanged.connect(self._render_news)
        frow.addWidget(self.news_search, 1)
        self.news_subject = QComboBox()
        self.news_subject.addItem("All subjects")
        self.news_subject.addItems(sorted(pyq.SUBJECT_WEIGHTS))
        self.news_subject.currentIndexChanged.connect(self._render_news)
        frow.addWidget(self.news_subject)
        outer.addWidget(filters)

        area, lay = scroll_page()
        outer.addWidget(area, 1)
        return page, lay

    # ----------------------------------------------------------- prelims page
    def _page_prelims(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        tools = QWidget()
        trow = QHBoxLayout(tools)
        trow.setContentsMargins(26, 14, 26, 6)
        trow.setSpacing(10)

        self.prelims_subject = QComboBox()
        self.prelims_subject.addItem("All subjects")
        self.prelims_subject.addItems(sorted(pyq.SUBJECT_WEIGHTS))
        self.prelims_subject.currentIndexChanged.connect(self._render_prelims)
        trow.addWidget(self.prelims_subject)

        self.prelims_format = QComboBox()
        self.prelims_format.addItem("All formats")
        for f in pyq.FORMATS:
            self.prelims_format.addItem(f.name, f.key)
        self.prelims_format.currentIndexChanged.connect(self._render_prelims)
        trow.addWidget(self.prelims_format)
        trow.addStretch(1)

        btn_reveal = QPushButton("Reveal all answers")
        btn_reveal.setObjectName("Ghost")
        btn_reveal.clicked.connect(self._reveal_all)
        trow.addWidget(btn_reveal)

        btn_md = QPushButton("Export Markdown")
        btn_md.setObjectName("Ghost")
        btn_md.clicked.connect(lambda: self._export("md"))
        trow.addWidget(btn_md)

        btn_html = QPushButton("Export printable HTML")
        btn_html.setObjectName("Ghost")
        btn_html.clicked.connect(lambda: self._export("html"))
        trow.addWidget(btn_html)
        outer.addWidget(tools)

        area, lay = scroll_page()
        outer.addWidget(area, 1)
        return page, lay

    # -------------------------------------------------------------- quiz page
    def _page_quiz(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 22, 26, 26)
        lay.setSpacing(14)

        head = QHBoxLayout()
        self.quiz_counter = QLabel("Quiz")
        self.quiz_counter.setObjectName("PageTitle")
        head.addWidget(self.quiz_counter)
        head.addStretch(1)
        self.quiz_score = QLabel()
        self.quiz_score.setStyleSheet(f"color:{theme.ACCENT};font-weight:700;")
        head.addWidget(self.quiz_score)
        self.quiz_clock = QLabel("00:00")
        self.quiz_clock.setStyleSheet(f"color:{theme.MUTED};font-variant-numeric:tabular-nums;")
        head.addWidget(self.quiz_clock)
        lay.addLayout(head)

        self.quiz_bar = QProgressBar()
        self.quiz_bar.setTextVisible(False)
        lay.addWidget(self.quiz_bar)

        self.quiz_holder = QVBoxLayout()
        lay.addLayout(self.quiz_holder)
        lay.addStretch(1)

        foot = QHBoxLayout()
        self.btn_quiz_start = QPushButton("Start test")
        self.btn_quiz_start.setObjectName("Primary")
        self.btn_quiz_start.clicked.connect(self._quiz_start)
        foot.addWidget(self.btn_quiz_start)
        self.btn_quiz_skip = QPushButton("Skip")
        self.btn_quiz_skip.setObjectName("Ghost")
        self.btn_quiz_skip.clicked.connect(lambda: self._quiz_next(None))
        foot.addWidget(self.btn_quiz_skip)
        foot.addStretch(1)
        self.btn_quiz_next = QPushButton("Next question")
        self.btn_quiz_next.clicked.connect(lambda: self._quiz_next(None))
        foot.addWidget(self.btn_quiz_next)
        lay.addLayout(foot)

        self.quiz_index = 0
        self.quiz_items: list[Question] = []
        self.quiz_right = 0
        self.quiz_wrong = 0
        self.quiz_timer = QTimer(self)
        self.quiz_timer.timeout.connect(self._tick)
        self.quiz_started: datetime | None = None
        self._quiz_set_running(False)
        return page

    # ------------------------------------------------------------- style page
    def _page_style(self) -> QWidget:
        page, lay = scroll_page()

        intro = Card()
        t = QLabel("How this app models UPSC style")
        t.setObjectName("CardTitle")
        intro.box.addWidget(t)
        body = QLabel(
            "Every question is set against the pattern model below, which is distilled "
            "from previous year Prelims papers: the recurring question shapes and their "
            "share of a paper, the subject weightage, and the framing rules the "
            "Commission follows. The same model drives the prompt sent to the language "
            "model and the offline template fallback, so a day's paper always looks like "
            "a UPSC paper rather than a news quiz."
        )
        body.setWordWrap(True)
        intro.box.addWidget(body)
        lay.addWidget(intro)

        for f in pyq.FORMATS:
            card = Card()
            row = QHBoxLayout()
            name = QLabel(f.name)
            name.setObjectName("CardTitle")
            row.addWidget(name)
            row.addWidget(chip(f"{f.share}% of paper", theme.ACCENT))
            row.addStretch(1)
            card.box.addLayout(row)
            how = QLabel(f.blueprint)
            how.setWordWrap(True)
            card.box.addWidget(how)
            ex = QLabel(f"<i>{f.exemplar}</i>")
            ex.setObjectName("Muted")
            ex.setWordWrap(True)
            card.box.addWidget(ex)
            if f.options:
                opts = QLabel(" &nbsp;|&nbsp; ".join(f.options))
                opts.setObjectName("Muted")
                opts.setWordWrap(True)
                card.box.addWidget(opts)
            lay.addWidget(card)

        weights = Card()
        wt = QLabel("Subject weightage targeted per paper")
        wt.setObjectName("CardTitle")
        weights.box.addWidget(wt)
        for s, w in pyq.SUBJECT_WEIGHTS.items():
            weights.box.addWidget(StatBar(s, w, 100, theme.subject_color(s),
                                          caption=f"{w}% of the paper"))
        lay.addWidget(weights)

        trends = Card()
        tt = QLabel("Trends the setter follows")
        tt.setObjectName("CardTitle")
        trends.box.addWidget(tt)
        for i, t_ in enumerate(pyq.TRENDS, 1):
            row = QLabel(f"<b style='color:{theme.ACCENT}'>{i}.</b> {t_}")
            row.setWordWrap(True)
            trends.box.addWidget(row)
        lay.addWidget(trends)

        lay.addStretch(1)
        return page

    # ----------------------------------------------------------- sources page
    def _page_sources(self) -> QWidget:
        page, lay = scroll_page()

        feeds = Card()
        ft = QLabel("Feeds collected every morning")
        ft.setObjectName("CardTitle")
        feeds.box.addWidget(ft)
        self.feed_list = QListWidget()
        self.feed_list.setMinimumHeight(240)
        feeds.box.addWidget(self.feed_list)

        add = QHBoxLayout()
        self.feed_name = QLineEdit()
        self.feed_name.setPlaceholderText("Feed name")
        self.feed_url = QLineEdit()
        self.feed_url.setPlaceholderText("https://…/feed.xml")
        self.feed_subject = QComboBox()
        self.feed_subject.addItem("Mixed")
        self.feed_subject.addItems(sorted(pyq.SUBJECT_WEIGHTS))
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._add_feed)
        btn_del = QPushButton("Remove selected")
        btn_del.setObjectName("Ghost")
        btn_del.clicked.connect(self._remove_feed)
        add.addWidget(self.feed_name, 2)
        add.addWidget(self.feed_url, 4)
        add.addWidget(self.feed_subject, 2)
        add.addWidget(btn_add)
        add.addWidget(btn_del)
        feeds.box.addLayout(add)
        lay.addWidget(feeds)

        prefs = Card()
        pt = QLabel("Generation settings")
        pt.setObjectName("CardTitle")
        prefs.box.addWidget(pt)

        grid = QHBoxLayout()
        grid.setSpacing(18)

        c1 = QVBoxLayout()
        c1.addWidget(muted("Prelims MCQs per day (minimum 20)"))
        self.spin_prelims = QSpinBox()
        self.spin_prelims.setRange(20, 60)
        self.spin_prelims.setValue(max(self.settings.prelims_count, 20))
        c1.addWidget(self.spin_prelims)
        c1.addWidget(muted("Mains questions per day"))
        self.spin_mains = QSpinBox()
        self.spin_mains.setRange(0, 15)
        self.spin_mains.setValue(self.settings.mains_count)
        c1.addWidget(self.spin_mains)
        c1.addWidget(muted("Articles pulled per feed"))
        self.spin_per_feed = QSpinBox()
        self.spin_per_feed.setRange(3, 40)
        self.spin_per_feed.setValue(self.settings.articles_per_feed)
        c1.addWidget(self.spin_per_feed)
        grid.addLayout(c1)

        c2 = QVBoxLayout()
        c2.addWidget(muted("Question-setting backend"))
        self.combo_backend = QComboBox()
        self.combo_backend.addItem("Auto — API, then claude CLI, then offline", "auto")
        self.combo_backend.addItem("Anthropic API (needs ANTHROPIC_API_KEY)", "api")
        self.combo_backend.addItem("Local claude CLI", "cli")
        self.combo_backend.addItem("Offline templates only", "offline")
        idx = self.combo_backend.findData(self.settings.backend)
        self.combo_backend.setCurrentIndex(max(idx, 0))
        c2.addWidget(self.combo_backend)
        c2.addWidget(muted("Model"))
        self.edit_model = QLineEdit(self.settings.model)
        c2.addWidget(self.edit_model)
        c2.addWidget(muted("Detected backends"))
        self.detected = QLabel()
        self.detected.setObjectName("Muted")
        self.detected.setWordWrap(True)
        c2.addWidget(self.detected)
        c2.addStretch(1)
        grid.addLayout(c2)
        prefs.box.addLayout(grid)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        btn_open = QPushButton("Open data folder")
        btn_open.setObjectName("Ghost")
        btn_open.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(EXPORT_DIR.parent)))
        )
        save_row.addWidget(btn_open)
        btn_save = QPushButton("Save settings")
        btn_save.setObjectName("Primary")
        btn_save.clicked.connect(self._save_settings)
        save_row.addWidget(btn_save)
        prefs.box.addLayout(save_row)
        lay.addWidget(prefs)
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------- navigation
    def _goto(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        btn = self.nav_group.button(index)
        if btn:
            btn.setChecked(True)
        name = PAGES[index][0]
        self.page_title.setText(name)
        subs = {
            0: f"{self.day} · everything for today at a glance",
            1: f"{len(self.articles)} items collected for {self.day}",
            2: f"{len(self.questions)} questions set in UPSC Prelims format",
            3: "Timed practice with UPSC marking: +2 for correct, −0.66 for wrong",
            4: f"{len(self.mains)} answer-writing questions",
            5: "The PYQ pattern model every question is set against",
            6: "Subject-wise accuracy across every attempt",
            7: "Feeds, counts and the question-setting backend",
        }
        self.page_sub.setText(subs.get(index, ""))

    # ------------------------------------------------------------------ fetch
    def fetch_news(self) -> None:
        if self.fetcher and self.fetcher.isRunning():
            return
        self._busy(True, "Collecting current affairs…")
        self.fetcher = FetchWorker(self.settings)
        self.fetcher.progress.connect(self._on_progress)
        self.fetcher.done.connect(self._on_fetched)
        self.fetcher.failed.connect(self._on_failed)
        self.fetcher.start()

    def _on_fetched(self, articles: list) -> None:
        new = self.store.save_articles(articles)
        self.day = date.today().isoformat()
        self.articles = self.store.articles_for(self.day)
        self._busy(False, f"Collected {len(articles)} items ({new} new) from "
                          f"{len(self.settings.feeds)} feeds")
        self._refresh_all()
        self._goto(1)

    # --------------------------------------------------------------- generate
    def generate_paper(self) -> None:
        if self.generator and self.generator.isRunning():
            return
        if not self.articles:
            QMessageBox.information(
                self, "No articles yet",
                "Fetch today's current affairs first, then generate the paper.")
            return
        self.settings.prelims_count = self.spin_prelims.value()
        self.settings.mains_count = self.spin_mains.value()
        self.settings.backend = self.combo_backend.currentData()
        self.settings.model = self.edit_model.text().strip() or self.settings.model
        self.settings.save()

        self._busy(True, "Setting questions…")
        self.generator = GenerateWorker(self.settings, self.articles)
        self.generator.progress.connect(self._on_progress)
        self.generator.done.connect(self._on_generated)
        self.generator.failed.connect(self._on_failed)
        self.generator.start()

    def _on_generated(self, questions: list, mains: list, backend: str) -> None:
        self.store.clear_day(self.day)
        self.store.save_questions(questions)
        self.store.save_mains(mains)
        self.questions = self.store.questions_for(self.day)
        self.mains = self.store.mains_for(self.day)
        label = {"api": "Anthropic API", "cli": "claude CLI",
                 "offline": "offline templates"}.get(backend, backend)
        self._busy(False, f"{len(self.questions)} Prelims and {len(self.mains)} Mains "
                          f"questions set via {label}")
        if backend == "offline":
            QMessageBox.information(
                self, "Offline drafts",
                "No model backend was reachable, so the questions were built by the "
                "offline template engine. They follow the PYQ formats but the wording "
                "and answer keys are drafts — verify each one against the linked source "
                "before trusting it.\n\nSet ANTHROPIC_API_KEY, or make the `claude` CLI "
                "available on PATH, for properly set questions.")
        self._refresh_all()
        self._goto(2)

    # ---------------------------------------------------------------- helpers
    def _busy(self, on: bool, message: str = "") -> None:
        self.btn_fetch.setEnabled(not on)
        self.btn_gen.setEnabled(not on)
        self.btn_publish.setEnabled(not on)
        self.bar.setVisible(on)
        if on:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
        self.status.setText(message)

    def _on_progress(self, message: str, pct: int) -> None:
        self.status.setText(message)
        self.bar.setValue(max(0, min(pct, 100)))

    def _on_failed(self, message: str) -> None:
        self._busy(False, "Failed")
        QMessageBox.warning(self, "Something went wrong", message)

    def _refresh_all(self) -> None:
        arts, qs, att = self.store.totals()
        self.tile_articles.set_value(str(len(self.articles)))
        self.tile_questions.set_value(str(len(self.questions)))
        self.tile_mains.set_value(str(len(self.mains)))
        self.tile_attempts.set_value(str(att))

        clear_layout(self.today_summary.box)
        t = QLabel(f"Paper for {self.day}")
        t.setObjectName("CardTitle")
        self.today_summary.box.addWidget(t)
        if self.questions:
            by_subject: dict[str, int] = {}
            for q in self.questions:
                by_subject[q.subject] = by_subject.get(q.subject, 0) + 1
            total = len(self.questions)
            for s, n in sorted(by_subject.items(), key=lambda kv: -kv[1]):
                self.today_summary.box.addWidget(
                    StatBar(s, n, total, theme.subject_color(s)))
            origins = {q.origin for q in self.questions}
            self.today_summary.box.addWidget(
                muted("Set by: " + ", ".join(sorted(origins))))
        else:
            self.today_summary.box.addWidget(
                muted("No paper yet for today. Fetch the news, then generate."))

        self.history_list.clear()
        for d in self.store.question_dates():
            n = len(self.store.questions_for(d))
            self.history_list.addItem(f"{d}   —   {n} questions")

        detected = Generator(self.settings).available_backends()
        pretty = {"api": "Anthropic API", "cli": "claude CLI", "offline": "offline templates"}
        text = "Backends: " + ", ".join(pretty.get(b, b) for b in detected)
        self.backend_label.setText(text)
        self.backend_label.setToolTip(f"Data folder: {EXPORT_DIR.parent}")
        if hasattr(self, "detected"):
            self.detected.setText(text)

        self._render_feeds()
        self._render_news()
        self._render_prelims()
        self._render_mains()
        self._render_progress()
        self._goto(self.stack.currentIndex())

    # ---------------------------------------------------------------- renders
    def _render_news(self) -> None:
        clear_layout(self.news_lay)
        needle = self.news_search.text().lower().strip() if hasattr(self, "news_search") else ""
        subject = self.news_subject.currentText() if hasattr(self, "news_subject") else "All subjects"
        shown = 0
        for a in self.articles:
            if subject != "All subjects" and a.subject != subject:
                continue
            if needle and needle not in (a.title + a.summary + a.body).lower():
                continue
            self.news_lay.addWidget(ArticleCard(a))
            shown += 1
        if not shown:
            self.news_lay.addWidget(muted(
                "Nothing here yet. Use “Fetch news” in the header to pull today's feeds."))
        self.news_lay.addStretch(1)

    def _render_prelims(self) -> None:
        clear_layout(self.prelims_lay)
        self.cards: list[QuestionCard] = []
        subject = self.prelims_subject.currentText() if hasattr(self, "prelims_subject") else "All subjects"
        fmt = self.prelims_format.currentData() if hasattr(self, "prelims_format") else None
        n = 0
        for q in self.questions:
            if subject != "All subjects" and q.subject != subject:
                continue
            if fmt and q.qtype != fmt:
                continue
            n += 1
            card = QuestionCard(n, q)
            card.answered.connect(self._on_answered)
            self.cards.append(card)
            self.prelims_lay.addWidget(card)
        if not n:
            self.prelims_lay.addWidget(muted(
                "No questions match. Generate a paper, or relax the filters."))
        self.prelims_lay.addStretch(1)

    def _render_mains(self) -> None:
        clear_layout(self.mains_lay)
        for i, m in enumerate(self.mains, 1):
            self.mains_lay.addWidget(MainsCard(i, m))
        if not self.mains:
            self.mains_lay.addWidget(muted("No Mains questions for today yet."))
        self.mains_lay.addStretch(1)

    def _render_progress(self) -> None:
        clear_layout(self.progress_lay)
        rows = self.store.subject_accuracy()
        card = Card()
        t = QLabel("Accuracy by subject")
        t.setObjectName("CardTitle")
        card.box.addWidget(t)
        if rows:
            for subject, total, ok in rows:
                card.box.addWidget(StatBar(subject, ok, total, theme.subject_color(subject)))
        else:
            card.box.addWidget(muted(
                "Attempt some questions — in the Prelims page or Quiz mode — and your "
                "subject-wise accuracy will build up here."))
        self.progress_lay.addWidget(card)

        arts, qs, att = self.store.totals()
        totals = Card()
        tt = QLabel("All time")
        tt.setObjectName("CardTitle")
        totals.box.addWidget(tt)
        totals.box.addWidget(QLabel(f"{arts} articles collected · {qs} questions set · "
                                    f"{att} attempts recorded"))
        self.progress_lay.addWidget(totals)
        self.progress_lay.addStretch(1)

    def _render_feeds(self) -> None:
        if not hasattr(self, "feed_list"):
            return
        self.feed_list.clear()
        for f in self.settings.feeds:
            self.feed_list.addItem(f"{f.get('name')}   —   {f.get('url')}   [{f.get('subject', 'Mixed')}]")

    # ---------------------------------------------------------------- actions
    def _on_answered(self, question: Question, chosen: int, correct: bool) -> None:
        self.store.record_attempt(question.id, chosen, correct)
        self._render_progress()
        arts, qs, att = self.store.totals()
        self.tile_attempts.set_value(str(att))

    def _reveal_all(self) -> None:
        for card in getattr(self, "cards", []):
            card.reveal(record=False)

    def _export(self, fmt: str) -> None:
        if not self.questions:
            QMessageBox.information(self, "Nothing to export", "Generate a paper first.")
            return
        suffix = "md" if fmt == "md" else "html"
        default = str(EXPORT_DIR / f"upsc-daily-{self.day}.{suffix}")
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Export paper", default)
        if not path:
            return
        out = export.write(self.day, self.questions, self.mains, self.articles,
                           fmt=suffix, path=Path(path))
        self.status.setText(f"Exported to {out}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def _load_history_day(self, item) -> None:
        day = item.text().split(" ")[0]
        self.day = day
        self.articles = self.store.articles_for(day)
        self.questions = self.store.questions_for(day)
        self.mains = self.store.mains_for(day)
        self._refresh_all()
        self._goto(2)

    def _add_feed(self) -> None:
        name = self.feed_name.text().strip()
        url = self.feed_url.text().strip()
        if not name or not url.startswith("http"):
            QMessageBox.information(self, "Check the feed",
                                    "A name and an http(s) feed URL are both needed.")
            return
        self.settings.feeds.append(
            {"name": name, "url": url, "subject": self.feed_subject.currentText()})
        self.settings.save()
        self.feed_name.clear()
        self.feed_url.clear()
        self._render_feeds()

    def _remove_feed(self) -> None:
        row = self.feed_list.currentRow()
        if row < 0:
            return
        del self.settings.feeds[row]
        self.settings.save()
        self._render_feeds()

    def _save_settings(self) -> None:
        self.settings.prelims_count = self.spin_prelims.value()
        self.settings.mains_count = self.spin_mains.value()
        self.settings.articles_per_feed = self.spin_per_feed.value()
        self.settings.backend = self.combo_backend.currentData()
        self.settings.model = self.edit_model.text().strip() or self.settings.model
        self.settings.save()
        self.status.setText("Settings saved")
        self._refresh_all()

    # ------------------------------------------------------------------- quiz
    def _quiz_set_running(self, on: bool) -> None:
        self.btn_quiz_next.setVisible(on)
        self.btn_quiz_skip.setVisible(on)
        self.btn_quiz_start.setVisible(not on)

    def _quiz_start(self) -> None:
        if not self.questions:
            QMessageBox.information(self, "No paper", "Generate today's paper first.")
            return
        self.quiz_items = list(self.questions)
        self.quiz_index = 0
        self.quiz_right = self.quiz_wrong = 0
        self.quiz_started = datetime.now()
        self.quiz_timer.start(1000)
        self._quiz_set_running(True)
        self._quiz_show()

    def _quiz_show(self) -> None:
        clear_layout(self.quiz_holder)
        if self.quiz_index >= len(self.quiz_items):
            self._quiz_finish()
            return
        q = self.quiz_items[self.quiz_index]
        card = QuestionCard(self.quiz_index + 1, q)
        card.answered.connect(self._quiz_answered)
        self.quiz_holder.addWidget(card)
        self.quiz_counter.setText(f"Question {self.quiz_index + 1} of {len(self.quiz_items)}")
        self.quiz_bar.setRange(0, len(self.quiz_items))
        self.quiz_bar.setValue(self.quiz_index)
        self._quiz_update_score()

    def _quiz_answered(self, question: Question, chosen: int, correct: bool) -> None:
        self.store.record_attempt(question.id, chosen, correct)
        if correct:
            self.quiz_right += 1
        else:
            self.quiz_wrong += 1
        self._quiz_update_score()
        QTimer.singleShot(1400, lambda: self._quiz_next(None))

    def _quiz_update_score(self) -> None:
        marks = self.quiz_right * 2 - self.quiz_wrong * (2 / 3)
        self.quiz_score.setText(
            f"{self.quiz_right} right · {self.quiz_wrong} wrong · {marks:.2f} marks")

    def _quiz_next(self, _=None) -> None:
        self.quiz_index += 1
        self._quiz_show()

    def _quiz_finish(self) -> None:
        self.quiz_timer.stop()
        self._quiz_set_running(False)
        total = len(self.quiz_items)
        attempted = self.quiz_right + self.quiz_wrong
        marks = self.quiz_right * 2 - self.quiz_wrong * (2 / 3)
        elapsed = self.quiz_clock.text()
        self.quiz_counter.setText("Test complete")
        self.quiz_bar.setValue(total)

        card = Card()
        t = QLabel("Result")
        t.setObjectName("CardTitle")
        card.box.addWidget(t)
        card.box.addWidget(QLabel(
            f"<span style='font-size:26px;font-weight:800;color:{theme.ACCENT}'>"
            f"{marks:.2f} / {total * 2}</span>"))
        card.box.addWidget(muted(
            f"{attempted} attempted of {total} · {self.quiz_right} correct · "
            f"{self.quiz_wrong} incorrect · {elapsed} taken · UPSC marking applied "
            f"(+2, −0.66)"))
        accuracy = int(self.quiz_right / attempted * 100) if attempted else 0
        card.box.addWidget(StatBar("Accuracy on attempted", self.quiz_right,
                                   max(attempted, 1), theme.GREEN))
        card.box.addWidget(muted(
            "In the real paper, a candidate at this accuracy would want to raise "
            "attempts only where the elimination is genuine — that is what the "
            f"{accuracy}% figure is telling you."))
        self.quiz_holder.addWidget(card)
        self._render_progress()

    def _tick(self) -> None:
        if not self.quiz_started:
            return
        secs = int((datetime.now() - self.quiz_started).total_seconds())
        self.quiz_clock.setText(f"{secs // 60:02d}:{secs % 60:02d}")
