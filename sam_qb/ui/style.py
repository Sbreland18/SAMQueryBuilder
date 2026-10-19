"""Light and dark themes.

The app draws its own colors (Fusion style + a stylesheet + a palette) so text stays readable whatever Windows
uses. The theme is Light, Dark or Match Windows (View > Theme, saved in %APPDATA%\\...\\ui_prefs.json).

Many screens put status colors straight into text (e.g. <span style='color:#B42318'>) or item colors. In dark mode
those light-theme colors are translated automatically (DARK_MAP) wherever text, rich text, style sheets and item
colors are set, so every screen stays readable without each one knowing about the theme.
"""
from __future__ import annotations

import json
import re
import sys

ACCENT = "#1F5FAD"

LIGHT = {
    "text": "#1B2A41", "sub": "#4A5568", "bg": "#F5F7FA", "card": "#FFFFFF", "alt": "#EEF2F7",
    "border": "#D8DEE6", "input_border": "#C9D1DB", "button_border": "#B8C2CF", "hover": "#EEF3F9",
    "tab": "#E4E9F0", "header": "#EDF1F6", "select": "#CFE2F7", "menu_select": "#E8F1FB", "disabled": "#9AA5B1",
    "disabled_bg": "#F0F2F5", "placeholder": "#8A94A3", "accent": ACCENT, "accent_hover": "#184C8A",
    "accent_text": "#FFFFFF", "ok": "#1E7B34", "bad": "#B42318", "banner": "#FFF4CE", "banner_border": "#E7C65A",
    "info": "#E8F1FB", "info_border": "#B9D3F0", "nav": "#1B2A41", "nav_text": "#DCE3EC", "nav_sel": "#273A57",
    "nav_mark": "#5AA3F0", "tooltip": "#FFFFE1", "check_border": "#8A94A3", "link": ACCENT,
}
DARK = {
    "text": "#E6EBF2", "sub": "#A9B4C2", "bg": "#1B2027", "card": "#242A33", "alt": "#2B323C",
    "border": "#3A4350", "input_border": "#465060", "button_border": "#4F5A6B", "hover": "#313946",
    "tab": "#2A313B", "header": "#2F3742", "select": "#2E4A6E", "menu_select": "#2E4A6E", "disabled": "#6B7685",
    "disabled_bg": "#2A3038", "placeholder": "#7D8896", "accent": "#2B6CD4", "accent_hover": "#1F5DBF",
    "accent_text": "#FFFFFF", "ok": "#6FD08C", "bad": "#FF8A80", "banner": "#3A331D", "banner_border": "#8A7A3A",
    "info": "#1F3550", "info_border": "#2E4A6E", "nav": "#151A20", "nav_text": "#DCE3EC", "nav_sel": "#273A57",
    "nav_mark": "#5AA3F0", "tooltip": "#313946", "check_border": "#7D8896", "link": "#7CB7FF",
}

# light-theme colors used inside text / item colors -> readable equivalents on a dark background
DARK_MAP = {
    # text and status colors
    "#B42318": "#FF8A80", "#A3302A": "#FF9E80", "#1E7B34": "#6FD08C", "#3B7A3B": "#8BD08B", "#1B2A41": "#E6EBF2",
    "#4A5568": "#A9B4C2", "#718096": "#9AA5B1", "#C2410C": "#FFA270", "#9A6700": "#F2C94C", "#1F5FAD": "#7CB7FF",
    "#0B4FA0": "#7CB7FF", "#6B3FA0": "#C9A2FF", "#184C8A": "#5D9BFF", "#666666": "#A9B4C2", "#666": "#A9B4C2",
    # backgrounds and borders
    "#FFFFFF": "#242A33", "#F5F7FA": "#1B2027", "#EEF2F7": "#2B323C", "#E8F1FB": "#1F3550", "#FFFBEA": "#3A331D",
    "#FFF4CE": "#3A331D", "#E5D9A8": "#6B5E2E", "#E7C65A": "#8A7A3A", "#CBD5E1": "#3A4350", "#D8DEE6": "#3A4350",
    "#B9D3F0": "#2E4A6E", "#CFE2F7": "#2E4A6E", "#EDF1F6": "#2F3742", "#E4E9F0": "#2A313B", "#EEF3F9": "#313946",
    "#F0F2F5": "#2A3038", "#C9D1DB": "#465060", "#B8C2CF": "#4F5A6B", "#8A94A3": "#7D8896", "#9AA5B1": "#6B7685",
    "#FFFFE1": "#313946",
}
# Qt named colors used for list / table items
QT_NAMED_DARK = {"#ff0000": "#FF6B6B", "#808000": "#F2C94C", "#008000": "#6FD08C", "#000080": "#7CB7FF",
                 "#800000": "#FF8A80", "#808080": "#9AA5B1", "#a0a0a4": "#8A94A3", "#000000": "#E6EBF2"}

QSS_TEMPLATE = """
* {{ font-family: "Segoe UI", "Arial"; font-size: 10pt; }}
QWidget {{ color: {text}; }}
QCheckBox, QRadioButton, QLabel, QGroupBox {{ background: transparent; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {check_border}; border-radius: 3px; background: {card}; }}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url(CHECK_SVG); }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {check_border}; border-radius: 8px; background: {card}; }}
QRadioButton::indicator:hover {{ border-color: {accent}; }}
QRadioButton::indicator:checked {{ border: 4px solid {accent}; background: {accent_text}; width: 8px; height: 8px; }}
QCheckBox:disabled, QRadioButton:disabled, QLabel:disabled {{ color: {disabled}; }}
QTabWidget::pane {{ background: {bg}; border: 1px solid {border}; }}
QTabBar::tab {{ background: {tab}; color: {text}; padding: 6px 12px; border: 1px solid {border}; }}
QTabBar::tab:selected {{ background: {card}; font-weight: 600; }}
QMenuBar, QMenu {{ background: {card}; color: {text}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {menu_select}; color: {text}; }}
QMenu::item:disabled {{ color: {disabled}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}
QStatusBar {{ background: {card}; color: {text}; }}
QSplitter, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {bg}; }}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{ background: {select}; color: {text}; }}
QMainWindow, QDialog, QWizard, QWidget#page {{ background: {bg}; }}
QLabel#title {{ font-size: 20pt; font-weight: 600; color: {text}; }}
QLabel#subtitle {{ font-size: 11pt; color: {sub}; }}
QLabel#stepTitle {{ font-size: 15pt; font-weight: 600; color: {text}; }}
QLabel#hint {{ color: {sub}; }}
QLabel#ok {{ color: {ok}; font-weight: 600; }}
QLabel#bad {{ color: {bad}; font-weight: 600; }}
QLabel a {{ color: {link}; }}
QFrame#card {{ background: {card}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#banner {{ background: {banner}; border: 1px solid {banner_border}; border-radius: 6px; }}
QFrame#infobar {{ background: {info}; border: 1px solid {info_border}; border-radius: 6px; }}
QGroupBox {{ background: {card}; border: 1px solid {border}; border-radius: 6px; margin-top: 14px; padding: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {text}; font-weight: 600; }}
QPushButton {{ background: {card}; color: {text}; border: 1px solid {button_border}; border-radius: 5px; padding: 5px 12px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:checked {{ background: {select}; border-color: {accent}; }}
QPushButton:disabled {{ color: {disabled}; background: {disabled_bg}; }}
QPushButton#primary {{ background: {accent}; color: {accent_text}; border: 1px solid {accent}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#big {{ font-size: 11pt; padding: 12px 18px; text-align: left; }}
QListWidget#steps {{ background: {nav}; color: {nav_text}; border: none; font-size: 11pt; outline: none; }}
QListWidget#steps::item {{ padding: 12px 10px; border-left: 4px solid transparent; }}
QListWidget#steps::item:selected {{ background: {nav_sel}; color: white; border-left: 4px solid {nav_mark}; }}
QListWidget, QTreeWidget, QTableWidget, QPlainTextEdit, QTextEdit, QTextBrowser, QLineEdit, QComboBox, QSpinBox,
QDateEdit, QTimeEdit {{ background: {card}; color: {text}; border: 1px solid {input_border}; border-radius: 4px;
    selection-background-color: {accent}; selection-color: {accent_text}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QPlainTextEdit:disabled {{ background: {disabled_bg}; color: {disabled}; }}
QComboBox QAbstractItemView {{ background: {card}; color: {text}; selection-background-color: {select};
    selection-color: {text}; border: 1px solid {border}; }}
QTableWidget, QTreeWidget, QListWidget {{ alternate-background-color: {alt}; gridline-color: {border}; }}
QTableCornerButton::section {{ background: {header}; border: none; }}
QPlainTextEdit#sql {{ font-family: "Consolas", "Courier New", monospace; font-size: 10pt; }}
QHeaderView::section {{ background: {header}; color: {text}; border: none; border-right: 1px solid {border}; padding: 4px; font-weight: 600; }}
QToolBar {{ background: {card}; border-bottom: 1px solid {border}; spacing: 4px; padding: 4px; }}
QToolButton {{ padding: 5px 10px; border-radius: 4px; color: {text}; }}
QToolButton:checked {{ background: {select}; border: 1px solid {accent}; font-weight: 600; }}
QToolButton:hover {{ background: {hover}; }}
QToolTip {{ background: {tooltip}; color: {text}; border: 1px solid {border}; }}
QProgressBar {{ background: {card}; border: 1px solid {border}; border-radius: 4px; text-align: center; color: {text}; }}
QProgressBar::chunk {{ background: {accent}; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {bg}; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {button_border}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
"""

# back-compat: some tools import QSS
QSS = QSS_TEMPLATE.format(**LIGHT)

_mode = "light"            # the resolved mode in use: light | dark
_patched = False
_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b")


# ----------------------------------------------------------------------------- preference
def _prefs_path():
    from ..paths import root_dir
    return root_dir() / "ui_prefs.json"


def get_pref() -> str:
    """'light' | 'dark' | 'system'"""
    try:
        v = json.loads(_prefs_path().read_text(encoding="utf-8")).get("theme", "light")
        return v if v in ("light", "dark", "system") else "light"
    except Exception:
        return "light"


TEXT_SIZES = {100: "Normal", 115: "Larger", 130: "Large", 150: "Largest", 90: "Smaller"}


def get_text_size() -> int:
    try:
        v = int(json.loads(_prefs_path().read_text(encoding="utf-8")).get("text_size", 100))
        return v if v in TEXT_SIZES else 100
    except Exception:
        return 100


def set_text_size(value: int):
    try:
        p = _prefs_path()
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        d = {}
    d["text_size"] = int(value)
    _prefs_path().write_text(json.dumps(d, indent=1), encoding="utf-8")


def scale_qss(qss: str, pct: int) -> str:
    """Scale every 'Npt' font size in a style sheet."""
    if pct == 100:
        return qss
    return re.sub(r"(\d+(?:\.\d+)?)pt\b", lambda m: f"{round(float(m.group(1)) * pct / 100, 1):g}pt", qss)


def set_pref(value: str):
    try:
        p = _prefs_path()
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        d = {}
    d["theme"] = value
    _prefs_path().write_text(json.dumps(d, indent=1), encoding="utf-8")


def windows_is_dark(app=None) -> bool:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        hints = (app or QGuiApplication.instance()).styleHints()
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        except Exception:
            pass
    return False


def is_dark() -> bool:
    return _mode == "dark"


def tokens() -> dict:
    return DARK if is_dark() else LIGHT


# ----------------------------------------------------------------------------- color translation
def color(hex_or_name: str) -> str:
    """A light-theme color as it should look in the current theme."""
    if not is_dark() or not hex_or_name:
        return hex_or_name
    h = hex_or_name.strip()
    if h.lower() == "white":
        return DARK_MAP["#FFFFFF"]
    return DARK_MAP.get(h.upper(), DARK_MAP.get(h, h))


def map_text(text):
    """Translate light-theme colors inside rich text / style sheets for dark mode."""
    if not is_dark() or not isinstance(text, str) or "#" not in text:
        return text
    return _HEX.sub(lambda m: DARK_MAP.get(m.group(0).upper(), m.group(0)), text)


def qcolor(c):
    """QColor for a light-theme color in the current theme."""
    from PySide6.QtGui import QColor
    return QColor(color(c))


def _map_brush(b):
    from PySide6.QtGui import QBrush, QColor
    if not is_dark():
        return b
    try:
        col = QColor(b) if not isinstance(b, QBrush) else b.color()
    except Exception:
        return b
    name = col.name().lower()
    new = QT_NAMED_DARK.get(name) or DARK_MAP.get(name.upper())
    return QColor(new) if new else b


def _install_patches():
    """Route text, style sheets and item colors through the dark-mode translation."""
    global _patched
    if _patched:
        return
    _patched = True
    from PySide6.QtWidgets import (QLabel, QListWidgetItem, QTableWidgetItem, QTextBrowser, QTextEdit,
                                   QTreeWidgetItem, QWidget)

    def wrap1(cls, name):
        orig = getattr(cls, name)

        def f(self, text, *a):
            return orig(self, map_text(text), *a)
        setattr(cls, name, f)

    wrap1(QLabel, "setText")
    wrap1(QWidget, "setStyleSheet")
    wrap1(QTextEdit, "setHtml")
    wrap1(QTextBrowser, "setHtml")

    def wrap_fg(cls, with_col):
        orig = cls.setForeground
        if with_col:
            def f(self, col, brush):
                return orig(self, col, _map_brush(brush))
        else:
            def f(self, brush):
                return orig(self, _map_brush(brush))
        cls.setForeground = f

    wrap_fg(QTreeWidgetItem, True)
    wrap_fg(QTableWidgetItem, False)
    wrap_fg(QListWidgetItem, False)


class _PolishFilter:
    """Translates labels / style sheets that were set in constructors (before the patches see them)."""

    def __init__(self, app):
        from PySide6.QtCore import QEvent, QObject

        class F(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.Polish and is_dark():
                    try:
                        from PySide6.QtWidgets import QLabel, QWidget
                        if isinstance(obj, QLabel) and "#" in obj.text() and not obj.property("_qb_mapped"):
                            obj.setProperty("_qb_mapped", True)
                            obj.setText(obj.text())
                        if isinstance(obj, QWidget) and "#" in obj.styleSheet() and not obj.property("_qb_ss"):
                            obj.setProperty("_qb_ss", True)
                            obj.setStyleSheet(obj.styleSheet())
                    except Exception:
                        pass
                return False
        self.f = F(app)
        app.installEventFilter(self.f)


_filter = None


# ----------------------------------------------------------------------------- apply
def apply_theme(app, mode: str | None = None):
    """mode: 'light' | 'dark' | 'system' (default: the saved preference)."""
    global _mode, _filter
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    pref = mode or get_pref()
    _mode = "dark" if (pref == "dark" or (pref == "system" and windows_is_dark(app))) else "light"
    t = tokens()
    app.setStyle("Fusion")
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if is_dark() else Qt.ColorScheme.Light)  # Qt 6.8+
    except Exception:
        pass
    pal = QPalette()
    text, base, window = QColor(t["text"]), QColor(t["card"]), QColor(t["bg"])
    for group in (QPalette.Active, QPalette.Inactive):
        pal.setColor(group, QPalette.Window, window)
        pal.setColor(group, QPalette.WindowText, text)
        pal.setColor(group, QPalette.Base, base)
        pal.setColor(group, QPalette.AlternateBase, QColor(t["alt"]))
        pal.setColor(group, QPalette.Text, text)
        pal.setColor(group, QPalette.Button, base)
        pal.setColor(group, QPalette.ButtonText, text)
        pal.setColor(group, QPalette.BrightText, QColor("#FFFFFF"))
        pal.setColor(group, QPalette.ToolTipBase, QColor(t["tooltip"]))
        pal.setColor(group, QPalette.ToolTipText, text)
        pal.setColor(group, QPalette.PlaceholderText, QColor(t["placeholder"]))
        pal.setColor(group, QPalette.Highlight, QColor(t["accent"]))
        pal.setColor(group, QPalette.HighlightedText, QColor(t["accent_text"]))
        pal.setColor(group, QPalette.Link, QColor(t["link"]))
        pal.setColor(group, QPalette.LinkVisited, QColor(t["link"]))
        pal.setColor(group, QPalette.Light, QColor(t["hover"]))
        pal.setColor(group, QPalette.Midlight, QColor(t["border"]))
        pal.setColor(group, QPalette.Mid, QColor(t["button_border"]))
        pal.setColor(group, QPalette.Dark, QColor(t["input_border"]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t["disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.Base, QColor(t["disabled_bg"]))
    pal.setColor(QPalette.Disabled, QPalette.Button, QColor(t["disabled_bg"]))
    pal.setColor(QPalette.Disabled, QPalette.Window, window)
    app.setPalette(pal)
    import os
    import tempfile
    svg = os.path.join(tempfile.gettempdir(), "samqb_check.svg")
    try:
        with open(svg, "w") as fh:
            fh.write('<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 15 15">'
                     '<path d="M3 7.5l3 3 6-6" fill="none" stroke="white" stroke-width="2.2" '
                     'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    except OSError:
        pass
    _install_patches()
    if _filter is None:
        _filter = _PolishFilter(app)
    pct = get_text_size()
    app.setStyleSheet(scale_qss(QSS_TEMPLATE.format(**t), pct).replace("CHECK_SVG", svg.replace("\\", "/")))
    try:
        f = app.font()
        f.setPointSizeF(10 * pct / 100)
        app.setFont(f)
    except Exception:
        pass
    return _mode


def contrast(fg: str, bg: str) -> float:
    """WCAG contrast ratio of two hex colors (used by the tests)."""
    def lum(h):
        h = h.lstrip("#")
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)
