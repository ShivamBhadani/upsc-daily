"""Reusable cards and small widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QRadioButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import pyq
from ..models import Article, MainsQuestion, Question
from . import theme

LETTERS = "abcd"


def chip(text: str, color: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("Chip")
    lbl.setStyleSheet(
        f"#Chip {{ color: {color}; background: rgba(255,255,255,0.05);"
        f" border: 1px solid {color}; }}"
    )
    lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lbl


def wrap(lbl: QLabel) -> QLabel:
    """Let a word-wrapped label shrink to whatever width it is given."""
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
    lbl.setMinimumWidth(120)
    return lbl


def muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Muted")
    return wrap(lbl)


def link_label(text: str, url: str) -> QLabel:
    lbl = QLabel(f'<a style="color:{theme.BLUE};text-decoration:none" href="{url}">{text}</a>')
    lbl.setObjectName("Muted")
    wrap(lbl)
    lbl.setOpenExternalLinks(False)
    lbl.linkActivated.connect(lambda u: QDesktopServices.openUrl(u))  # type: ignore[arg-type]
    return lbl


class Card(QFrame):
    """A rounded surface with a soft shadow."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.setMinimumWidth(360)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(shadow)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(20, 18, 20, 18)
        self.box.setSpacing(10)


class ArticleCard(Card):
    """One collected news item."""

    def __init__(self, article: Article, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(chip(article.subject, theme.subject_color(article.subject)))
        top.addStretch(1)
        top.addWidget(muted(article.source))
        self.box.addLayout(top)

        title = QLabel(article.title)
        title.setObjectName("CardTitle")
        wrap(title)
        self.box.addWidget(title)

        body = (article.summary or article.body)[:320]
        if body:
            self.box.addWidget(muted(body + ("…" if len(body) == 320 else "")))

        foot = QHBoxLayout()
        foot.addWidget(muted(article.published or ""))
        foot.addStretch(1)
        foot.addWidget(link_label("Open article ↗", article.url))
        self.box.addLayout(foot)


class QuestionCard(Card):
    """A Prelims MCQ with click-to-answer options and a reveal panel."""

    answered = Signal(object, int, bool)   # question, chosen index, was correct

    def __init__(self, index: int, question: Question, practice: bool = True,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.question = question
        self.practice = practice
        self._locked = False

        head = QHBoxLayout()
        head.setSpacing(8)
        num = QLabel(f"Q{index}")
        num.setStyleSheet(f"color:{theme.ACCENT};font-weight:800;font-size:15px;")
        head.addWidget(num)
        head.addWidget(chip(question.subject, theme.subject_color(question.subject)))
        head.addWidget(chip(question.difficulty, theme.MUTED))
        fmt = pyq.FORMAT_BY_KEY.get(question.qtype)
        fmt_name = fmt.name if fmt else question.qtype
        head.addWidget(chip(fmt_name, theme.ACCENT_DIM))
        if question.origin == "offline":
            head.addWidget(chip("offline draft", theme.RED))
        head.addStretch(1)
        self.box.addLayout(head)

        stem = QLabel(question.stem)
        stem.setObjectName("Stem")
        wrap(stem)
        self.box.addWidget(stem)

        if question.statements:
            for i, s in enumerate(question.statements, 1):
                row = QLabel(f"<b style='color:{theme.ACCENT}'>{i}.</b> {s}")
                wrap(row)
                row.setContentsMargins(10, 0, 0, 0)
                self.box.addWidget(row)

        if question.pairs:
            for left, right in question.pairs:
                row = QLabel(f"<b>{left}</b> &nbsp;—&nbsp; {right}")
                wrap(row)
                row.setContentsMargins(10, 0, 0, 0)
                self.box.addWidget(row)

        tail = pyq.closing_line(question.qtype, question.stem)
        if tail and (question.statements or question.pairs):
            tail_lbl = QLabel(tail)
            tail_lbl.setObjectName("Stem")
            wrap(tail_lbl)
            self.box.addWidget(tail_lbl)

        self.group = QButtonGroup(self)
        self.buttons: list[QRadioButton] = []
        for i, opt in enumerate(question.options):
            btn = QRadioButton(f"({LETTERS[i]})  {opt}")
            btn.setCursor(Qt.PointingHandCursor)
            self.group.addButton(btn, i)
            self.buttons.append(btn)
            self.box.addWidget(btn)
        self.group.idClicked.connect(self._choose)

        self.explain = QLabel()
        self.explain.setObjectName("Explain")
        wrap(self.explain)
        self.explain.setVisible(False)
        self.box.addWidget(self.explain)

        if question.source_url:
            self.box.addWidget(link_label(f"Source: {question.source_title or question.source_url} ↗",
                                          question.source_url))

        if not practice:
            self.reveal(record=False)

    def _choose(self, chosen: int) -> None:
        if self._locked:
            return
        self._locked = True
        correct = chosen == self.question.answer_index
        self.reveal(chosen=chosen)
        self.answered.emit(self.question, chosen, correct)

    def reveal(self, chosen: int | None = None, record: bool = True) -> None:
        key = self.question.answer_index
        for i, btn in enumerate(self.buttons):
            if i == key:
                btn.setProperty("state", "right")
            elif chosen is not None and i == chosen:
                btn.setProperty("state", "wrong")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        verdict = ""
        if chosen is not None:
            verdict = ("<b style='color:%s'>Correct.</b> " % theme.GREEN) if chosen == key \
                else ("<b style='color:%s'>Incorrect.</b> " % theme.RED)
        text = (f"{verdict}<b>Answer: ({LETTERS[key]})</b><br>{self.question.explanation}")
        if self.question.pyq_link:
            text += f"<br><br><i style='color:{theme.MUTED}'>{self.question.pyq_link}</i>"
        self.explain.setText(text)
        self.explain.setVisible(True)
        self._locked = True

    def set_revealed(self, on: bool) -> None:
        if on:
            self.reveal(record=False)
        else:
            self.explain.setVisible(False)
            self._locked = False
            for btn in self.buttons:
                btn.setProperty("state", "")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            self.group.setExclusive(False)
            for btn in self.buttons:
                btn.setChecked(False)
            self.group.setExclusive(True)


class MainsCard(Card):
    """A GS answer-writing prompt."""

    def __init__(self, index: int, item: MainsQuestion, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        head = QHBoxLayout()
        head.setSpacing(8)
        num = QLabel(f"{index}")
        num.setStyleSheet(f"color:{theme.ACCENT};font-weight:800;font-size:15px;")
        head.addWidget(num)
        head.addWidget(chip(item.gs_paper, theme.BLUE))
        head.addWidget(chip(f"{item.marks} marks", theme.MUTED))
        head.addWidget(chip(item.directive, theme.ACCENT_DIM))
        head.addStretch(1)
        self.box.addLayout(head)

        q = QLabel(item.question)
        q.setObjectName("Stem")
        wrap(q)
        self.box.addWidget(q)

        if item.hints:
            self.box.addWidget(muted("Cover these dimensions:"))
            for h in item.hints:
                row = QLabel(f"<span style='color:{theme.ACCENT}'>•</span> {h}")
                wrap(row)
                row.setContentsMargins(10, 0, 0, 0)
                self.box.addWidget(row)

        if item.source_url:
            self.box.addWidget(link_label(f"Source: {item.source_title} ↗", item.source_url))


class StatBar(QWidget):
    """A labelled horizontal accuracy bar."""

    def __init__(self, label: str, done: int, total: int, color: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pct = int(done / total * 100) if total else 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(6)
        row = QHBoxLayout()
        name = QLabel(label)
        name.setStyleSheet("font-weight:600;")
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(muted(f"{done}/{total}  ·  {pct}%"))
        lay.addLayout(row)

        track = QFrame()
        track.setFixedHeight(8)
        track.setStyleSheet(f"background:{theme.SURFACE_2};border-radius:4px;")
        tl = QHBoxLayout(track)
        tl.setContentsMargins(0, 0, 0, 0)
        fill = QFrame()
        fill.setStyleSheet(f"background:{color};border-radius:4px;")
        tl.addWidget(fill, max(pct, 1))
        spacer = QFrame()
        spacer.setStyleSheet("background:transparent;")
        tl.addWidget(spacer, max(100 - pct, 0))
        lay.addWidget(track)
