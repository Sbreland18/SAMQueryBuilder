"""Start page: new query, templates and saved queries."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget, QLineEdit, QTreeWidget, QTreeWidgetItem, QComboBox)

from ..app_config import APP_NAME
from ..paths import queries_dir
from .widgets import label


class HomePage(QWidget):
    new_query = Signal()
    open_template = Signal(dict)
    open_file = Signal(str)
    browse = Signal()
    exports = Signal()
    assistant = Signal()
    import_sql = Signal()
    restored = Signal(str)        # a saved query was restored from its history
    open_uploads = Signal()
    open_tool = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 24, 30, 24)
        lay.addWidget(label(APP_NAME, "title"))
        lay.addWidget(label("Build SQL for SAM's Ad Hoc Query module step by step - no SQL knowledge needed.", "subtitle"))
        lay.addSpacing(12)
        row = QHBoxLayout()
        lay.addLayout(row, 1)

        # ---- start card
        c1 = self._card("Start")
        ba = QPushButton("Describe what you need\nThe Query Assistant builds it for you")
        ba.setObjectName("big")
        ba.setStyleSheet("background:#E8F1FB; border:1px solid #1F5FAD;")
        ba.clicked.connect(self.assistant)
        c1.layout().addWidget(ba)
        b = QPushButton("New blank query\nPick tables and columns yourself")
        b.setObjectName("big")
        b.clicked.connect(self.new_query)
        c1.layout().addWidget(b)
        b2 = QPushButton("Open a saved query (.samq)...")
        b2.setObjectName("big")
        b2.clicked.connect(self.browse)
        c1.layout().addWidget(b2)
        b4 = QPushButton("Import a query you already have\nPaste SQL from SAM and edit it here")
        b4.setObjectName("big")
        b4.clicked.connect(self.import_sql)
        c1.layout().addWidget(b4)
        b3 = QPushButton("Export to a platform\nClever, OneRoster/ClassLink, Microsoft SDS,\nGoogle, Canvas, NWEA...")
        b3.setObjectName("big")
        b3.clicked.connect(self.exports)
        c1.layout().addWidget(b3)
        c1.layout().addWidget(label(
            "<b>Tip:</b> Starting from a template is the fastest way to learn. Open one, look at each step, "
            "then change it to fit your needs.", "hint"))
        c1.layout().addStretch()
        row.addWidget(c1, 1)

        # ---- templates card
        c2 = self._card("Start from a template")
        self.tsearch = QLineEdit()
        self.tsearch.setPlaceholderText("Search templates...")
        self.tsearch.textChanged.connect(self._fill_templates)
        c2.layout().addWidget(self.tsearch)
        self.templates = QTreeWidget()
        self.templates.setHeaderHidden(True)
        self.templates.itemDoubleClicked.connect(self._tmpl_open)
        self.templates.currentItemChanged.connect(self._tmpl_desc)
        c2.layout().addWidget(self.templates, 1)
        self.tdesc = label("", "hint")
        self.tdesc.setMinimumHeight(60)
        self.tdesc.setAlignment(Qt.AlignTop)
        c2.layout().addWidget(self.tdesc)
        ob = QPushButton("Use this template")
        ob.setObjectName("primary")
        ob.clicked.connect(lambda: self._tmpl_open(self.templates.currentItem()))
        c2.layout().addWidget(ob)
        row.addWidget(c2, 2)

        # ---- saved card
        c3 = self._card("My saved queries")
        fr = QHBoxLayout()
        self.saved_search = QLineEdit()
        self.saved_search.setPlaceholderText("Search name, table, column or tag...")
        self.saved_search.textChanged.connect(self.refresh_saved)
        fr.addWidget(self.saved_search, 2)
        self.saved_tag = QComboBox()
        self.saved_tag.currentIndexChanged.connect(self.refresh_saved)
        fr.addWidget(self.saved_tag, 1)
        c3.layout().addLayout(fr)
        self.saved = QListWidget()
        self.saved.itemDoubleClicked.connect(
            lambda it: it.data(Qt.UserRole) and self.open_file.emit(it.data(Qt.UserRole)))
        self.saved.setContextMenuPolicy(Qt.CustomContextMenu)
        self.saved.customContextMenuRequested.connect(self._saved_menu)
        c3.layout().addWidget(self.saved, 1)
        c3.layout().addWidget(label("Right-click a query to star it, tag it or see its history.", "hint"))
        self.saved_in = label(f"Saved in: {queries_dir()}", "hint")
        c3.layout().addWidget(self.saved_in)
        rb = QPushButton("Refresh")
        rb.clicked.connect(self.refresh_saved)
        c3.layout().addWidget(rb)
        row.addWidget(c3, 1)

        # ---- nightly uploads status board + tools
        row2 = QHBoxLayout()
        lay.addLayout(row2)
        c4 = self._card("Nightly uploads")
        self.status = QTreeWidget()
        self.status.setHeaderLabels(["Upload", "Last run", "Result", "Rows", "Last good upload"])
        self.status.setRootIsDecorated(False)
        self.status.setMaximumHeight(150)
        self.status.itemDoubleClicked.connect(lambda *_: self.open_uploads.emit())
        c4.layout().addWidget(self.status)
        self.status_hint = label("", "hint")
        c4.layout().addWidget(self.status_hint)
        row2.addWidget(c4, 3)
        c5 = self._card("District tools")
        for txt, key in (("CAC Agent setup walkthrough", "cac"), ("Data cleanup reports", "cleanup"),
                         ("Vendor privacy register", "register"), ("Year-end rollover checklist", "rollover")):
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, k=key: self.open_tool.emit(k))
            c5.layout().addWidget(b)
        c5.layout().addStretch()
        row2.addWidget(c5, 1)
        self._templates: list[dict] = []

    def _card(self, title):
        f = QFrame()
        f.setObjectName("card")
        l = QVBoxLayout(f)
        t = QLabel(title)
        t.setStyleSheet("font-size:13pt;font-weight:600;color:#1B2A41")
        l.addWidget(t)
        return f

    def set_templates(self, templates: list[dict]):
        self._templates = templates
        self._fill_templates()

    def _fill_templates(self):
        self.templates.clear()
        flt = self.tsearch.text().lower().strip()
        cats: dict[str, QTreeWidgetItem] = {}
        for t in self._templates:
            if flt and flt not in (t.get("name", "") + t.get("description", "")).lower():
                continue
            cat = t.get("category") or "General"
            if cat not in cats:
                ci = QTreeWidgetItem([cat])
                f = ci.font(0)
                f.setBold(True)
                ci.setFont(0, f)
                self.templates.addTopLevelItem(ci)
                ci.setExpanded(True)
                cats[cat] = ci
            it = QTreeWidgetItem([t.get("name", "Template")])
            it.setData(0, Qt.UserRole, t)
            it.setToolTip(0, t.get("description", ""))
            cats[cat].addChild(it)

    def _tmpl_desc(self, it, _p=None):
        t = it.data(0, Qt.UserRole) if it else None
        self.tdesc.setText(t.get("description", "") if t else "")

    def _tmpl_open(self, it, _c=None):
        t = it.data(0, Qt.UserRole) if it else None
        if t:
            self.open_template.emit(t)

    def refresh_saved(self, *_a):
        from .. import library
        if not hasattr(self, "saved_tag"):
            return
        cur = self.saved_tag.currentData()
        self.saved_tag.blockSignals(True)
        self.saved_tag.clear()
        self.saved_tag.addItem("All queries", "")
        self.saved_tag.addItem("\u2605 Favorites", "*")
        for t in library.all_tags():
            self.saved_tag.addItem(f"Tag: {t}", t)
        self.saved_tag.setCurrentIndex(max(0, self.saved_tag.findData(cur)))
        self.saved_tag.blockSignals(False)
        if hasattr(self, "saved_in"):
            self.saved_in.setText(f"Saved in: {queries_dir()}")
        cur = self.saved_tag.currentData() or ""
        rows = library.queries(self.saved_search.text(), "" if cur == "*" else cur, favorites_only=cur == "*")
        self.saved.clear()
        for r in rows:
            tags = f"   [{', '.join(r['tags'])}]" if r["tags"] else ""
            it = QListWidgetItem(("\u2605 " if r["favorite"] else "") + f"{r['name']}    "
                                 f"({r['modified']:%m/%d/%Y}){tags}")
            it.setData(Qt.UserRole, r["path"])
            it.setData(Qt.UserRole + 1, r)
            it.setToolTip((r["description"] + "\n\n" if r["description"] else "") + r["path"])
            self.saved.addItem(it)
        if not rows:
            self.saved.addItem("No saved queries match." if (self.saved_search.text() or cur) else
                               "No saved queries yet.")

    def _saved_menu(self, pos):
        from PySide6.QtWidgets import QInputDialog, QMenu
        from .. import library
        it = self.saved.itemAt(pos)
        r = it.data(Qt.UserRole + 1) if it else None
        if not r:
            return
        m = QMenu(self)
        a_open = m.addAction("Open")
        a_fav = m.addAction("Remove from favorites" if r["favorite"] else "\u2605 Add to favorites")
        a_tags = m.addAction("Tags...")
        a_hist = m.addAction("Version history...")
        a = m.exec(self.saved.mapToGlobal(pos))
        if a is a_open:
            self.open_file.emit(r["path"])
        elif a is a_fav:
            library.set_favorite(r["file"], not r["favorite"])
            self.refresh_saved()
        elif a is a_tags:
            text, ok = QInputDialog.getText(self, "Tags", "Tags (comma separated), e.g. Counselors, Weekly, "
                                                          "State reporting:", text=", ".join(r["tags"]))
            if ok:
                library.set_tags(r["file"], text.split(","))
                self.refresh_saved()
        elif a is a_hist:
            from .more_tools import HistoryDialog
            if HistoryDialog(r["path"], r["name"], self).exec():
                self.refresh_saved()
                self.restored.emit(r["path"])

    def set_status(self, rows: list[dict]):
        from PySide6.QtGui import QColor
        self.status.clear()
        colors = {"ok": "#1E7B34", "held": "#C2410C", "failed": "#B42318"}
        for r in rows:
            last = r.get("last") or {}
            tot = sum(v for v in (last.get("counts") or {}).values() if v and v > 0)
            it = QTreeWidgetItem([r["name"], (last.get("when") or "never").replace("T", " "),
                                  {"ok": "OK", "held": "HELD (safety net)", "failed": "FAILED"}.get(
                                      last.get("status", ""), "-"),
                                  f"{tot:,}" if last else "", (r.get("last_ok") or "").replace("T", " ")])
            if last.get("status") in colors:
                it.setForeground(2, QColor(colors[last["status"]]))
            it.setToolTip(2, last.get("message", ""))
            self.status.addTopLevelItem(it)
        for i in range(5):
            self.status.resizeColumnToContents(i)
        bad = sum(1 for r in rows if (r.get("last") or {}).get("status") in ("held", "failed"))
        if not rows:
            self.status_hint.setText("No upload profiles yet - set one up from Export to a platform > Upload setup.")
        elif bad:
            self.status_hint.setText(f"<span style='color:#B42318'><b>{bad} upload(s) need attention.</b></span> "
                                     "Double-click to open Package & Upload.")
        else:
            self.status_hint.setText("Double-click an upload to open Package & Upload.")

