"""Dialogs for: explain a query, fill-in values, nightly schedule timeline, data quality trends, team folder,
sharing a query with other districts and automatic backups."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTime, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QTimeEdit, QVBoxLayout, QWidget)

from .. import paths
from ..app_config import APP_NAME, GITHUB_REPO, SUPPORT_EMAIL
from .style import qcolor
from .widgets import label, list_item

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
LEVEL_COLOR = {"error": "#B42318", "warn": "#C2410C", "info": "#4A5568"}


def _time_edit(value: str, default="06:00") -> QTimeEdit:
    t = QTimeEdit(QTime.fromString(value or default, "HH:mm"))
    t.setDisplayFormat("h:mm AP")
    return t


def _day_combo(value: str) -> QComboBox:
    cb = QComboBox()
    for d in DAYS:
        cb.addItem(d.title(), d)
    cb.setCurrentIndex(max(0, cb.findData(value or "SUN")))
    return cb


# ============================================================================ explain a query
class ExplainDialog(QDialog):
    """Explains the query being edited, or SQL pasted in (e.g. an inherited query)."""

    def __init__(self, catalog, query=None, parent=None, open_in_builder=None):
        super().__init__(parent)
        self.catalog, self.query, self.open_in_builder = catalog, query, open_in_builder
        self.setWindowTitle("Explain a query")
        self.resize(900, 720)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Paste a query (for example one you inherited) and click <b>Explain</b> to see in plain "
                            "English what it lists, which rows it includes or leaves out and how the tables "
                            "connect.", "subtitle"))
        self.sql = QPlainTextEdit()
        self.sql.setObjectName("sql")
        self.sql.setPlaceholderText("SELECT ... FROM ...")
        self.sql.setMaximumHeight(200)
        lay.addWidget(self.sql)
        row = QHBoxLayout()
        b = QPushButton("Explain")
        b.setObjectName("primary")
        b.clicked.connect(self.explain_sql)
        row.addWidget(b)
        if query is not None:
            b2 = QPushButton("Explain the query I'm editing")
            b2.clicked.connect(lambda: self.show_query(self.query, []))
            row.addWidget(b2)
        self.open_btn = QPushButton("Open it in the builder")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open)
        row.addWidget(self.open_btn)
        cp = QPushButton("Copy explanation")
        cp.clicked.connect(self._copy)
        row.addWidget(cp)
        row.addStretch()
        lay.addLayout(row)
        self.out = QTextBrowser()
        lay.addWidget(self.out, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._last = None
        if query is not None:
            self.show_query(query, [])

    def explain_sql(self):
        text = self.sql.toPlainText().strip()
        if not text:
            return
        from ..sql_import import import_sql
        try:
            q, notes = import_sql(text, self.catalog)
        except Exception as e:  # noqa: BLE001
            self.out.setHtml(f"<p style='color:#B42318'>Couldn't read that SQL: {e}</p>")
            return
        self.show_query(q, notes)

    def show_query(self, q, notes):
        from ..dupcheck import warnings as dup_warnings
        from ..explain import explain_html
        self._last = q
        self.open_btn.setEnabled(self.open_in_builder is not None and q is not self.query)
        html = explain_html(q, self.catalog)
        extra = dup_warnings(q, self.catalog)
        if extra:
            html += "<p><b>Watch out</b></p><ul>" + "".join(f"<li style='color:#C2410C'>{w}</li>" for w in extra) + "</ul>"
        if notes:
            html += "<p><b>Notes from reading the SQL</b></p><ul>" + "".join(f"<li>{n}</li>" for n in notes) + "</ul>"
        self.out.setHtml(html)

    def _open(self):
        if self._last is not None and self.open_in_builder:
            self.open_in_builder(self._last)
            self.accept()

    def _copy(self):
        from ..explain import explain_text
        if self._last is not None:
            QApplication.clipboard().setText(explain_text(self._last, self.catalog))


# ============================================================================ fill-in values
class AskValuesDialog(QDialog):
    def __init__(self, prompts: list[dict], settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fill in the values")
        self.prompts, self.settings = prompts, settings
        lay = QVBoxLayout(self)
        lay.addWidget(label("This query asks for these values each time you copy it:"))
        f = QFormLayout()
        self.edits = {}
        remembered = settings.get("ask_values") or {}
        for p in prompts:
            prev = remembered.get(p["prompt"])
            if p["two"]:
                a, b = QLineEdit(), QLineEdit()
                a.setText(str(prev[0]) if isinstance(prev, list) else p["default"])
                b.setText(str(prev[1]) if isinstance(prev, list) else p["default2"])
                w = QWidget()
                h = QHBoxLayout(w)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(a)
                h.addWidget(QLabel("and"))
                h.addWidget(b)
                self.edits[p["prompt"]] = (a, b)
                f.addRow(p["prompt"] + ":", w)
            else:
                e = QLineEdit(str(prev) if prev is not None and not isinstance(prev, list) else p["default"])
                if p["op"] in ("in", "not_in"):
                    e.setPlaceholderText("several values: separate with commas")
                elif p["op"] == "last_days":
                    e.setPlaceholderText("number of days")
                self.edits[p["prompt"]] = e
                f.addRow(p["prompt"] + ":", e)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self) -> dict:
        out = {}
        for k, e in self.edits.items():
            out[k] = (e[0].text().strip(), e[1].text().strip()) if isinstance(e, tuple) else e.text().strip()
        return out

    def _ok(self):
        if any((not v[0] or not v[1]) if isinstance(v, tuple) else not v for v in self.values().values()):
            QMessageBox.information(self, "Fill in the values", "Fill in every value first.")
            return
        self.accept()


def sql_with_values(parent, q, settings: dict, header=True) -> str | None:
    """Generate SQL, asking for fill-in values first when the query has any. None = cancelled."""
    from ..askvalues import asked, remember, with_values
    from ..query_model import generate_sql
    prompts = asked(q) if not q.sql_override.strip() else []
    if not prompts:
        return generate_sql(q, header=header)
    d = AskValuesDialog(prompts, settings, parent)
    if d.exec() != QDialog.Accepted:
        return None
    vals = d.values()
    remember(settings, vals)
    paths.save_settings(settings, audit=False)
    return generate_sql(with_values(q, vals), header=header)


# ============================================================================ nightly schedule timeline
KIND_COLOR = {"cac": "#1F5FAD", "listener": "#6B3FA0", "upload": "#1E7B34", "report": "#9A6700",
              "health": "#C2410C", "backup": "#4A5568", "dq": "#A3302A"}
KIND_NAME = {"cac": "SAM CAC jobs", "listener": "CAS Agent Listener", "upload": "Upload", "report": "Report email",
             "health": "Health report", "backup": "Backup", "dq": "Data quality"}


class _TimelineBar(QWidget):
    def __init__(self):
        super().__init__()
        self.events = []
        self.setMinimumHeight(110)

    def sizeHint(self):
        return QSize(800, 120)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, right, y = 20, w - 20, 46
        p.setPen(QPen(qcolor("#B8C2CF"), 3))
        p.drawLine(QPointF(left, y), QPointF(right, y))
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() * 0.8))
        p.setFont(f)
        p.setPen(qcolor("#4A5568"))
        for hr in range(0, 25, 3):
            x = left + (right - left) * hr / 24
            p.drawLine(QPointF(x, y - 4), QPointF(x, y + 4))
            lbl = "12 AM" if hr in (0, 24) else ("12 PM" if hr == 12 else f"{hr % 12} {'AM' if hr < 12 else 'PM'}")
            p.drawText(QRectF(x - 30, y + 8, 60, 16), Qt.AlignCenter, lbl)
        lanes = {}
        for e in self.events:
            x = left + (right - left) * e["min"] / 1440
            lane = lanes.get(round(x / 10), 0)
            lanes[round(x / 10)] = lane + 1
            p.setPen(Qt.NoPen)
            p.setBrush(qcolor(KIND_COLOR.get(e["kind"], "#4A5568")))
            p.drawEllipse(QPointF(x, y - 12 - lane * 10), 5, 5)
        # legend
        x = left
        for k, name in KIND_NAME.items():
            p.setBrush(qcolor(KIND_COLOR[k]))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x + 5, h - 14), 5, 5)
            p.setPen(qcolor("#1B2A41"))
            tw = p.fontMetrics().horizontalAdvance(name)
            p.drawText(QPointF(x + 14, h - 10), name)
            x += tw + 30
        p.end()


class TimelineDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Nightly schedule timeline")
        self.resize(1000, 700)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Everything that runs on a schedule, on one 24-hour line. Uploads should start at least "
                            "an hour after their SAM CAC Agent jobs and 30 minutes after the CAS Agent Listener. "
                            "Record CAC job times in the CAC Agent walkthrough.", "subtitle"))
        row = QHBoxLayout()
        row.addWidget(QLabel("CAS Agent Listener runs at:"))
        self.listener = _time_edit(settings.get("cac_listener_time") or "02:00")
        self.has_listener = QCheckBox("set")
        self.has_listener.setChecked(bool(settings.get("cac_listener_time")))
        self.listener.setEnabled(self.has_listener.isChecked())
        self.has_listener.toggled.connect(self.listener.setEnabled)
        self.has_listener.toggled.connect(self._save)
        self.listener.timeChanged.connect(self._save)
        row.addWidget(self.listener)
        row.addWidget(self.has_listener)
        row.addStretch()
        lay.addLayout(row)
        self.bar = _TimelineBar()
        lay.addWidget(self.bar)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "What", "How often"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)
        lay.addWidget(QLabel("<b>Checks</b>"))
        self.problems = QListWidget()
        self.problems.setMaximumHeight(170)
        lay.addWidget(self.problems)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.refresh()

    def _save(self, *_a):
        self.settings["cac_listener_time"] = self.listener.time().toString("HH:mm") if self.has_listener.isChecked() \
            else ""
        paths.save_settings(self.settings)
        self.refresh()

    def refresh(self):
        from ..timeline import events, problems
        ev = events(self.settings)
        self.bar.events = ev
        self.bar.update()
        self.table.setRowCount(0)
        for e in ev:
            r = self.table.rowCount()
            self.table.insertRow(r)
            t = QTime.fromString(e["time"], "HH:mm").toString("h:mm AP")
            for c, v in enumerate((t, e["label"], e["when"])):
                it = QTableWidgetItem(v)
                if c == 1:
                    it.setForeground(qcolor(KIND_COLOR.get(e["kind"], "#1B2A41")))
                self.table.setItem(r, c, it)
        self.problems.clear()
        found = problems(self.settings)
        for lvl, msg in found:
            it = list_item(("Problem: " if lvl == "error" else "Check: " if lvl == "warn" else "Tip: ") + msg)
            it.setForeground(qcolor(LEVEL_COLOR[lvl]))
            self.problems.addItem(it)
        if not found:
            it = list_item("No timing problems found." if ev else "Nothing is scheduled yet.")
            it.setForeground(qcolor("#1E7B34"))
            self.problems.addItem(it)


# ============================================================================ data quality trends
class _Spark(QWidget):
    def __init__(self, values):
        super().__init__()
        self.values = values
        self.setMinimumSize(140, 26)

    def paintEvent(self, _e):
        if len(self.values) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width() - 6, self.height() - 6
        lo, hi = min(self.values), max(self.values)
        span = (hi - lo) or 1
        pts = [QPointF(3 + w * i / (len(self.values) - 1), 3 + h - h * (v - lo) / span)
               for i, v in enumerate(self.values)]
        better = self.values[-1] <= self.values[0]
        p.setPen(QPen(qcolor("#1E7B34" if better else "#B42318"), 2))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        p.end()


class DataQualityDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Data quality trends")
        self.resize(980, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(label("How many records each Data cleanup report finds, week by week - green lines are "
                            "shrinking (getting better), red ones are growing. Counts come from the cleanup CSVs in "
                            "the folder below (or the SAM connection when it's on). Only counts are stored.",
                            "subtitle"))
        from ..health import get as hget
        row = QHBoxLayout()
        row.addWidget(QLabel("Cleanup results folder:"))
        self.folder = QLineEdit(hget(settings)["cleanup_folder"])
        self.folder.setPlaceholderText(r"where the CAC Agent saves the Data cleanup reports, e.g. C:\SAM Exports\Cleanup")
        self.folder.editingFinished.connect(self._save_folder)
        row.addWidget(self.folder, 1)
        b = QPushButton("Browse...")
        b.clicked.connect(self._browse)
        row.addWidget(b)
        lay.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Report", "Now", "Change since last", "Trend", "Since"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 4):
            self.table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)
        sr = QHBoxLayout()
        b = QPushButton("Take a snapshot now")
        b.setObjectName("primary")
        b.clicked.connect(self._snap)
        sr.addWidget(b)
        sr.addWidget(QLabel("Weekly snapshot:"))
        d = settings.get("dq_schedule") or {}
        self.day = _day_combo(d.get("day") or "MON")
        self.time = _time_edit(d.get("time") or "06:30")
        sr.addWidget(self.day)
        sr.addWidget(QLabel("at"))
        sr.addWidget(self.time)
        b = QPushButton("Schedule in Windows")
        b.clicked.connect(self._schedule)
        sr.addWidget(b)
        b = QPushButton("Remove schedule")
        b.clicked.connect(self._unschedule)
        sr.addWidget(b)
        b = QPushButton("Export history (CSV)...")
        b.clicked.connect(self._export)
        sr.addWidget(b)
        sr.addStretch()
        lay.addLayout(sr)
        self.status = label("", "hint")
        lay.addWidget(self.status)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.refresh()

    def _save_folder(self):
        self.settings.setdefault("health", {})["cleanup_folder"] = self.folder.text().strip()
        paths.save_settings(self.settings)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Cleanup results folder", self.folder.text())
        if d:
            self.folder.setText(d.replace("/", "\\"))
            self._save_folder()

    def refresh(self):
        from ..dqtrend import table
        rows = table()
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(f"{r['latest']:,}"))
            ch = r["change"]
            it = QTableWidgetItem("-" if ch is None else ("no change" if ch == 0 else f"{ch:+,}"))
            if ch:
                it.setForeground(qcolor("#B42318" if ch > 0 else "#1E7B34"))
            self.table.setItem(i, 2, it)
            self.table.setCellWidget(i, 3, _Spark([v for _d, v in r["values"]]))
            self.table.setItem(i, 4, QTableWidgetItem(dt.date.fromisoformat(r["values"][0][0]).strftime("%m/%d/%Y")))
            self.table.setRowHeight(i, 30)
        self.table.setColumnWidth(3, 160)
        self.status.setText("" if rows else "No snapshots yet - set the folder, then take a snapshot.")

    def _snap(self):
        from ..dqtrend import take_snapshot
        self._save_folder()
        try:
            s = take_snapshot(self.settings)
            self.status.setText(f"Snapshot saved: {sum(s['counts'].values()):,} records in {len(s['counts'])} reports.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Snapshot", str(e))
        self.refresh()

    def _schedule(self):
        from ..dqtrend import schedule
        self.settings["dq_schedule"] = {"enabled": True, "day": self.day.currentData(),
                                        "time": self.time.time().toString("HH:mm")}
        paths.save_settings(self.settings)
        try:
            schedule(self.settings)
            self.status.setText("Scheduled in Windows Task Scheduler.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Schedule", str(e))

    def _unschedule(self):
        from ..scheduler import delete
        self.settings.setdefault("dq_schedule", {})["enabled"] = False
        paths.save_settings(self.settings)
        self.status.setText(delete("Data quality snapshot"))

    def _export(self):
        import csv
        from ..dqtrend import history, report_names
        fn, _ = QFileDialog.getSaveFileName(self, "Export history", "data_quality_history.csv", "CSV (*.csv)")
        if not fn:
            return
        h = history()
        names = report_names()
        files = sorted({f for s in h for f in s["counts"]})
        with open(fn, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Report"] + [s["date"] for s in h])
            for f in files:
                w.writerow([names.get(f, f)] + [s["counts"].get(f, "") for s in h])
        self.status.setText(f"Saved {fn}")


# ============================================================================ team folder
class TeamFolderDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Team folder")
        self.resize(760, 480)
        lay = QVBoxLayout(self)
        lay.addWidget(label(
            "Point every tech-team PC at the same network folder to share one copy of: District Settings, SAM "
            "codes and schools, the vendor privacy register and sign-offs, export school choices, CAC folders and "
            "times, district versions of export files, vendor-template packages and saved queries.<br><br>"
            "<b>Each PC keeps its own</b> upload profiles and passwords, alert email settings, the SAM connection "
            "and the admin PIN. If the folder can't be reached, the app keeps working with the last copy it "
            "saw.", "subtitle"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Team folder:"))
        self.folder = QLineEdit(settings.get("team_folder", ""))
        self.folder.setPlaceholderText(r"\\server\share\SAM Query Builder   (blank = this PC only)")
        row.addWidget(self.folder, 1)
        b = QPushButton("Browse...")
        b.clicked.connect(self._browse)
        row.addWidget(b)
        lay.addLayout(row)
        self.folder.textChanged.connect(self._status)
        self.status = label("")
        lay.addWidget(self.status)
        self.copy_mine = QCheckBox("This is the first PC: copy my settings, district versions, packages and saved "
                                   "queries into the team folder")
        lay.addWidget(self.copy_mine)
        lay.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._status()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Team folder", self.folder.text())
        if d:
            self.folder.setText(d.replace("/", "\\"))
            self._status()

    def _status(self, *_a):
        typed = self.folder.text().strip()
        info = paths.team_info({"team_folder": typed}) if typed else {}
        has_team_file = bool(info) and bool(info.get("keys"))
        if info and has_team_file:
            self.status.setText(f"<span style='color:#1E7B34'>This folder is already used by your team.</span> Last "
                                f"change {info['updated'].replace('T', ' ') or '-'} by {info['updated_by'] or '-'}. "
                                "This PC will take the team's settings.")
            self.copy_mine.setChecked(False)
        elif info:
            self.status.setText("This folder is empty - this PC's settings can start it.")
            self.copy_mine.setChecked(True)
        elif typed:
            self.status.setText("<span style='color:#B42318'>That folder can't be reached right now.</span>")
        else:
            self.status.setText("Not using a team folder - everything is kept on this PC.")
            self.copy_mine.setChecked(False)

    def _save(self):
        import shutil
        from pathlib import Path
        new = self.folder.text().strip()
        if new and not Path(new).is_dir():
            QMessageBox.warning(self, "Team folder", "That folder can't be reached. Check the path and that you "
                                                    "can open it in File Explorer.")
            return
        old_q = paths.queries_dir()
        old_ov = paths.user_dir() / "package_overrides"
        from ..template_builder import store_dir
        old_pk = store_dir()
        copy_mine = bool(new) and self.copy_mine.isChecked()
        if copy_mine and paths.team_info({"team_folder": new}).get("keys") and QMessageBox.question(
                self, "Team folder", "This folder already holds your team's settings. Replace them with this PC's "
                                     "settings?") != QMessageBox.Yes:
            return
        if copy_mine:
            tf = Path(new)
            for src, dst in ((old_q, tf / "Queries"), (old_ov, tf / "package_overrides"),
                             (old_pk, tf / "custom_packages")):
                if src.is_dir() and src != dst:
                    for f in src.rglob("*"):
                        if f.is_file():
                            target = dst / f.relative_to(src)
                            if not target.exists():
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(f, target)
        paths.join_team(self.settings, new, copy_mine)
        self.accept()


# ============================================================================ share a query
class ShareQueryDialog(QDialog):
    def __init__(self, query, settings: dict, parent=None):
        super().__init__(parent)
        from ..community import prepare
        self.settings = settings
        self.shared, notes = prepare(query, settings)
        self.setWindowTitle("Share this query with other districts")
        self.resize(760, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Send this query's design (never any data) to the community library. Once it's "
                            "reviewed, every district gets it as a template in a data update.", "subtitle"))
        f = QFormLayout()
        self.name = QLineEdit(query.name)
        f.addRow("Name:", self.name)
        self.desc = QPlainTextEdit(query.description)
        self.desc.setPlaceholderText("What it's for and anything to change before running it")
        self.desc.setMaximumHeight(110)
        f.addRow("Description:", self.desc)
        self.author = QLineEdit((settings.get("district") or {}).get("district_name", ""))
        self.author.setPlaceholderText("your name and/or district, for credit (optional)")
        f.addRow("Shared by:", self.author)
        lay.addLayout(f)
        if notes:
            lay.addWidget(label("<b>Before you share:</b><ul>" + "".join(f"<li>{n}</li>" for n in notes) + "</ul>"))
        from ..explain import explain_html
        from .. import catalog as _c
        try:
            cat = _c.Catalog.load()
        except Exception:
            cat = None
        prev = QTextBrowser()
        prev.setHtml("<b>What other districts will see</b>" + explain_html(query, cat))
        lay.addWidget(prev, 1)
        row = QHBoxLayout()
        b = QPushButton("Open on GitHub")
        b.setObjectName("primary")
        b.setToolTip(f"Opens a new issue on github.com/{GITHUB_REPO} (free GitHub account needed)")
        b.clicked.connect(self._github)
        row.addWidget(b)
        b = QPushButton("Send by email")
        b.setEnabled(bool(SUPPORT_EMAIL))
        b.setToolTip(f"Sends to {SUPPORT_EMAIL}" if SUPPORT_EMAIL else "No support email address is set in this version")
        b.clicked.connect(self._email)
        row.addWidget(b)
        b = QPushButton("Save file...")
        b.clicked.connect(self._save)
        row.addWidget(b)
        row.addStretch()
        b = QPushButton("Close")
        b.clicked.connect(self.reject)
        row.addWidget(b)
        lay.addLayout(row)
        self.status = label("", "hint")
        lay.addWidget(self.status)

    def _compose(self):
        from ..community import compose
        return compose(self.shared, self.name.text(), self.desc.toPlainText(), self.author.text())

    def _github(self):
        from ..community import github_url
        t, body = self._compose()
        QApplication.clipboard().setText(body)
        QDesktopServices.openUrl(QUrl(github_url(t, body)))
        self.status.setText("Opened GitHub - sign in and click 'Submit new issue'. If the query was too long for the "
                            "link, paste it from your clipboard.")

    def _email(self):
        from ..bugreport import mailto_url, send_email
        t, body = self._compose()
        try:
            if send_email(self.settings, t, body):
                self.status.setText(f"Sent to {SUPPORT_EMAIL}. Thank you!")
                return
        except Exception:
            pass
        QApplication.clipboard().setText(body)
        QDesktopServices.openUrl(QUrl(mailto_url(t, body)))
        self.status.setText("Opened your mail program - paste the full text from your clipboard if it's cut short.")

    def _save(self):
        t, body = self._compose()
        fn, _ = QFileDialog.getSaveFileName(self, "Save shared query", "shared_query.txt", "Text (*.txt)")
        if fn:
            with open(fn, "w", encoding="utf-8") as fh:
                fh.write(f"{t}\n\n{body}\n")
            self.status.setText(f"Saved {fn} - attach it to an email or a GitHub issue.")


# ============================================================================ automatic backups
class AutoBackupDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        from ..backup import auto_settings
        self.settings = settings
        a = auto_settings(settings)
        self.setWindowTitle("Automatic backups")
        self.resize(720, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Back up this district's settings, district versions of export files and (optionally) "
                            "saved queries to a folder on a schedule - ideally a network share that is itself "
                            "backed up. Passwords are never included; restore with File > Restore settings.",
                            "subtitle"))
        f = QFormLayout()
        row = QHBoxLayout()
        self.folder = QLineEdit(a["folder"])
        self.folder.setPlaceholderText(r"\\server\backups\SAM Query Builder")
        row.addWidget(self.folder, 1)
        b = QPushButton("Browse...")
        b.clicked.connect(self._browse)
        row.addWidget(b)
        f.addRow("Backup folder:", row)
        sr = QHBoxLayout()
        self.day = _day_combo(a["day"])
        self.time = _time_edit(a["time"])
        sr.addWidget(self.day)
        sr.addWidget(QLabel("at"))
        sr.addWidget(self.time)
        sr.addStretch()
        f.addRow("Every week on:", sr)
        self.keep = QSpinBox()
        self.keep.setRange(1, 104)
        self.keep.setValue(int(a["keep"]))
        f.addRow("Keep the newest:", self.keep)
        self.queries = QCheckBox("Include saved queries")
        self.queries.setChecked(bool(a["include_queries"]))
        f.addRow("", self.queries)
        lay.addLayout(f)
        self.status = label(f"Last backup: {a.get('last', '').replace('T', ' ') or 'never'}"
                            + (f" - {a['last_result']}" if a.get("last_result") else ""), "hint")
        lay.addWidget(self.status)
        lay.addStretch()
        br = QHBoxLayout()
        for txt, fn in (("Back up now", self._now), ("Save and schedule in Windows", self._schedule),
                        ("Remove schedule", self._unschedule)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            br.addWidget(b)
        br.addStretch()
        b = QPushButton("Close")
        b.clicked.connect(self._close)
        br.addWidget(b)
        lay.addLayout(br)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Backup folder", self.folder.text())
        if d:
            self.folder.setText(d.replace("/", "\\"))

    def _store(self):
        self.settings.setdefault("auto_backup", {}).update(
            folder=self.folder.text().strip(), day=self.day.currentData(), time=self.time.time().toString("HH:mm"),
            keep=self.keep.value(), include_queries=self.queries.isChecked())
        paths.save_settings(self.settings)

    def _now(self):
        from ..backup import run_auto
        self._store()
        try:
            self.status.setText(run_auto(self.settings))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Backup", str(e))

    def _schedule(self):
        from ..backup import schedule_auto
        self._store()
        if not self.folder.text().strip():
            QMessageBox.information(self, "Backup", "Choose a backup folder first.")
            return
        try:
            schedule_auto(self.settings)
            self.status.setText("Scheduled in Windows Task Scheduler.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Schedule", str(e))

    def _unschedule(self):
        from ..scheduler import delete
        self.status.setText(delete("Settings backup"))

    def _close(self):
        self._store()
        self.accept()


# ============================================================================ version history
class HistoryDialog(QDialog):
    def __init__(self, path: str, title: str, parent=None):
        super().__init__(parent)
        from pathlib import Path
        self.path = Path(path)
        self.setWindowTitle(f"Version history - {title}")
        self.resize(980, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Every save keeps the previous copy (the newest 30). Pick one to see what changed since, "
                            "then restore it if you need to.", "subtitle"))
        from PySide6.QtWidgets import QSplitter
        sp = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show)
        sp.addWidget(self.list)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.changes = QTextBrowser()
        self.changes.setMaximumHeight(170)
        rl.addWidget(self.changes)
        self.diff = QPlainTextEdit()
        self.diff.setObjectName("sql")
        self.diff.setReadOnly(True)
        rl.addWidget(self.diff, 1)
        sp.addWidget(right)
        sp.setSizes([300, 680])
        lay.addWidget(sp, 1)
        row = QHBoxLayout()
        self.restore_btn = QPushButton("Restore this version")
        self.restore_btn.setObjectName("primary")
        self.restore_btn.clicked.connect(self._restore)
        row.addWidget(self.restore_btn)
        row.addStretch()
        b = QPushButton("Close")
        b.clicked.connect(self.reject)
        row.addWidget(b)
        lay.addLayout(row)
        self._fill()

    def _fill(self):
        from ..history import versions
        self.vers = versions(self.path)
        self.list.clear()
        for v in self.vers:
            self.list.addItem(f"{v['when']:%m/%d/%Y %I:%M %p}" + (f"  - {v['note']}" if v["note"] else ""))
        self.restore_btn.setEnabled(bool(self.vers))
        if self.vers:
            self.list.setCurrentRow(0)
        else:
            self.changes.setHtml("No earlier versions yet - they appear after the file is saved again.")

    def _show(self, r):
        from ..history import describe_changes, sql_diff
        if not (0 <= r < len(self.vers)):
            return
        old = self.vers[r]["path"]
        if self.path.exists():
            ch = describe_changes(old, self.path)
            self.changes.setHtml("<b>Changed since this version</b><ul>" + "".join(f"<li>{c}</li>" for c in ch)
                                 + "</ul>")
            self.diff.setPlainText(sql_diff(old, self.path) or "(the SQL is the same)")
        else:
            self.changes.setHtml("The current file was deleted or reset - restoring brings this version back.")
            self.diff.setPlainText("")

    def _restore(self):
        from ..history import restore
        r = self.list.currentRow()
        if not (0 <= r < len(self.vers)):
            return
        if QMessageBox.question(self, "Restore", "Replace the current version with this one? (The current one is "
                                                "kept in the history.)") != QMessageBox.Yes:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        restore(self.path, self.vers[r]["path"])
        QMessageBox.information(self, "Restore", "Restored. Reopen the query (or file) to see it.")
        self.accept()


# ============================================================================ where is this field used?
class WhereUsedDialog(QDialog):
    def __init__(self, catalog, settings: dict, parent=None, open_query=None, open_package=None):
        super().__init__(parent)
        self.catalog, self.settings = catalog, settings
        self.open_query, self.open_package = open_query, open_package
        self.setWindowTitle("Where is this field used?")
        self.resize(900, 680)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Pick a SAM table and column to see every export package, saved query and template that "
                            "uses it - and which vendors in use receive it. Handy before changing how data is kept "
                            "in SAM, or when a parent asks who gets their child's data.", "subtitle"))
        row = QHBoxLayout()
        self.table = QComboBox()
        self.table.setEditable(True)
        for t in sorted(catalog.tables, key=str.lower):
            self.table.addItem(t)
        self.table.setCurrentText("Student")
        self.table.currentTextChanged.connect(self._cols)
        row.addWidget(QLabel("Table:"))
        row.addWidget(self.table, 1)
        self.col = QComboBox()
        self.col.setEditable(True)
        row.addWidget(QLabel("Column:"))
        row.addWidget(self.col, 1)
        b = QPushButton("Search")
        b.setObjectName("primary")
        b.clicked.connect(self.search)
        row.addWidget(b)
        lay.addLayout(row)
        from PySide6.QtWidgets import QTreeWidget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Where", "How it's used"])
        self.tree.setColumnWidth(0, 420)
        self.tree.itemDoubleClicked.connect(self._open)
        lay.addWidget(self.tree, 1)
        self.summary = label("")
        lay.addWidget(self.summary)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._cols()
        self.col.setCurrentText("DOB")

    def _cols(self, *_a):
        cur = self.col.currentText()
        self.col.clear()
        t = self.table.currentText()
        self.col.addItems(self.catalog.columns(t) if self.catalog.has_table(t) else [])
        if cur:
            self.col.setCurrentText(cur)

    def search(self):
        from PySide6.QtWidgets import QTreeWidgetItem
        from ..whereused import find
        t, c = self.table.currentText().strip(), self.col.currentText().strip()
        if not t or not c:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = find(t, c, self.settings)
        finally:
            QApplication.restoreOverrideCursor()
        self.tree.clear()

        def section(title, items):
            top = QTreeWidgetItem([f"{title} ({len(items)})", ""])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            return top
        pk = section("Export packages", res["packages"])
        for p in res["packages"]:
            it = QTreeWidgetItem([p["name"] + ("   [in use]" if p["in_use"] else ""), ""])
            it.setData(0, Qt.UserRole, ("package", p["id"]))
            if p["in_use"]:
                it.setForeground(0, qcolor("#B42318"))
            for fl in p["files"]:
                ch = QTreeWidgetItem([fl["file"], ", ".join(fl["how"])])
                ch.setData(0, Qt.UserRole, ("package", p["id"]))
                it.addChild(ch)
            pk.addChild(it)
        qs = section("My saved queries", res["queries"])
        for q in res["queries"]:
            it = QTreeWidgetItem([q["name"], ", ".join(q["how"])])
            it.setData(0, Qt.UserRole, ("query", q["path"]))
            qs.addChild(it)
        ts = section("Templates", res["templates"])
        for q in res["templates"]:
            ts.addChild(QTreeWidgetItem([q["name"], ", ".join(q["how"])]))
        for top in (pk, qs):
            top.setExpanded(True)
        v = res["vendors_in_use"]
        self.summary.setText(f"<b>{t}.{c}</b> goes to <b>{len(v)}</b> vendor(s) you use"
                             + (": " + ", ".join(v) if v else "") + ". Double-click to open.")

    def _open(self, it, _c=None):
        d = it.data(0, Qt.UserRole)
        if not d:
            return
        if d[0] == "query" and self.open_query:
            self.open_query(d[1])
            self.accept()
        elif d[0] == "package" and self.open_package:
            self.open_package(d[1])
            self.accept()


# ============================================================================ data minimization
class MinimizeDialog(QDialog):
    def __init__(self, platform: dict, settings: dict, parent=None):
        super().__init__(parent)
        self.platform, self.settings = platform, settings
        self.setWindowTitle(f"Data minimization - {platform['name']}")
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(label(
            "Sensitive columns this package sends. <b>Needed</b> ones are required by the vendor's layout or link "
            "the files together; <b>optional</b> ones can usually be left out. Tick a column to send it <b>empty</b> "
            "- the column stays, so the file layout doesn't change. This saves a district version of the file "
            "('Reset to standard' undoes it). Check with the vendor first if a feature depends on the data.",
            "subtitle"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Send empty", "File", "Column", "Kind of data", "Vendor layout"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)
        self.status = label("", "hint")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        b = QPushButton("Blank the ticked columns")
        b.setObjectName("primary")
        b.clicked.connect(self._apply)
        row.addWidget(b)
        row.addStretch()
        c = QPushButton("Close")
        c.clicked.connect(self.accept)
        row.addWidget(c)
        lay.addLayout(row)
        self._fill()

    def _fill(self):
        from ..minimize import review
        from ..privacy import LEVELS
        self.rows = review(self.platform, self.settings)
        self.table.setRowCount(0)
        opt = 0
        for r in self.rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            cb = QCheckBox()
            cb.setChecked(r["blanked"])
            cb.setEnabled(not r["blanked"])
            self.table.setCellWidget(i, 0, cb)
            self.table.setItem(i, 1, QTableWidgetItem(r["file"]))
            self.table.setItem(i, 2, QTableWidgetItem(r["heading"] + (f"   ({r['source']})" if r["source"] else "")))
            it = QTableWidgetItem("Sent empty" if r["blanked"] else r["level_name"])
            if not r["blanked"]:
                it.setForeground(qcolor(LEVELS[r["level"]][1]))
            self.table.setItem(i, 3, it)
            self.table.setItem(i, 4, QTableWidgetItem("needed" if r["needed"] else "optional"))
            opt += (not r["needed"] and not r["blanked"])
        self.table.resizeColumnsToContents()
        self.status.setText(f"{len(self.rows)} sensitive column(s); {opt} optional one(s) still sent."
                            if self.rows else "This package sends no sensitive columns.")

    def _apply(self):
        from ..minimize import blank_columns
        picks = {}
        for i, r in enumerate(self.rows):
            cb = self.table.cellWidget(i, 0)
            if cb.isChecked() and not r["blanked"]:
                picks.setdefault(r["file"], set()).add(r["heading"])
        if not picks:
            return
        needed = [f"{f}: {h}" for f, hs in picks.items() for h in hs
                  if next(r for r in self.rows if r["file"] == f and r["heading"] == h)["needed"]]
        if needed and QMessageBox.question(self, "Data minimization", "These columns are NEEDED by the vendor's "
                                           "layout - blanking them may make the vendor reject rows:\n\n"
                                           + "\n".join(needed) + "\n\nBlank them anyway?") != QMessageBox.Yes:
            return
        n = sum(blank_columns(self.platform, self.settings, f, hs) for f, hs in picks.items())
        self.status.setText(f"Blanked {n} column(s) - saved as district versions. Send the vendor a new sample.")
        self._fill()


# ============================================================================ compare with the vendor's side
class ReconcileDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Compare with the vendor's data")
        self.resize(1000, 720)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Compare the file you send (from SAM) with the vendor's own export or error report - "
                            "for example Clever's student export, a Google Admin user list or a vendor's 'not "
                            "synced' report - to find people missing on either side. Nothing is uploaded.",
                            "subtitle"))
        f = QFormLayout()
        self.ours, self.theirs = QLineEdit(), QLineEdit()
        for w, title in ((self.ours, "Your file (from SAM):"), (self.theirs, "Vendor's file:")):
            r = QHBoxLayout()
            r.addWidget(w, 1)
            b = QPushButton("Browse...")
            b.clicked.connect(lambda _=False, e=w: self._browse(e))
            r.addWidget(b)
            f.addRow(title, r)
        self.k1, self.k2 = QComboBox(), QComboBox()
        kr = QHBoxLayout()
        kr.addWidget(self.k1, 1)
        kr.addWidget(QLabel("matches"))
        kr.addWidget(self.k2, 1)
        f.addRow("Match people on:", kr)
        self.f1, self.f2 = QComboBox(), QComboBox()
        fr = QHBoxLayout()
        fr.addWidget(self.f1, 1)
        fr.addWidget(QLabel("vs"))
        fr.addWidget(self.f2, 1)
        f.addRow("Also compare (optional):", fr)
        lay.addLayout(f)
        row = QHBoxLayout()
        b = QPushButton("Compare")
        b.setObjectName("primary")
        b.clicked.connect(self.run)
        row.addWidget(b)
        self.save_btn = QPushButton("Save report (CSV)...")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)
        row.addWidget(self.save_btn)
        row.addStretch()
        lay.addLayout(row)
        self.summary = label("")
        lay.addWidget(self.summary)
        from PySide6.QtWidgets import QTabWidget
        self.tabs = QTabWidget()
        self.t_ours, self.t_theirs, self.t_diff = QTableWidget(), QTableWidget(), QTableWidget()
        for t, name in ((self.t_ours, "In SAM file only"), (self.t_theirs, "At the vendor only"),
                        (self.t_diff, "Different values")):
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.tabs.addTab(t, name)
        lay.addWidget(self.tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.data = None

    def _browse(self, edit):
        fn, _ = QFileDialog.getOpenFileName(self, "Choose a file", edit.text(),
                                            "Data files (*.csv *.txt *.xlsx);;All files (*)")
        if fn:
            edit.setText(fn)
            self._load()

    def _load(self):
        from ..reconcile import read, suggest_keys
        if not (self.ours.text() and self.theirs.text()):
            return
        try:
            h1, r1 = read(self.ours.text())
            h2, r2 = read(self.theirs.text())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Compare", f"Couldn't read a file: {e}")
            return
        self.data = (h1, r1, h2, r2)
        self._loaded_paths = (self.ours.text(), self.theirs.text())
        for cb, h in ((self.k1, h1), (self.k2, h2)):
            cb.clear()
            cb.addItems(h)
        for cb, h in ((self.f1, h1), (self.f2, h2)):
            cb.clear()
            cb.addItem("(nothing)", -1)
            for i, x in enumerate(h):
                cb.addItem(x, i)
        i, j, share = suggest_keys(h1, r1, h2, r2)
        self.k1.setCurrentIndex(i)
        self.k2.setCurrentIndex(j)
        self.summary.setText(f"Suggested match: <b>{h1[i] if h1 else ''}</b> = <b>{h2[j] if h2 else ''}</b> "
                             f"({share:.0%} of your IDs found). Change it if that's not right, then Compare.")

    def _fill(self, table, head, rows):
        table.clear()
        table.setColumnCount(len(head))
        table.setHorizontalHeaderLabels([str(h) for h in head])
        table.setRowCount(min(len(rows), 5000))
        for r, row in enumerate(rows[:5000]):
            for c, v in enumerate(row[:len(head)]):
                table.setItem(r, c, QTableWidgetItem(str(v)))
        table.resizeColumnsToContents()

    def run(self):
        from ..reconcile import compare
        if not self.data or getattr(self, "_loaded_paths", None) != (self.ours.text(), self.theirs.text()):
            self._load()
        if not self.data:
            return
        h1, r1, h2, r2 = self.data
        pairs = [(self.f1.currentData(), self.f2.currentData())] if self.f1.currentData() not in (None, -1) and \
            self.f2.currentData() not in (None, -1) else []
        self.res = compare(h1, r1, h2, r2, self.k1.currentIndex(), self.k2.currentIndex(), pairs)
        res = self.res
        self._fill(self.t_ours, h1, res["only_ours"])
        self._fill(self.t_theirs, h2, res["only_theirs"])
        self._fill(self.t_diff, ["ID", "Field", "SAM file", "Vendor"], [list(x) for x in res["differences"]])
        self.tabs.setTabText(0, f"In SAM file only ({len(res['only_ours']):,})")
        self.tabs.setTabText(1, f"At the vendor only ({len(res['only_theirs']):,})")
        self.tabs.setTabText(2, f"Different values ({len(res['differences']):,})")
        dup = (f" Duplicate IDs: {res['dupes_ours']} in your file, {res['dupes_theirs']} in the vendor's."
               if res["dupes_ours"] or res["dupes_theirs"] else "")
        self.summary.setText(f"<b>{res['matched']:,}</b> matched; <b>{len(res['only_ours']):,}</b> only in your "
                             f"file (not at the vendor - check their sync errors); <b>{len(res['only_theirs']):,}"
                             f"</b> only at the vendor (left the district? accounts to remove).{dup}")
        self.save_btn.setEnabled(True)

    def _save(self):
        from ..reconcile import save_report
        fn, _ = QFileDialog.getSaveFileName(self, "Save comparison", "vendor_comparison.csv", "CSV (*.csv)")
        if fn:
            h1, _r1, h2, _r2 = self.data
            save_report(fn, h1, h2, self.res)
            self.summary.setText(self.summary.text() + f"<br>Saved {fn}")
