"""'Describe your query' assistant window."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QLineEdit, QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QRadioButton, QSplitter, QTabWidget, QVBoxLayout, QWidget,
                               QGridLayout)

from ..assistant import EXAMPLES, build_conversation, build_from_text
from ..query_model import generate_sql
from .dialogs import TaskWorker
from .sample_view import SampleResults
from .widgets import SqlHighlighter, label


class AssistantDialog(QDialog):
    use_query = Signal(object)          # QueryDef
    open_settings = Signal()

    def __init__(self, catalog, get_settings, parent=None):
        super().__init__(parent)
        self.catalog, self.get_settings = catalog, get_settings
        self.plan = None
        self.worker = None
        self.setWindowTitle("Query Assistant - describe what you need")
        self.resize(1100, 820)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Describe the list you want in plain English. The assistant picks the tables, links, "
                            "columns, filters and sort order, shows sample results, and lists anything you should "
                            "double-check. You can then fine-tune it in the builder.", "subtitle"))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("e.g. All enrolled 9th graders at the high school with their homeroom teacher "
                                     "and parent phone numbers, sorted by last name")
        self.text.setMaximumHeight(90)
        lay.addWidget(self.text)

        ex = QGridLayout()
        ex.addWidget(QLabel("<b>Try:</b>"), 0, 0)
        for i, e in enumerate(EXAMPLES):
            b = QPushButton(e if len(e) < 60 else e[:57] + "...")
            b.setToolTip(e)
            b.setStyleSheet("text-align:left; padding:3px 8px; color:#1F5FAD;")
            b.clicked.connect(lambda _=False, e=e: (self.text.setPlainText(e), self.build()))
            ex.addWidget(b, 1 + i // 2, i % 2)
        lay.addLayout(ex)

        row = QHBoxLayout()
        self.mode_rules = QRadioButton("Built-in helper (works offline, free)")
        self.mode_ai = QRadioButton("AI helper (Claude - needs an API key)")
        grp = QButtonGroup(self)
        grp.addButton(self.mode_rules)
        grp.addButton(self.mode_ai)
        s = get_settings()
        (self.mode_ai if s.get("ai_api_key") and s.get("ai_default") else self.mode_rules).setChecked(True)
        row.addWidget(self.mode_rules)
        row.addWidget(self.mode_ai)
        setb = QPushButton("AI settings...")
        setb.clicked.connect(self.open_settings)
        row.addWidget(setb)
        row.addStretch()
        self.go = QPushButton("Build my query")
        self.go.setObjectName("primary")
        self.go.setMinimumHeight(34)
        self.go.clicked.connect(self.build)
        row.addWidget(self.go)
        lay.addLayout(row)
        self.privacy = label("AI helper: only your description, table/column names and District Settings codes are "
                             "sent to Claude - never student or staff data.", "hint")
        lay.addWidget(self.privacy)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("background:#E8F1FB; border:1px solid #B9D3F0; border-radius:6px; padding:8px;"
                                   "font-size:10.5pt;")
        self.summary.setVisible(False)
        lay.addWidget(self.summary)
        rrow = QHBoxLayout()
        self.refine = QLineEdit()
        self.refine.setPlaceholderText("Change something: 'also add birth date', 'remove email', 'only 10th grade', "
                                       "'sort by homeroom'...")
        self.refine.returnPressed.connect(self._refine)
        self.refine_btn = QPushButton("Update")
        self.refine_btn.clicked.connect(self._refine)
        self.restart = QPushButton("Start over")
        self.restart.clicked.connect(self._restart)
        rrow.addWidget(QLabel("<b>Refine:</b>"))
        rrow.addWidget(self.refine, 1)
        rrow.addWidget(self.refine_btn)
        rrow.addWidget(self.restart)
        self.refine_box = QWidget()
        self.refine_box.setLayout(rrow)
        self.refine_box.setVisible(False)
        lay.addWidget(self.refine_box)
        self.messages: list[str] = []

        split = QSplitter(Qt.Vertical)
        top = QWidget()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        c1 = QVBoxLayout()
        c1.addWidget(QLabel("<b>What I understood</b>"))
        self.understood = QListWidget()
        c1.addWidget(self.understood)
        c2 = QVBoxLayout()
        c2.addWidget(QLabel("<b>Please check</b>"))
        self.unsure = QListWidget()
        self.unsure.setWordWrap(True)
        c2.addWidget(self.unsure)
        tl.addLayout(c1, 1)
        tl.addLayout(c2, 1)
        split.addWidget(top)
        self.tabs = QTabWidget()
        self.sample = SampleResults()
        self.tabs.addTab(self.sample, "Sample results")
        self.sql = QPlainTextEdit()
        self.sql.setObjectName("sql")
        self.sql.setReadOnly(True)
        SqlHighlighter(self.sql.document())
        self.tabs.addTab(self.sql, "SQL")
        split.addWidget(self.tabs)
        split.setSizes([200, 380])
        lay.addWidget(split, 1)

        bottom = QHBoxLayout()
        self.fb_good = QPushButton("Looks right")
        self.fb_good.setToolTip("Tell the helper it understood you (saved on this PC only)")
        self.fb_good.clicked.connect(lambda: self._feedback(True))
        self.fb_bad = QPushButton("This isn't right...")
        self.fb_bad.setToolTip("Describe what you expected - saved so the helper can be improved in an update")
        self.fb_bad.clicked.connect(lambda: self._feedback(False))
        for b in (self.fb_good, self.fb_bad):
            b.setEnabled(False)
            bottom.addWidget(b)
        self.fb_note = QLabel("")
        self.fb_note.setStyleSheet("color:#1E7B34")
        bottom.addWidget(self.fb_note)
        bottom.addStretch()
        self.use = QPushButton("Open in the builder")
        self.use.setObjectName("primary")
        self.use.setEnabled(False)
        self.use.clicked.connect(self._use)
        bottom.addWidget(self.use)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        lay.addLayout(bottom)

    def build(self):
        text = self.text.toPlainText().strip()
        if "\n+ " in text:   # edited conversation: first line + refinements
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            self.messages = [lines[0]] + [ln[2:].strip() for ln in lines[1:] if ln.startswith("+")]
            self._show(build_conversation(self.messages, self.catalog, self.get_settings()))
            return
        if not text:
            self.status.setText("Type a description first.")
            return
        settings = self.get_settings()
        self.messages = [text]
        if self.mode_ai.isChecked():
            if not settings.get("ai_api_key"):
                self.status.setText("<span style='color:#B42318'>Add your Anthropic API key in AI settings first, "
                                    "or use the built-in helper.</span>")
                return
            from ..ai_helper import ask_claude
            self.go.setEnabled(False)
            self.status.setText("Asking Claude... (usually 5-20 seconds)")
            self.worker = TaskWorker(ask_claude, text, self.catalog, settings)
            self.worker.progress.connect(lambda m, _p: self.status.setText(m))
            self.worker.done.connect(self._ai_done)
            self.worker.start()
        else:
            self._show(build_conversation(self.messages, self.catalog, settings))

    def _refine(self):
        extra = self.refine.text().strip()
        if not extra or not self.messages:
            return
        self.messages.append(extra)
        self.refine.clear()
        if self.mode_ai.isChecked() and self.get_settings().get("ai_api_key"):
            from ..ai_helper import ask_claude
            text = self.messages[0] + "\n\nChanges requested afterwards:\n- " + "\n- ".join(self.messages[1:])
            self.go.setEnabled(False)
            self.status.setText("Asking Claude...")
            self.worker = TaskWorker(ask_claude, text, self.catalog, self.get_settings())
            self.worker.progress.connect(lambda m, _p: self.status.setText(m))
            self.worker.done.connect(self._ai_done)
            self.worker.start()
        else:
            self._show(build_conversation(self.messages, self.catalog, self.get_settings()))
        self.text.setPlainText("\n".join([self.messages[0]] + [f"+ {m}" for m in self.messages[1:]]))

    def _restart(self):
        self.messages = []
        self.text.clear()
        self.summary.setVisible(False)
        self.refine_box.setVisible(False)
        self.understood.clear()
        self.unsure.clear()
        self.use.setEnabled(False)
        self.text.setFocus()

    def _ai_done(self, plan, err):
        self.go.setEnabled(True)
        if err:
            self.status.setText(f"<span style='color:#B42318'>AI helper failed: {err}</span> - showing the "
                                "built-in helper's version instead.")
            self._show(build_conversation(self.messages or [self.text.toPlainText()], self.catalog,
                                          self.get_settings()), keep_status=True)
            return
        self._show(plan)

    def _show(self, plan, keep_status=False):
        self.plan = plan
        if not keep_status:
            self.status.setText(f"<b>{plan.source}</b>: {len(plan.query.tables)} tables, "
                                f"{len(plan.query.columns)} columns.")
        if getattr(plan, "summary", ""):
            self.summary.setText("<b>Here's what I built:</b> " + plan.summary)
            self.summary.setVisible(True)
        self.refine_box.setVisible(True)
        self.understood.clear()
        for u in plan.understood:
            self.understood.addItem(QListWidgetItem("- " + u))
        self.unsure.clear()
        for u in plan.unsure or ["Nothing flagged - still glance at the sample results."]:
            it = QListWidgetItem("- " + u)
            if plan.unsure:
                it.setForeground(Qt.darkYellow)
            self.unsure.addItem(it)
        self.sample.show_query(plan.query, self.catalog)
        self.sql.setPlainText(generate_sql(plan.query))
        self.use.setEnabled(True)
        self.fb_good.setEnabled(True)
        self.fb_bad.setEnabled(True)
        self.fb_note.setText("")

    def _feedback(self, good: bool):
        if not getattr(self, "plan", None):
            return
        from PySide6.QtWidgets import QInputDialog
        from ..feedback import record
        comment = ""
        if not good:
            comment, ok = QInputDialog.getMultiLineText(
                self, "What was wrong?",
                "What did you expect? (for example: 'I wanted 9th through 12th, not just 12th' or "
                "'Homeroom teacher should be a column')", "")
            if not ok:
                return
        record(self.messages, self.plan, good, comment, generate_sql(self.plan.query))
        self.fb_good.setEnabled(False)
        self.fb_bad.setEnabled(False)
        self.fb_note.setText("Thanks - feedback saved." + ("" if good else
                             " Try rewording below, or use Help > Export assistant feedback to send it in."))

    def _use(self):
        if self.plan:
            self.use_query.emit(self.plan.query)
            self.accept()
