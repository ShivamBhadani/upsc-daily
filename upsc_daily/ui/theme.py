"""Colour palette and stylesheet for the application."""

from __future__ import annotations

BG = "#0e1014"
SURFACE = "#161a21"
SURFACE_2 = "#1d222c"
SURFACE_3 = "#252b37"
BORDER = "#2b313d"
TEXT = "#e7e9ef"
MUTED = "#8f97a8"
ACCENT = "#d9a441"
ACCENT_DIM = "#8a6a2a"
BLUE = "#5b9bd5"
GREEN = "#46b07f"
RED = "#e0656c"

SUBJECT_COLORS: dict[str, str] = {
    "Polity & Governance": "#5b9bd5",
    "Economy": "#46b07f",
    "Environment & Ecology": "#5fbf9b",
    "Science & Technology": "#a97fd6",
    "History, Art & Culture": "#d9a441",
    "Geography": "#d98b5b",
    "International Relations": "#d96a9b",
    "Social Issues & Schemes": "#7fb0d6",
    "Governance": "#5b9bd5",
    "Mixed": "#8f97a8",
}


def subject_color(subject: str) -> str:
    return SUBJECT_COLORS.get(subject, MUTED)


STYLESHEET = f"""
* {{ font-family: "Segoe UI", "Inter", system-ui, sans-serif; }}

QWidget {{ background: {BG}; color: {TEXT}; font-size: 14px; }}
QLabel {{ background: transparent; }}

QMainWindow, QDialog {{ background: {BG}; }}

/* ---------- sidebar ---------- */
#Sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#Brand {{ font-size: 19px; font-weight: 700; color: {TEXT}; padding: 22px 20px 2px 20px; }}
#BrandSub {{ font-size: 11px; color: {ACCENT}; letter-spacing: 2px;
             padding: 0 20px 18px 20px; text-transform: uppercase; }}
QPushButton#NavButton {{
    background: transparent; border: none; border-radius: 9px;
    color: {MUTED}; text-align: left; padding: 11px 16px; margin: 2px 12px;
    font-size: 14px; font-weight: 500;
}}
QPushButton#NavButton:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#NavButton:checked {{
    background: {SURFACE_3}; color: {ACCENT}; font-weight: 600;
    border-left: 3px solid {ACCENT};
}}
#SidebarFoot {{ color: {MUTED}; font-size: 11px; padding: 14px 20px; }}

/* ---------- header ---------- */
#Header {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
#PageTitle {{ font-size: 22px; font-weight: 700; }}
#PageSub {{ font-size: 12px; color: {MUTED}; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 16px; color: {TEXT}; font-weight: 500;
}}
QPushButton:hover {{ background: {SURFACE_3}; border-color: {ACCENT_DIM}; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {MUTED}; background: {SURFACE}; border-color: {BORDER}; }}
QPushButton#Primary {{
    background: {ACCENT}; color: #17130a; border: none; font-weight: 700;
}}
QPushButton#Primary:hover {{ background: #e5b45a; }}
QPushButton#Primary:disabled {{ background: {ACCENT_DIM}; color: #3a3223; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid {BORDER}; }}
QPushButton#Ghost:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}

/* ---------- cards ---------- */
#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
#Card:hover {{ border-color: {SURFACE_3}; }}
#CardTitle {{ font-size: 15px; font-weight: 600; }}
#Stem {{ font-size: 15.5px; font-weight: 600; line-height: 150%; }}
#Muted {{ color: {MUTED}; font-size: 12px; }}
#Explain {{ background: {SURFACE_2}; border-radius: 10px; border-left: 3px solid {GREEN};
            padding: 12px 14px; color: {TEXT}; font-size: 13.5px; }}
#Chip {{ font-size: 10.5px; font-weight: 700; padding: 3px 9px; border-radius: 9px;
         letter-spacing: .6px; }}

/* ---------- options ---------- */
QRadioButton {{ padding: 9px 12px; border-radius: 9px; background: {SURFACE_2};
                border: 1px solid transparent; font-size: 14px; }}
QRadioButton:hover {{ background: {SURFACE_3}; }}
QRadioButton::indicator {{ width: 15px; height: 15px; border-radius: 8px;
                           border: 2px solid {MUTED}; background: transparent; }}
QRadioButton::indicator:checked {{ border: 5px solid {ACCENT}; background: {BG}; }}
QRadioButton[state="right"] {{ background: rgba(70,176,127,0.16); border-color: {GREEN}; }}
QRadioButton[state="wrong"]  {{ background: rgba(224,101,108,0.16); border-color: {RED}; }}

/* ---------- inputs ---------- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 7px 10px; selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER};
                               selection-background-color: {SURFACE_3}; outline: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px;
                        border: 2px solid {MUTED}; background: transparent; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ---------- misc ---------- */
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 5px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 4px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 5px; min-width: 40px; }}

QProgressBar {{ background: {SURFACE_2}; border: none; border-radius: 4px;
                height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

QListWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QListWidget::item {{ padding: 9px; border-radius: 7px; }}
QListWidget::item:selected {{ background: {SURFACE_3}; color: {ACCENT}; }}

QTableWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
                gridline-color: {BORDER}; }}
QHeaderView::section {{ background: {SURFACE_2}; border: none; padding: 8px;
                        color: {MUTED}; font-weight: 600; }}

QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER};
            padding: 6px; border-radius: 6px; }}
QSplitter::handle {{ background: {BORDER}; }}
"""
