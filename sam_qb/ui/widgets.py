"""Reusable widgets."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QComboBox, QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from ..query_model import FORMATS, Fmt

SQL_KEYWORDS = ("SELECT DISTINCT TOP FROM WHERE AND OR NOT IN IS NULL LIKE BETWEEN ORDER BY ASC DESC "
                "INNER LEFT RIGHT FULL OUTER JOIN ON AS CASE WHEN THEN ELSE END CAST CONVERT CONCAT "
                "LTRIM RTRIM UPPER LOWER SUBSTRING REPLACE PATINDEX REPLICATE ISNULL NULLIF DATEADD "
                "GETDATE ROUND varchar decimal int char date").split()


from .style import qcolor  # noqa: E402


class SqlHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.rules = []
        kw = QTextCharFormat()
        kw.setForeground(qcolor("#0B4FA0"))
        kw.setFontWeight(QFont.Bold)
        self.rules.append((re.compile(r"\b(" + "|".join(SQL_KEYWORDS) + r")\b", re.I), kw))
        st = QTextCharFormat()
        st.setForeground(qcolor("#A3302A"))
        self.rules.append((re.compile(r"'(?:[^']|'')*'"), st))
        br = QTextCharFormat()
        br.setForeground(qcolor("#6B3FA0"))
        self.rules.append((re.compile(r"\[[^\]]*\]"), br))
        cm = QTextCharFormat()
        cm.setForeground(qcolor("#3B7A3B"))
        cm.setFontItalic(True)
        self.rules.append((re.compile(r"--[^\n]*"), cm))

    def highlightBlock(self, text):
        for rx, fmt in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color:#D8DEE6")
    return f


def label(text, name=None, wrap=True):
    lb = QLabel(text)
    lb.setWordWrap(wrap)
    if name:
        lb.setObjectName(name)
    return lb


class ColumnPicker(QComboBox):
    """Editable, searchable combo listing Alias.Column for every table in the query."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(240)
        comp = self.completer()
        comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion)

    def populate(self, query, catalog, current: tuple[str, str] | None = None):
        self.blockSignals(True)
        self.clear()
        self.addItem("", None)
        for t in query.tables:
            for c in catalog.columns(t.table):
                self.addItem(f"{t.alias}.{c}", (t.alias, c))
        if current and current[0]:
            i = self.findText(f"{current[0]}.{current[1]}")
            if i < 0:
                self.addItem(f"{current[0]}.{current[1]}", current)
                i = self.count() - 1
            self.setCurrentIndex(i)
        self.blockSignals(False)

    def value(self) -> tuple[str, str]:
        d = self.currentData()
        if d:
            return d
        txt = self.currentText().strip()
        i = self.findText(txt)
        if i >= 0 and self.itemData(i):
            return self.itemData(i)
        return ("", "")


class FormatListEditor(QWidget):
    """Edits an ordered list of Fmt objects in place."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.formats: list[Fmt] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.add_combo = QComboBox()
        for k, (lbl, *_rest) in FORMATS.items():
            self.add_combo.addItem(lbl, k)
            self.add_combo.setItemData(self.add_combo.count() - 1, FORMATS[k][3], Qt.ToolTipRole)
        add_btn = QPushButton("Add format")
        add_btn.clicked.connect(self._add)
        top.addWidget(self.add_combo, 1)
        top.addWidget(add_btn)
        lay.addLayout(top)
        self.list = QListWidget()
        self.list.setMaximumHeight(130)
        self.list.currentRowChanged.connect(self._select)
        lay.addWidget(self.list)
        btns = QHBoxLayout()
        for txt, fn in (("Up", lambda: self._move(-1)), ("Down", lambda: self._move(1)), ("Remove", self._remove)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch()
        lay.addLayout(btns)
        self.help = label("", "hint")
        lay.addWidget(self.help)
        row = QHBoxLayout()
        self.a_lbl, self.a = QLabel("Option A"), QLineEdit()
        self.b_lbl, self.b = QLabel("Option B"), QLineEdit()
        for w in (self.a_lbl, self.a, self.b_lbl, self.b):
            row.addWidget(w)
        lay.addLayout(row)
        self.a.textEdited.connect(self._params)
        self.b.textEdited.connect(self._params)
        self._show_params(None)

    def set_formats(self, formats: list[Fmt]):
        self.formats = formats
        self._refresh()

    def _text(self, f: Fmt):
        lbl, a, b, _ = FORMATS.get(f.type, (f.type, None, None, ""))
        extra = []
        if a:
            extra.append(f"{a}: {f.a!r}")
        if b:
            extra.append(f"{b}: {f.b!r}")
        return lbl + (f"   ({', '.join(extra)})" if extra else "")

    def _refresh(self, keep=None):
        self.list.blockSignals(True)
        self.list.clear()
        for f in self.formats:
            self.list.addItem(self._text(f))
        self.list.blockSignals(False)
        if keep is not None and 0 <= keep < len(self.formats):
            self.list.setCurrentRow(keep)
        else:
            self._show_params(None)

    def _add(self):
        t = self.add_combo.currentData()
        f = Fmt(t)
        if t in ("left", "right"):
            f.a = "1"
        if t == "decimals":
            f.a = "2"
        if t == "pad_zeros":
            f.a = "9"
        self.formats.append(f)
        self._refresh(len(self.formats) - 1)
        self.changed.emit()

    def _remove(self):
        r = self.list.currentRow()
        if 0 <= r < len(self.formats):
            del self.formats[r]
            self._refresh(min(r, len(self.formats) - 1))
            self.changed.emit()

    def _move(self, d):
        r = self.list.currentRow()
        n = r + d
        if 0 <= r < len(self.formats) and 0 <= n < len(self.formats):
            self.formats[r], self.formats[n] = self.formats[n], self.formats[r]
            self._refresh(n)
            self.changed.emit()

    def _select(self, r):
        self._show_params(self.formats[r] if 0 <= r < len(self.formats) else None)

    def _show_params(self, f: Fmt | None):
        if f is None:
            for w in (self.a_lbl, self.a, self.b_lbl, self.b):
                w.setVisible(False)
            self.help.setText("Formats are applied top to bottom. Select one to see its options.")
            return
        lbl, a, b, hlp = FORMATS.get(f.type, (f.type, None, None, ""))
        self.help.setText(hlp)
        self.a_lbl.setVisible(bool(a))
        self.a.setVisible(bool(a))
        self.b_lbl.setVisible(bool(b))
        self.b.setVisible(bool(b))
        self.a_lbl.setText(a or "")
        self.b_lbl.setText(b or "")
        self.a.setText(f.a)
        self.b.setText(f.b)

    def _params(self):
        r = self.list.currentRow()
        if 0 <= r < len(self.formats):
            self.formats[r].a = self.a.text()
            self.formats[r].b = self.b.text()
            self.list.item(r).setText(self._text(self.formats[r]))
            self.changed.emit()


def list_item(text, data=None, tip=None):
    it = QListWidgetItem(text)
    if data is not None:
        it.setData(Qt.UserRole, data)
    if tip:
        it.setToolTip(tip)
    return it


def choose_codes(parent, title, opts, current, multi=True):
    """Checklist dialog of (code, description). Returns the chosen codes or None if cancelled."""
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QVBoxLayout, QLineEdit
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(440, 500)
    lay = QVBoxLayout(dlg)
    flt = QLineEdit()
    flt.setPlaceholderText("Type to filter...")
    lay.addWidget(flt)
    lst = QListWidget()
    for code, desc in opts:
        it = QListWidgetItem(f"{desc}  ({code})" if desc else code)
        it.setData(Qt.UserRole, code)
        if multi:
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if code in current else Qt.Unchecked)
        lst.addItem(it)
        if not multi and code in current:
            lst.setCurrentItem(it)
    flt.textChanged.connect(lambda t: [lst.item(i).setHidden(t.lower() not in lst.item(i).text().lower())
                                       for i in range(lst.count())])
    lay.addWidget(lst)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lst.itemDoubleClicked.connect(lambda _i: (not multi) and dlg.accept())
    lay.addWidget(bb)
    if not dlg.exec():
        return None
    if multi:
        return [lst.item(i).data(Qt.UserRole) for i in range(lst.count()) if lst.item(i).checkState() == Qt.Checked]
    it = lst.currentItem()
    return [it.data(Qt.UserRole)] if it else []


def make_pattern_edit(current: str, staff: bool, allow_blank: bool = False):
    """Username / email pattern picker: presets (with examples), or type your own {token} pattern."""
    from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget
    from .. import district

    class PatternEdit(QWidget):
        def __init__(self):
            super().__init__()
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            row = QHBoxLayout()
            self.combo = QComboBox()
            if allow_blank:
                self.combo.addItem("Same as the username", "")
            for k, lab in district.PATTERN_PRESETS:
                self.combo.addItem(f"{lab}   ({district.example(k, staff)})", k)
            self.combo.addItem("Custom pattern (type it on the right)...", "__custom__")
            self.edit = QLineEdit()
            self.edit.setPlaceholderText("e.g. {f}.{last}")
            self.edit.setMaximumWidth(190)
            self.edit.setToolTip("Tokens: {first} {last} {middle} {f} {l} {m} (initials), {first3}/{last5} (first N "
                                 "letters), {id} {id4} (ID or its last N digits), {grad} {grad2} (graduation year). "
                                 "Anything else (. _ - letters, digits) is kept as typed.")
            row.addWidget(self.combo, 1)
            row.addWidget(self.edit)
            lay.addLayout(row)
            self.ex = QLabel()
            self.ex.setStyleSheet("color:#4A5568;")
            lay.addWidget(self.ex)
            cur = district.normalize_pattern(current) if (current or not allow_blank) else ""
            self.edit.setText(cur)
            i = self.combo.findData(cur)
            self.combo.setCurrentIndex(i if i >= 0 else self.combo.count() - 1)
            self.combo.currentIndexChanged.connect(self._picked)
            self.edit.textChanged.connect(self._typed)
            self._typed(cur)

        def _picked(self, _i):
            k = self.combo.currentData()
            if k != "__custom__":
                self.edit.blockSignals(True)
                self.edit.setText(k)
                self.edit.blockSignals(False)
                self._typed(k)
            else:
                self.edit.setFocus()

        def _typed(self, text):
            i = self.combo.findData(text.strip())
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(i if i >= 0 else self.combo.count() - 1)
            self.combo.blockSignals(False)
            if not text.strip() and allow_blank:
                self.ex.setText("Uses the username pattern.")
                return
            errs = district.pattern_errors(text)
            self.ex.setText(("<span style='color:#B42318'>" + "; ".join(errs) + "</span>") if errs else
                            f"Jane Marie Smith{'' if staff else ', class of 2027'} -> "
                            f"<b>{district.example(text, staff)}</b>")

        def value(self) -> str:
            t = self.edit.text().strip()
            if not t and allow_blank:
                return ""
            return t if not district.pattern_errors(t) else district.normalize_pattern("")

        def is_valid(self) -> bool:
            t = self.edit.text().strip()
            return (not t and allow_blank) or not district.pattern_errors(t)

    return PatternEdit()
