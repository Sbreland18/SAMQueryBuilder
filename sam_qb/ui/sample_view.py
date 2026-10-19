"""Results grid: made-up sample data (default), a real CSV file the CAC Agent wrote, or - when the optional
read-only SAM connection is turned on - real rows straight from SAM."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..preview import run_preview

NOTES = {
    "sample": "<b>Sample data preview</b> &nbsp;<span style='color:#9A6700'>Made-up names and values - shows the "
              "shape of your results, not real SAM records.</span>",
    "file": "<b>Your file</b> &nbsp;<span style='color:#1F5FAD'>Rows from a CSV you opened (e.g. what the CAC Agent "
            "wrote last night) compared with this query's columns.</span>",
    "sam": "<b>Real SAM data</b> &nbsp;<span style='color:#B42318'>Read-only results from the SAM database - "
           "contains real student information.</span>",
}


class SampleResults(QWidget):
    def __init__(self, parent=None, get_settings=None):
        super().__init__(parent)
        self.get_settings = get_settings or (lambda: {})
        self.mode = "sample"
        self._query = None
        self._catalog = None
        self._file = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        top = QHBoxLayout()
        self.note = QLabel(NOTES["sample"])
        self.note.setTextFormat(Qt.RichText)
        top.addWidget(self.note, 1)
        self.group = QButtonGroup(self)
        self.btn_sample = QPushButton("Sample data")
        self.btn_file = QPushButton("My CSV file...")
        self.btn_file.setToolTip("Open a CSV the CAC Agent (or SAM) produced and compare it with this query")
        self.btn_sam = QPushButton("Run in SAM (read-only)")
        self.btn_sam.setToolTip("Turned on in Tools > SAM database connection")
        for b, m in ((self.btn_sample, "sample"), (self.btn_file, "file"), (self.btn_sam, "sam")):
            b.setCheckable(True)
            self.group.addButton(b)
            top.addWidget(b)
        self.btn_sample.setChecked(True)
        self.btn_sample.clicked.connect(lambda: self._set_mode("sample"))
        self.btn_file.clicked.connect(self._pick_file)
        self.btn_sam.clicked.connect(lambda: self._set_mode("sam"))
        self.status = QLabel("")
        self.status.setObjectName("hint")
        top.addWidget(self.status)
        lay.addLayout(top)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.RichText)
        self.message.setStyleSheet("color:#4A5568; padding:8px;")
        lay.addWidget(self.message)
        self.grid = QTableWidget(0, 0)
        self.grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grid.setAlternatingRowColors(True)
        self.grid.verticalHeader().setDefaultSectionSize(22)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.grid.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.grid, 1)
        self._update_sam_button()

    # ------------------------------------------------------------------ modes
    def _update_sam_button(self):
        try:
            from ..samdb import enabled
            on = enabled(self.get_settings())
        except Exception:
            on = False
        self.btn_sam.setVisible(on)
        if not on and self.mode == "sam":
            self.mode = "sample"
            self.btn_sample.setChecked(True)

    def _set_mode(self, mode):
        self.mode = mode
        self.note.setText(NOTES[mode])
        if self._query is not None:
            self.show_query(self._query, self._catalog, force=True)

    def _pick_file(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Open a CSV file to compare", self._file,
                                            "CSV / text files (*.csv *.txt);;All files (*)")
        if not fn:
            (self.btn_file if self.mode == "file" else self.btn_sample if self.mode == "sample"
             else self.btn_sam).setChecked(True)
            return
        self._file = fn
        self._set_mode("file")

    # ------------------------------------------------------------------ display
    def show_query(self, query, catalog, force=False):
        self._query, self._catalog = query, catalog
        self._update_sam_button()
        if self.mode == "file" and self._file:
            return self._show_file(query)
        if self.mode == "sam":
            if not force:
                self.status.setText("Query changed - click 'Run in SAM' to refresh")
                return None
            return self._show_sam(query)
        res = run_preview(query, catalog)
        if res.error:
            return self._error(res.error)
        msg = "" if res.rows else ("No sample rows match your filters. That can be normal with made-up data - the "
                                   "real query in SAM may still return rows. Try loosening a filter to check the "
                                   "columns look right.")
        more = f" (showing first {res.shown})" if res.total > res.shown else ""
        self._fill(res.headings, res.rows, f"{res.total} sample row{'s' if res.total != 1 else ''}{more}", msg)

    def _show_file(self, query):
        from pathlib import Path
        from ..filediff import read_csv
        try:
            head, rows = read_csv(self._file)
        except Exception as e:  # noqa: BLE001
            return self._error(f"Could not read {self._file}: {e}")
        want = [c.heading or c.column for c in query.columns]
        missing = [h for h in want if h not in head]
        extra = [h for h in head if h not in want]
        order_ok = [h for h in head if h in want] == [h for h in want if h in head]
        parts = []
        if missing:
            parts.append(f"<span style='color:#B42318'><b>Columns in the query but not the file:</b> "
                         f"{', '.join(missing)}</span>")
        if extra:
            parts.append(f"<span style='color:#9A6700'><b>Columns in the file but not the query:</b> "
                         f"{', '.join(extra)}</span>")
        if not order_ok:
            parts.append("<span style='color:#9A6700'>The column order differs from the query.</span>")
        if not parts:
            parts.append("<span style='color:#1E7B34'>The file's columns match this query.</span>")
        shown = rows[:500]
        self._fill(head, [[r.get(h, "") for h in head] for r in shown],
                   f"{Path(self._file).name}: {len(rows):,} rows" + (" (showing 500)" if len(rows) > 500 else ""),
                   "<br>".join(parts), always_msg=True)

    def _show_sam(self, query):
        from ..query_model import generate_sql
        from .. import samdb
        try:
            res = samdb.run(self.get_settings(), generate_sql(query, header=False))
        except Exception as e:  # noqa: BLE001
            return self._error(f"Could not run the query in SAM: {e}")
        tot = res["total"]
        st = (f"{tot:,} rows in SAM" if tot >= 0 else "many rows in SAM") + \
            (f" (showing first {len(res['rows'])})" if res["truncated"] else "")
        self._fill(res["headings"], res["rows"], st, "" if res["rows"] else "The query returned no rows in SAM.")

    def _error(self, text):
        self.grid.setVisible(False)
        self.message.setVisible(True)
        self.message.setText(text)
        self.status.setText("")

    def _fill(self, headings, rows, status, msg="", always_msg=False):
        self.message.setVisible(bool(msg))
        self.message.setText(msg)
        self.grid.setVisible(True)
        self.grid.setSortingEnabled(False)
        self.grid.clear()
        self.grid.setColumnCount(len(headings))
        self.grid.setHorizontalHeaderLabels([str(h) for h in headings])
        self.grid.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                txt = "" if v is None else (f"{v:g}" if isinstance(v, float) else str(v))
                it = QTableWidgetItem(txt)
                if v is None:
                    it.setText("NULL")
                    it.setForeground(Qt.gray)
                if isinstance(v, (int, float)):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.grid.setItem(r, c, it)
        self.grid.resizeColumnsToContents()
        for c in range(self.grid.columnCount()):
            if self.grid.columnWidth(c) > 260:
                self.grid.setColumnWidth(c, 260)
        try:
            from ..dupcheck import repeated_keys
            col, dup = repeated_keys(list(headings), rows)
            if dup:
                status += f"  -  {dup:,} repeated {col} value(s): some records appear more than once"
        except Exception:
            pass
        self.status.setText(status)
