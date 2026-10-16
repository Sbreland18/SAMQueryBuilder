"""The six builder steps (mirrors SAM Report Builder's flow)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMenu,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter,
                               QTableWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
                               QRadioButton, QButtonGroup)

from ..query_model import (FORMATS, JOIN_TYPES, OPERATORS, Condition, FilterGroup, Link, OutColumn, Part,
                           SortItem, column_expr, from_sql, generate_sql, validate)
from ..catalog_builder import split_camel
from .widgets import ColumnPicker, FormatListEditor, SqlHighlighter, hline, label, list_item


class Ctx:
    """query = the part being edited; root = the whole saved query (differs only for UNION parts)."""

    def __init__(self, catalog, query):
        self.catalog = catalog
        self.query = query
        self.root = query
        self.settings = {}


class Step(QWidget):
    changed = Signal()
    title = ""
    intro = ""

    def __init__(self, ctx: Ctx):
        super().__init__()
        self.ctx = ctx
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(16, 12, 16, 8)
        self.outer.addWidget(label(self.title, "stepTitle"))
        if self.intro:
            self.outer.addWidget(label(self.intro, "hint"))

    @property
    def q(self):
        return self.ctx.query

    @property
    def cat(self):
        return self.ctx.catalog

    def refresh(self):
        pass

    def emit(self):
        self.changed.emit()


# =============================================================================== Step 1
class TablesStep(Step):
    title = "Step 1 - Choose tables and columns"
    intro = ("Find a table on the left (search by table or column name), then double-click columns to add them. "
             "Adding a column adds its table automatically. Right-click a table for more options.")

    def __init__(self, ctx):
        super().__init__(ctx)
        split = QSplitter(Qt.Horizontal)
        self.outer.addWidget(split, 1)

        # ---- left: table browser
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tables or columns (e.g. homeroom, LastName, attendance)...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.fill_tree)
        ll.addWidget(self.search)
        self.show_hidden = QCheckBox("Show backup / audit / system copies")
        self.show_hidden.toggled.connect(self.fill_tree)
        ll.addWidget(self.show_hidden)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._table_selected)
        self.tree.itemDoubleClicked.connect(self._tree_double)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        ll.addWidget(self.tree, 1)
        split.addWidget(left)

        # ---- middle: columns of selected table
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        self.tinfo = label("Select a table to see its columns.", "hint")
        ml.addWidget(self.tinfo)
        self.col_filter = QLineEdit()
        self.col_filter.setPlaceholderText("Filter columns...")
        self.col_filter.setClearButtonEnabled(True)
        self.col_filter.textChanged.connect(self._fill_columns)
        ml.addWidget(self.col_filter)
        self.cols = QListWidget()
        self.cols.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.cols.itemDoubleClicked.connect(lambda it: self._add_columns([it]))
        ml.addWidget(self.cols, 1)
        row = QHBoxLayout()
        b = QPushButton("Add selected columns  >")
        b.setObjectName("primary")
        b.clicked.connect(lambda: self._add_columns(self.cols.selectedItems()))
        row.addWidget(b)
        b2 = QPushButton("Add table only")
        b2.clicked.connect(self._add_table_only)
        row.addWidget(b2)
        ml.addLayout(row)
        split.addWidget(mid)

        # ---- right: query contents
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        g1 = QGroupBox("Tables in this query")
        g1l = QVBoxLayout(g1)
        self.qtables = QListWidget()
        self.qtables.setMaximumHeight(150)
        g1l.addWidget(self.qtables)
        rb = QPushButton("Remove table (and its columns)")
        rb.clicked.connect(self._remove_table)
        g1l.addWidget(rb)
        rl.addWidget(g1)
        g2 = QGroupBox("Columns that will show (in order)")
        g2l = QVBoxLayout(g2)
        self.qcols = QListWidget()
        self.qcols.setSelectionMode(QAbstractItemView.ExtendedSelection)
        g2l.addWidget(self.qcols, 1)
        r2 = QHBoxLayout()
        for txt, fn in (("Up", lambda: self._move(-1)), ("Down", lambda: self._move(1)), ("Remove", self._remove_cols)):
            bb = QPushButton(txt)
            bb.clicked.connect(fn)
            r2.addWidget(bb)
        g2l.addLayout(r2)
        rl.addWidget(g2, 1)
        split.addWidget(right)
        split.setSizes([330, 300, 340])
        self.current_table = None
        self.fill_tree()

    # ---------------------------------------------------------------- tree
    def fill_tree(self):
        self.tree.clear()
        hidden = self.show_hidden.isChecked()
        text = self.search.text().strip()
        if text:
            matches = self.cat.search(text, hidden)
            by_table: dict[str, list[str]] = {}
            for t, c in matches:
                by_table.setdefault(t, [])
                if c:
                    by_table[t].append(c)
            # common tables first, then by number of hits
            order = sorted(by_table, key=lambda t: (not self.cat.tables[t].get("common"), -len(by_table[t]), t.lower()))
            for t in order[:400]:
                it = self._table_item(t)
                if by_table[t]:
                    it.setText(0, it.text(0) + f"   - matches: {', '.join(by_table[t][:4])}"
                               + ("..." if len(by_table[t]) > 4 else ""))
                self.tree.addTopLevelItem(it)
            if not order:
                self.tree.addTopLevelItem(QTreeWidgetItem(["No tables or columns match."]))
            else:
                self.tree.setCurrentItem(self.tree.topLevelItem(0))
            return
        common = QTreeWidgetItem(["Most used tables"])
        f = common.font(0)
        f.setBold(True)
        common.setFont(0, f)
        for t in self.cat.common_tables:
            common.addChild(self._table_item(t))
        self.tree.addTopLevelItem(common)
        common.setExpanded(True)
        for cat, tables in self.cat.categories(hidden).items():
            ci = QTreeWidgetItem([f"{cat}  ({len(tables)})"])
            ci.setFont(0, f)
            for t in tables:
                ci.addChild(self._table_item(t))
            self.tree.addTopLevelItem(ci)

    def _table_item(self, t):
        info = self.cat.tables.get(t, {})
        fr = info.get("friendly", t)
        txt = t if fr.replace(" ", "").lower() == t.lower() else f"{fr}  [{t}]"
        it = QTreeWidgetItem([txt])
        it.setData(0, Qt.UserRole, t)
        tip = info.get("description") or f"{len(info.get('columns', []))} columns"
        it.setToolTip(0, f"<b>{t}</b><br>{tip}")
        return it

    def _table_selected(self, cur, _prev=None):
        t = cur.data(0, Qt.UserRole) if cur else None
        if not t:
            return
        self.current_table = t
        info = self.cat.tables[t]
        desc = info.get("description") or ""
        self.tinfo.setText(f"<b>{info.get('friendly', t)}</b> &nbsp;<span style='color:#666'>({t}, "
                           f"{len(info['columns'])} columns)</span><br>{desc}")
        text = self.search.text().strip().lower()
        self.col_filter.blockSignals(True)
        self.col_filter.setText(self.search.text().strip()
                                if text and any(text in c.lower() for c in info["columns"]) else "")
        self.col_filter.blockSignals(False)
        self._fill_columns()

    def _fill_columns(self):
        self.cols.clear()
        t = self.current_table
        if not t:
            return
        flt = self.col_filter.text().lower().strip()
        for c in self.cat.columns(t):
            if flt and flt not in c.lower():
                continue
            note = self.cat.column_note(t, c)
            txt = c + ("   (sensitive)" if self.cat.is_sensitive(c) else "")
            self.cols.addItem(list_item(txt, c, note or f"{t}.{c}"))

    def _tree_double(self, it, _col):
        t = it.data(0, Qt.UserRole)
        if t:
            self._ensure_table(t)

    def _tree_menu(self, pos):
        it = self.tree.itemAt(pos)
        t = it.data(0, Qt.UserRole) if it else None
        if not t:
            return
        m = QMenu(self)
        m.addAction("Add table to query", lambda: self._ensure_table(t))
        m.addAction("Add another copy of this table (e.g. Employee as Counselor)", lambda: self._ensure_table(t, True))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ---------------------------------------------------------------- actions
    def _ensure_table(self, t, force_new=False):
        alias = self.q.add_table(t, force_new)
        self.refresh()
        self.emit()
        return alias

    def _add_table_only(self):
        if self.current_table:
            self._ensure_table(self.current_table)

    def _target_alias(self, table):
        """If several copies of the table exist, use the one selected in 'Tables in this query'."""
        copies = [t.alias for t in self.q.tables if t.table == table]
        sel = self.qtables.currentItem()
        if sel and sel.data(Qt.UserRole) in copies:
            return sel.data(Qt.UserRole)
        return copies[0] if copies else self.q.add_table(table)

    def _add_columns(self, items):
        t = self.current_table
        if not t or not items:
            return
        alias = self._target_alias(t)
        for it in items:
            c = it.data(Qt.UserRole)
            if any(oc.kind == "field" and oc.alias == alias and oc.column == c for oc in self.q.columns):
                continue
            nice = split_camel(c) or c
            base = nice if alias == t else f"{alias} {nice}"
            self.q.columns.append(OutColumn("field", alias, c, self.q.unique_heading(base)))
        self.refresh()
        self.emit()

    def _remove_table(self):
        it = self.qtables.currentItem()
        if not it:
            return
        alias = it.data(Qt.UserRole)
        if QMessageBox.question(self, "Remove table", f"Remove {alias} and every column, link and filter that uses it?") \
                != QMessageBox.Yes:
            return
        self.q.remove_alias(alias)
        self.refresh()
        self.emit()

    def _remove_cols(self):
        rows = sorted({self.qcols.row(i) for i in self.qcols.selectedItems()}, reverse=True)
        for r in rows:
            h = self.q.columns[r].heading
            del self.q.columns[r]
            self.q.sort = [s for s in self.q.sort if s.heading != h]
        self.refresh()
        self.emit()

    def _move(self, d):
        r = self.qcols.currentRow()
        n = r + d
        if 0 <= r < len(self.q.columns) and 0 <= n < len(self.q.columns):
            self.q.columns[r], self.q.columns[n] = self.q.columns[n], self.q.columns[r]
            self.refresh()
            self.qcols.setCurrentRow(n)
            self.emit()

    def refresh(self):
        self.qtables.clear()
        for t in self.q.tables:
            txt = t.table if t.alias == t.table else f"{t.alias}  (copy of {t.table})"
            self.qtables.addItem(list_item(txt, t.alias, self.cat.description(t.table)))
        self.qcols.clear()
        for c in self.q.columns:
            src = f"{c.alias}.{c.column}" if c.kind == "field" else ("SQL expression" if c.kind == "raw"
                                                                     else "custom column")
            self.qcols.addItem(list_item(f"{c.heading}    <- {src}", None, column_expr(c)))


# =============================================================================== Step 2
class LinksStep(Step):
    title = "Step 2 - Link the tables"
    intro = ("Every table must be connected to the others. Click 'Suggest links' and the builder will find the "
             "usual SAM links for you (it may add in-between tables such as Schedule Roster). "
             "Inner Link is the most common choice.")

    def __init__(self, ctx):
        super().__init__(ctx)
        info = QFrame()
        info.setObjectName("infobar")
        il = QVBoxLayout(info)
        il.addWidget(label("<br>".join(f"<b>{v[0]}</b> - {v[2]}" for v in JOIN_TYPES.values())))
        self.outer.addWidget(info)
        row = QHBoxLayout()
        b = QPushButton("Suggest links")
        b.setObjectName("primary")
        b.clicked.connect(self.suggest)
        row.addWidget(b)
        b2 = QPushButton("Add link manually")
        b2.clicked.connect(self.add_link)
        row.addWidget(b2)
        b3 = QPushButton("Remove selected link")
        b3.clicked.connect(self.remove_link)
        row.addWidget(b3)
        b4 = QPushButton("Clear all links")
        b4.clicked.connect(self.clear_links)
        row.addWidget(b4)
        row.addStretch()
        self.outer.addLayout(row)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Left table", "Left column", "Link type", "Right table", "Right column",
                                              "Extra conditions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.outer.addWidget(self.table, 1)
        self.status = label("")
        self.outer.addWidget(self.status)
        self.note = label("", "hint")
        self.outer.addWidget(self.note)

    def suggest(self, quiet=False):
        if len(self.q.tables) < 2:
            if not quiet:
                QMessageBox.information(self, "Suggest links", "Only one table is in the query, so no links are needed.")
            return
        _, added, problems = self.cat.suggest_links(self.q, add_tables=True)
        msg = []
        if added:
            msg.append("Added in-between table(s) so everything connects: " + ", ".join(added) + ".")
        msg += problems
        self.note.setText(" ".join(msg))
        self.refresh()
        self.emit()

    def add_link(self):
        if len(self.q.tables) < 2:
            QMessageBox.information(self, "Add link", "Add at least two tables in Step 1 first.")
            return
        a, b = self.q.tables[0].alias, self.q.tables[1].alias
        self.q.links.append(Link(a, "", b, "", "INNER"))
        self.refresh()
        self.emit()

    def remove_link(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.q.links):
            del self.q.links[r]
            self.refresh()
            self.emit()

    def clear_links(self):
        self.q.links.clear()
        self.note.setText("")
        self.refresh()
        self.emit()

    def _alias_combo(self, cur):
        cb = QComboBox()
        for t in self.q.tables:
            cb.addItem(t.alias)
        cb.setCurrentText(cur)
        return cb

    def _col_combo(self, alias, cur):
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItem("")
        cols = self.cat.columns(self.q.alias_table(alias) or "")
        # put ID-looking columns first
        for c in sorted(cols, key=lambda c: (not c.lower().endswith("id"), cols.index(c))):
            cb.addItem(c)
        cb.setCurrentText(cur)
        return cb

    def refresh(self):
        self.table.setRowCount(0)
        for i, l in enumerate(self.q.links):
            self.table.insertRow(i)
            la = self._alias_combo(l.left_alias)
            lc = self._col_combo(l.left_alias, l.left_col)
            jt = QComboBox()
            for k, v in JOIN_TYPES.items():
                jt.addItem(v[0], k)
                jt.setItemData(jt.count() - 1, v[2], Qt.ToolTipRole)
            jt.setCurrentIndex(list(JOIN_TYPES).index(l.join))
            ra = self._alias_combo(l.right_alias)
            rc = self._col_combo(l.right_alias, l.right_col)
            xb = QPushButton(self._extra_text(l))
            xb.setToolTip("Extra conditions for this link (added to the ON clause), e.g. OwnerType = the Contact "
                          "code, or PrimaryPhone = 1. Use these instead of Step 4 filters with Left links so rows "
                          "without a match are kept.")
            xb.clicked.connect(lambda _=False, l=l: self._edit_extra(l))
            for col, w in enumerate((la, lc, jt, ra, rc, xb)):
                self.table.setCellWidget(i, col, w)
            la.currentTextChanged.connect(lambda v, l=l, i=i: self._set(l, "left_alias", v, i))
            ra.currentTextChanged.connect(lambda v, l=l, i=i: self._set(l, "right_alias", v, i))
            lc.currentTextChanged.connect(lambda v, l=l: self._set(l, "left_col", v))
            rc.currentTextChanged.connect(lambda v, l=l: self._set(l, "right_col", v))
            jt.currentIndexChanged.connect(lambda _x, l=l, jt=jt: self._set(l, "join", jt.currentData()))
        self._status()

    @staticmethod
    def _extra_text(l):
        n = len([c for c in l.conditions if c.column])
        return f"{n} condition{'s' if n != 1 else ''}..." if n else "Add..."

    def _edit_extra(self, link):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Extra conditions: {link.left_alias} - {link.right_alias}")
        dlg.resize(820, 320)
        lay = QVBoxLayout(dlg)
        lay.addWidget(label("These conditions are added to the link itself (the ON clause). All of them must be "
                            "true. With a Left link, rows that don't match still appear with blanks.", "hint"))
        grp = FilterGroup("ALL", link.conditions)
        box = GroupBox(grp, self.ctx, 1)
        box.setTitle("Conditions")
        box.match.setEnabled(False)
        for b in box.findChildren(QPushButton):
            if b.text() == "Remove group":
                b.setVisible(False)
        lay.addWidget(box)
        lay.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.accept)
        lay.addWidget(bb)
        dlg.exec()
        link.conditions = [c for c in grp.conditions if c.column]
        self.refresh()
        self.emit()

    def _set(self, link, attr, value, row=None):
        setattr(link, attr, value)
        if attr in ("left_alias", "right_alias") and row is not None:
            col = 1 if attr == "left_alias" else 4
            cb = self._col_combo(value, "")
            cb.currentTextChanged.connect(lambda v, l=link, a=("left_col" if col == 1 else "right_col"): self._set(l, a, v))
            self.table.setCellWidget(row, col, cb)
            setattr(link, "left_col" if col == 1 else "right_col", "")
        self._status()
        self.emit()

    def _status(self):
        if len(self.q.tables) < 2:
            self.status.setObjectName("ok")
            self.status.setText("Only one table - no links needed.")
        else:
            _, unreachable = from_sql(self.q)
            if unreachable:
                self.status.setObjectName("bad")
                self.status.setText("Not connected yet: " + ", ".join(unreachable) + ". Click 'Suggest links'.")
            else:
                self.status.setObjectName("ok")
                self.status.setText("All tables are connected.")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


# =============================================================================== Step 3
class FormatStep(Step):
    title = "Step 3 - Format columns"
    intro = ("Rename column headings and add formats (e.g. remove leading zeros, lower case, dates). "
             "Use 'Add custom column' to combine several columns and text into one, such as a username or email.")

    def __init__(self, ctx):
        super().__init__(ctx)
        split = QSplitter(Qt.Horizontal)
        self.outer.addWidget(split, 1)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._select)
        ll.addWidget(self.list, 1)
        b = QPushButton("Add custom column")
        b.clicked.connect(self._add_custom)
        ll.addWidget(b)
        b2 = QPushButton("Add a row count (how many)")
        b2.setToolTip("Adds a 'Count' column; the other columns become the groups (e.g. count per grade).")
        b2.clicked.connect(self._add_count)
        ll.addWidget(b2)
        split.addWidget(left)

        self.editor = QWidget()
        el = QVBoxLayout(self.editor)
        el.setContentsMargins(0, 0, 0, 0)
        hr = QHBoxLayout()
        hr.addWidget(QLabel("Column heading:"))
        self.heading = QLineEdit()
        self.heading.editingFinished.connect(self._heading)
        hr.addWidget(self.heading, 1)
        hr.addWidget(QLabel("Summarize:"))
        self.agg = QComboBox()
        from ..query_model import AGGREGATES
        for k, v in AGGREGATES.items():
            self.agg.addItem(v, k)
        self.agg.setToolTip("Pick Count/Total/Average to summarize rows. Columns left on 'Show each value' "
                            "become the groups (e.g. Grade + Count of rows = students per grade).")
        self.agg.currentIndexChanged.connect(self._agg)
        hr.addWidget(self.agg)
        el.addLayout(hr)
        self.source = label("", "hint")
        el.addWidget(self.source)
        self.raw_box = QGroupBox("SQL expression (exact T-SQL, e.g. CASE WHEN ... END)")
        rbl = QVBoxLayout(self.raw_box)
        self.raw_edit = QPlainTextEdit()
        self.raw_edit.setObjectName("sql")
        self.raw_edit.setMaximumHeight(90)
        self.raw_edit.textChanged.connect(self._raw_changed)
        rbl.addWidget(self.raw_edit)
        el.addWidget(self.raw_box)

        # custom column parts
        self.parts_box = QGroupBox("Pieces of the custom column (joined together in order)")
        pl = QVBoxLayout(self.parts_box)
        self.parts = QListWidget()
        self.parts.setMaximumHeight(140)
        self.parts.currentRowChanged.connect(self._select_part)
        pl.addWidget(self.parts)
        pr = QHBoxLayout()
        self.part_picker = ColumnPicker()
        pr.addWidget(self.part_picker, 1)
        b1 = QPushButton("Add column piece")
        b1.clicked.connect(self._add_part_field)
        pr.addWidget(b1)
        pl.addLayout(pr)
        pr2 = QHBoxLayout()
        self.part_text = QLineEdit()
        self.part_text.setPlaceholderText("Text, e.g. @district.k12.ms.us or ', '")
        pr2.addWidget(self.part_text, 1)
        b2 = QPushButton("Add text piece")
        b2.clicked.connect(self._add_part_text)
        pr2.addWidget(b2)
        pl.addLayout(pr2)
        pr3 = QHBoxLayout()
        for txt, fn in (("Up", lambda: self._move_part(-1)), ("Down", lambda: self._move_part(1)),
                        ("Remove piece", self._remove_part)):
            bb = QPushButton(txt)
            bb.clicked.connect(fn)
            pr3.addWidget(bb)
        pr3.addStretch()
        pl.addLayout(pr3)
        self.part_fmt_box = QGroupBox("Formats for the selected piece")
        pfl = QVBoxLayout(self.part_fmt_box)
        self.part_fmt = FormatListEditor()
        self.part_fmt.changed.connect(self._fmt_changed)
        pfl.addWidget(self.part_fmt)
        pl.addWidget(self.part_fmt_box)
        el.addWidget(self.parts_box)

        self.fmt_box = QGroupBox("Formats for the whole column")
        fl = QVBoxLayout(self.fmt_box)
        self.fmt = FormatListEditor()
        self.fmt.changed.connect(self._fmt_changed)
        fl.addWidget(self.fmt)
        el.addWidget(self.fmt_box)
        self.expr = QPlainTextEdit()
        self.expr.setObjectName("sql")
        self.expr.setReadOnly(True)
        self.expr.setMaximumHeight(80)
        SqlHighlighter(self.expr.document())
        el.addWidget(QLabel("Resulting SQL for this column:"))
        el.addWidget(self.expr)
        el.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor)
        split.addWidget(scroll)
        split.setSizes([280, 700])
        self.editor.setEnabled(False)

    def refresh(self):
        r = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for c in self.q.columns:
            self.list.addItem(c.heading + ("   (custom)" if c.kind == "custom" else ""))
        self.list.blockSignals(False)
        self.part_picker.populate(self.q, self.cat)
        if self.q.columns:
            self.list.setCurrentRow(max(0, min(r, len(self.q.columns) - 1)))
            self._select(self.list.currentRow())
        else:
            self.editor.setEnabled(False)

    def _col(self):
        r = self.list.currentRow()
        return self.q.columns[r] if 0 <= r < len(self.q.columns) else None

    def _select(self, r):
        c = self._col()
        self.editor.setEnabled(c is not None)
        if not c:
            return
        self.heading.setText(c.heading)
        self.agg.blockSignals(True)
        self.agg.setCurrentIndex(max(0, self.agg.findData(c.agg)))
        self.agg.blockSignals(False)
        custom = c.kind == "custom"
        self.raw_box.setVisible(c.kind == "raw")
        if c.kind == "raw" and self.raw_edit.toPlainText() != c.column:
            self.raw_edit.blockSignals(True)
            self.raw_edit.setPlainText(c.column)
            self.raw_edit.blockSignals(False)
        self.parts_box.setVisible(custom)
        self.source.setText("SQL expression" if c.kind == "raw" else "Custom column" if custom else
                            f"Source: {c.alias}.{c.column}. " + (self.cat.column_note(self.q.alias_table(c.alias) or "", c.column)))
        self.fmt.set_formats(c.formats)
        if custom:
            self._fill_parts()
        self._update_expr()

    def _fill_parts(self, keep=None):
        c = self._col()
        self.parts.blockSignals(True)
        self.parts.clear()
        for p in c.parts:
            self.parts.addItem(f"Column  {p.alias}.{p.column}" + (f"  [{len(p.formats)} format(s)]" if p.formats else "")
                               if p.kind == "field" else (f"SQL  {p.value[:60]}..." if p.kind == "sql" and len(p.value) > 60
                                                          else f"SQL  {p.value}" if p.kind == "sql"
                                                          else f"Text  \"{p.value}\""))
        self.parts.blockSignals(False)
        if keep is not None and 0 <= keep < len(c.parts):
            self.parts.setCurrentRow(keep)
        self._select_part(self.parts.currentRow())

    def _select_part(self, r):
        c = self._col()
        p = c.parts[r] if c and 0 <= r < len(c.parts) else None
        self.part_fmt_box.setEnabled(bool(p and p.kind == "field"))
        self.part_fmt.set_formats(p.formats if p and p.kind == "field" else [])

    def _heading(self):
        c = self._col()
        if not c:
            return
        new = self.heading.text().strip() or c.column or "Column"
        if new == c.heading:
            return
        new = self.q.unique_heading(new, ignore=c)
        for s in self.q.sort:
            if s.heading == c.heading:
                s.heading = new
        c.heading = new
        self.heading.setText(new)
        self.list.currentItem().setText(new + ("   (custom)" if c.kind == "custom" else ""))
        self._update_expr()
        self.emit()

    def _raw_changed(self):
        c = self._col()
        if c and c.kind == "raw":
            c.column = self.raw_edit.toPlainText().strip()
            self._update_expr()
            self.emit()

    def _agg(self):
        c = self._col()
        if c:
            c.agg = self.agg.currentData() or ""
            self._update_expr()
            self.emit()

    def _add_count(self):
        h = self.q.unique_heading("Count")
        self.q.columns.append(OutColumn("custom", heading=h, agg="count"))
        self.refresh()
        self.list.setCurrentRow(len(self.q.columns) - 1)
        self.emit()

    def _add_custom(self):
        h = self.q.unique_heading("Custom Column")
        self.q.columns.append(OutColumn("custom", heading=h))
        self.refresh()
        self.list.setCurrentRow(len(self.q.columns) - 1)
        self.emit()

    def _add_part_field(self):
        c = self._col()
        a, col = self.part_picker.value()
        if c and a:
            c.parts.append(Part("field", a, col))
            self._fill_parts(len(c.parts) - 1)
            self._fmt_changed()

    def _add_part_text(self):
        c = self._col()
        if c and self.part_text.text() != "":
            c.parts.append(Part("text", value=self.part_text.text()))
            self.part_text.clear()
            self._fill_parts(len(c.parts) - 1)
            self._fmt_changed()

    def _remove_part(self):
        c = self._col()
        r = self.parts.currentRow()
        if c and 0 <= r < len(c.parts):
            del c.parts[r]
            self._fill_parts(min(r, len(c.parts) - 1))
            self._fmt_changed()

    def _move_part(self, d):
        c = self._col()
        r = self.parts.currentRow()
        n = r + d
        if c and 0 <= r < len(c.parts) and 0 <= n < len(c.parts):
            c.parts[r], c.parts[n] = c.parts[n], c.parts[r]
            self._fill_parts(n)
            self._fmt_changed()

    def _fmt_changed(self):
        c = self._col()
        if c and c.kind == "custom":
            r = self.parts.currentRow()
            if 0 <= r < len(c.parts) and c.parts[r].kind == "field":
                p = c.parts[r]
                self.parts.item(r).setText(f"Column  {p.alias}.{p.column}" +
                                           (f"  [{len(p.formats)} format(s)]" if p.formats else ""))
        self._update_expr()
        self.emit()

    def _update_expr(self):
        c = self._col()
        from ..query_model import agg_sql
        self.expr.setPlainText(agg_sql(c, column_expr(c)) if c else "")


# =============================================================================== Step 4
class ConditionRow(QWidget):
    removed = Signal(object)
    changed = Signal()

    def __init__(self, cond: Condition, ctx: Ctx):
        super().__init__()
        self.cond = cond
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.picker = ColumnPicker()
        self.picker.populate(ctx.query, ctx.catalog, (cond.alias, cond.column))
        self.picker.currentIndexChanged.connect(self._col)
        lay.addWidget(self.picker, 3)
        self.op = QComboBox()
        for k, (lbl, _n) in OPERATORS.items():
            self.op.addItem(lbl, k)
        self.op.setCurrentIndex(list(OPERATORS).index(cond.op) if cond.op in OPERATORS else 0)
        self.op.currentIndexChanged.connect(self._op)
        lay.addWidget(self.op, 2)
        self.ctx = ctx
        self.v1 = QLineEdit(cond.value)
        self.v1.textChanged.connect(self._vals)
        lay.addWidget(self.v1, 2)
        from PySide6.QtWidgets import QToolButton
        self.pick = QToolButton()
        self.pick.setText("Choose...")
        self.pick.setToolTip("Pick from your district's codes (File > SAM Codes & Schools)")
        self.pick.clicked.connect(self._choose)
        lay.addWidget(self.pick)
        self.and_lbl = QLabel("and")
        lay.addWidget(self.and_lbl)
        self.v2 = QLineEdit(cond.value2)
        self.v2.textChanged.connect(self._vals)
        lay.addWidget(self.v2, 2)
        rm = QPushButton("-")
        rm.setToolTip("Remove this condition")
        rm.setFixedWidth(30)
        rm.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(rm)
        self._visibility()

    def _col(self):
        self.cond.alias, self.cond.column = self.picker.value()
        self._visibility()
        self.changed.emit()

    def _code_set(self):
        from ..codes import code_set_for
        t = self.ctx.query.alias_table(self.cond.alias) if self.cond.alias else None
        return code_set_for(t, self.cond.column) if t else None

    def _choose(self):
        from ..codes import options
        from PySide6.QtWidgets import QMenu
        cs = self._code_set()
        opts = options(self.ctx.settings, cs) if cs else []
        if not opts:
            QMessageBox.information(self, "Choose a value",
                                    "No codes are loaded for this column yet. Use File > SAM Codes & Schools to add "
                                    "your schools or import your code lists.")
            return
        multi = self.cond.op in ("in", "not_in")
        current = {x.strip() for x in self.v1.text().split(",") if x.strip()}
        from .widgets import choose_codes
        picked = choose_codes(self, "Choose values" if multi else "Choose a value", opts, current, multi)
        if picked is not None:
            self.v1.setText(", ".join(picked))

    def _op(self):
        self.cond.op = self.op.currentData()
        self._visibility()
        self.changed.emit()

    def _vals(self):
        self.cond.value, self.cond.value2 = self.v1.text(), self.v2.text()
        self.changed.emit()

    def _visibility(self):
        n = OPERATORS[self.cond.op][1]
        self.v1.setVisible(n >= 1)
        self.v2.setVisible(n == 2)
        self.and_lbl.setVisible(n == 2)
        ph = {"in": "e.g. 09, 10, 11", "not_in": "e.g. 09, 10, 11", "last_days": "number of days",
              "raw": "e.g. Student.ADAGrade IN ('11','12')", "contains": "text"}.get(self.cond.op, "value")
        self.v1.setPlaceholderText(ph)
        self.pick.setVisible(n >= 1 and self.cond.op in ("eq", "ne", "in", "not_in") and bool(self._code_set()))


class GroupBox(QGroupBox):
    removed = Signal(object)
    changed = Signal()

    def __init__(self, group: FilterGroup, ctx: Ctx, index: int):
        super().__init__(f"Filter group {index}")
        self.group, self.ctx = group, ctx
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Rows must match"))
        self.match = QComboBox()
        self.match.addItem("ALL of these (AND)", "ALL")
        self.match.addItem("ANY of these (OR)", "ANY")
        self.match.setCurrentIndex(0 if group.match == "ALL" else 1)
        self.match.currentIndexChanged.connect(self._match)
        top.addWidget(self.match)
        top.addStretch()
        rm = QPushButton("Remove group")
        rm.clicked.connect(lambda: self.removed.emit(self))
        top.addWidget(rm)
        lay.addLayout(top)
        self.rows = QVBoxLayout()
        lay.addLayout(self.rows)
        for c in group.conditions:
            self._add_row(c)
        add = QPushButton("+ Add condition")
        add.clicked.connect(self._new)
        lay.addWidget(add, 0, Qt.AlignLeft)

    def _match(self):
        self.group.match = self.match.currentData()
        self.changed.emit()

    def _add_row(self, c):
        row = ConditionRow(c, self.ctx)
        row.changed.connect(self.changed)
        row.removed.connect(self._remove_row)
        self.rows.addWidget(row)

    def _new(self):
        c = Condition()
        self.group.conditions.append(c)
        self._add_row(c)
        self.changed.emit()

    def _remove_row(self, row):
        self.group.conditions.remove(row.cond)
        row.setParent(None)
        row.deleteLater()
        self.changed.emit()


class FiltersStep(Step):
    title = "Step 4 - Filters (which rows to include)"
    intro = ("Add conditions to limit the rows. Conditions in a group can be ALL (AND) or ANY (OR); "
             "groups are then combined. Example: Last Name starts with A  OR  starts with B, AND Gender = M. "
             "Values are compared exactly as stored in SAM (codes, not descriptions).")

    def __init__(self, ctx):
        super().__init__(ctx)
        top = QHBoxLayout()
        top.addWidget(QLabel("Combine groups using:"))
        self.mode = QComboBox()
        self.mode.addItem("ALL groups must match (AND)", "ALL")
        self.mode.addItem("ANY group may match (OR)", "ANY")
        self.mode.currentIndexChanged.connect(self._mode)
        top.addWidget(self.mode)
        top.addStretch()
        add = QPushButton("+ Add filter group")
        add.setObjectName("primary")
        add.clicked.connect(self._add_group)
        top.addWidget(add)
        self.outer.addLayout(top)
        quick = QHBoxLayout()
        quick.addWidget(QLabel("<b>Quick filters:</b>"))
        self.qs = QPushButton("Schools...")
        self.qs.setToolTip("Limit to one or more of your schools (add them in File > SAM Codes & Schools)")
        self.qs.clicked.connect(lambda: self._quick("schools"))
        quick.addWidget(self.qs)
        self.qg = QPushButton("Grades...")
        self.qg.clicked.connect(lambda: self._quick("grade"))
        quick.addWidget(self.qg)
        self.qe = QPushButton("Enrolled only")
        self.qe.setToolTip("Uses the Enrolled status code(s) from District Settings")
        self.qe.clicked.connect(self._quick_enrolled)
        quick.addWidget(self.qe)
        self.quick_note = label("", "hint")
        quick.addWidget(self.quick_note, 1)
        self.outer.addLayout(quick)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.outer.addWidget(self.scroll, 1)

    def refresh(self):
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(0 if self.q.filter_mode == "ALL" else 1)
        self.mode.blockSignals(False)
        host = QWidget()
        lay = QVBoxLayout(host)
        if not self.q.filters:
            lay.addWidget(label("No filters yet - every row will be returned. Click '+ Add filter group' to add one.", "hint"))
        for i, g in enumerate(self.q.filters, 1):
            gb = GroupBox(g, self.ctx, i)
            gb.changed.connect(self.emit)
            gb.removed.connect(self._remove_group)
            lay.addWidget(gb)
        lay.addStretch()
        self.scroll.setWidget(host)

    def _mode(self):
        self.q.filter_mode = self.mode.currentData()
        self.emit()

    # ------------------------------------------------------------ quick filters
    def _school_target(self):
        """Pick (alias, column) for a school filter, adding a link table if needed."""
        q = self.q
        aliases = {t.alias: t.table for t in q.tables}
        for want in ("stuSchool", "empSchool", "SchoolDef", "Schedule", "AttendanceDaily"):
            for a, t in aliases.items():
                if t == want:
                    return a, "SchoolID"
        for a, t in aliases.items():
            if t == "Student":
                q.add_table("stuSchool")
                q.links.append(Link(a, "StudentID", "stuSchool", "StudentID", "INNER"))
                self._ensure_cond(Condition("stuSchool", "PrimarySchoolFlag", "eq", "1"))
                return "stuSchool", "SchoolID"
            if t == "Employee":
                q.add_table("empSchool")
                q.links.append(Link(a, "EmployeeID", "empSchool", "EmployeeID", "INNER"))
                self._ensure_cond(Condition("empSchool", "PrimarySchoolFlag", "eq", "1"))
                return "empSchool", "SchoolID"
        return None

    def _main_group(self):
        g = next((g for g in self.q.filters if g.match == "ALL"), None)
        if g is None:
            g = FilterGroup("ALL", [])
            self.q.filters.insert(0, g)
        return g

    def _ensure_cond(self, c):
        g = self._main_group()
        if not any(x.alias == c.alias and x.column == c.column for x in g.conditions):
            g.conditions.append(c)

    def _set_cond(self, alias, column, values):
        g = self._main_group()
        g.conditions = [c for c in g.conditions if not (c.alias == alias and c.column == column)]
        if values:
            g.conditions.append(Condition(alias, column, "in" if len(values) > 1 else "eq", ", ".join(values)))
        if not g.conditions:
            self.q.filters.remove(g)

    def _quick(self, kind):
        from ..codes import options
        opts = options(self.ctx.settings, kind)
        if not opts and kind == "grade":
            opts = [(c, "") for c in ["PK", "KG"] + [f"{i:02d}" for i in range(1, 13)]]
        if not opts:
            QMessageBox.information(self, "Schools", "Add your schools first: File > SAM Codes & Schools > Schools "
                                    "(type SchoolID and name, or import the 'school_list.csv' helper query).")
            return
        if kind == "schools":
            target = self._school_target()
            if not target:
                QMessageBox.information(self, "Schools", "Add Student, Employee or a school table in Step 1 first.")
                return
        else:
            st = next((t.alias for t in self.q.tables if t.table == "Student"), None)
            if not st:
                QMessageBox.information(self, "Grades", "Add the Student table in Step 1 first.")
                return
            target = (st, "ADAGrade")
        current = set()
        for g in self.q.filters:
            for c in g.conditions:
                if (c.alias, c.column) == target:
                    current |= {x.strip() for x in c.value.split(",")}
        from .widgets import choose_codes
        picked = choose_codes(self, "Choose schools" if kind == "schools" else "Choose grades", opts, current, True)
        if picked is None:
            return
        self._set_cond(target[0], target[1], picked)
        self.quick_note.setText(f"{'Schools' if kind == 'schools' else 'Grades'}: {', '.join(picked) or 'all'}")
        self.refresh()
        self.emit()

    def _quick_enrolled(self):
        from .. import district
        codes = str(district.get(self.ctx.settings).get("enrolled_status_codes", "")).strip()
        st = next((t.alias for t in self.q.tables if t.table == "Student"), None)
        if not st:
            QMessageBox.information(self, "Enrolled only", "Add the Student table in Step 1 first.")
            return
        if not codes:
            QMessageBox.information(self, "Enrolled only", "Set the Enrolled status code in File > District Settings "
                                    "(or import enrollment codes in File > SAM Codes & Schools).")
            return
        self._set_cond(st, "EnrollmentStatus", [c.strip() for c in codes.split(",") if c.strip()])
        self.refresh()
        self.emit()

    def _add_group(self):
        if not self.q.tables:
            QMessageBox.information(self, "Filters", "Choose tables in Step 1 first.")
            return
        self.q.filters.append(FilterGroup("ALL", [Condition()]))
        self.refresh()
        self.emit()

    def _remove_group(self, gb):
        self.q.filters.remove(gb.group)
        self.refresh()
        self.emit()


# =============================================================================== Step 5
class SortStep(Step):
    title = "Step 5 - Sort order and options"
    intro = "Choose how rows are ordered, and other output options."

    def __init__(self, ctx):
        super().__init__(ctx)
        row = QHBoxLayout()
        g1 = QGroupBox("Sort by (top = first)")
        g1l = QHBoxLayout(g1)
        self.avail = QListWidget()
        self.sorted = QListWidget()
        mid = QVBoxLayout()
        for txt, fn in ((">", self._add), ("<", self._remove), ("Up", lambda: self._move(-1)),
                        ("Down", lambda: self._move(1)), ("A-Z / Z-A", self._toggle)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            mid.addWidget(b)
        mid.addStretch()
        self.avail.itemDoubleClicked.connect(lambda _i: self._add())
        self.sorted.itemDoubleClicked.connect(lambda _i: self._toggle())
        v1 = QVBoxLayout()
        v1.addWidget(QLabel("Columns"))
        v1.addWidget(self.avail)
        v2 = QVBoxLayout()
        v2.addWidget(QLabel("Sorted by (double-click to flip A-Z / Z-A)"))
        v2.addWidget(self.sorted)
        g1l.addLayout(v1)
        g1l.addLayout(mid)
        g1l.addLayout(v2)
        row.addWidget(g1, 2)

        g2 = QGroupBox("Options")
        g2l = QVBoxLayout(g2)
        self.distinct = QCheckBox("Only show distinct rows (remove exact duplicates)")
        self.distinct.toggled.connect(self._opts)
        g2l.addWidget(self.distinct)
        tr = QHBoxLayout()
        tr.addWidget(QLabel("Limit to the first"))
        self.top = QSpinBox()
        self.top.setRange(0, 1000000)
        self.top.setSpecialValueText("all")
        self.top.valueChanged.connect(self._opts)
        tr.addWidget(self.top)
        tr.addWidget(QLabel("rows (0 = all)"))
        tr.addStretch()
        g2l.addLayout(tr)
        g2l.addWidget(hline())
        g2l.addWidget(QLabel("Query name (used as the title in SAM):"))
        self.name = QLineEdit()
        self.name.textEdited.connect(self._opts)
        g2l.addWidget(self.name)
        g2l.addWidget(QLabel("Description (what it returns, who it is for):"))
        self.desc = QPlainTextEdit()
        self.desc.setMaximumHeight(110)
        self.desc.textChanged.connect(self._opts)
        g2l.addWidget(self.desc)
        g2l.addStretch()
        row.addWidget(g2, 1)
        self.outer.addLayout(row, 1)
        self._loading = False

    def refresh(self):
        self._loading = True
        sorted_h = [s.heading for s in self.ctx.root.sort]
        self.avail.clear()
        for c in self.ctx.root.columns:
            if c.heading not in sorted_h:
                self.avail.addItem(c.heading)
        self.sorted.clear()
        for s in self.ctx.root.sort:
            self.sorted.addItem(list_item(f"{s.heading}   ({'Z-A' if s.desc else 'A-Z'})", s.heading))
        self.distinct.setChecked(self.ctx.root.distinct)
        self.top.setValue(int(self.ctx.root.top or 0))
        self.name.setText(self.ctx.root.name)
        if self.desc.toPlainText() != self.ctx.root.description:
            self.desc.setPlainText(self.ctx.root.description)
        self._loading = False

    def _opts(self):
        if self._loading:
            return
        self.ctx.root.distinct = self.distinct.isChecked()
        self.ctx.root.top = self.top.value()
        self.ctx.root.name = self.name.text()
        self.ctx.root.description = self.desc.toPlainText()
        self.emit()

    def _add(self):
        it = self.avail.currentItem()
        if it:
            self.ctx.root.sort.append(SortItem(it.text()))
            self.refresh()
            self.emit()

    def _remove(self):
        r = self.sorted.currentRow()
        if 0 <= r < len(self.ctx.root.sort):
            del self.ctx.root.sort[r]
            self.refresh()
            self.emit()

    def _move(self, d):
        r = self.sorted.currentRow()
        n = r + d
        if 0 <= r < len(self.ctx.root.sort) and 0 <= n < len(self.ctx.root.sort):
            self.ctx.root.sort[r], self.ctx.root.sort[n] = self.ctx.root.sort[n], self.ctx.root.sort[r]
            self.refresh()
            self.sorted.setCurrentRow(n)
            self.emit()

    def _toggle(self):
        r = self.sorted.currentRow()
        if 0 <= r < len(self.ctx.root.sort):
            self.ctx.root.sort[r].desc = not self.ctx.root.sort[r].desc
            self.refresh()
            self.sorted.setCurrentRow(r)
            self.emit()


# =============================================================================== Step 6
HOW_TO = """<b>Use this query in SAM</b>
<ol>
<li>Click <b>Copy SQL</b> below.</li>
<li>In SAM open <b>Ad Hoc Query &gt; Query</b>, create a new query, give it the same name, paste the SQL and save.
Check <b>Shared</b> if others should be able to run it.</li>
<li>Run it from <b>Ad Hoc Query &gt; Run Query</b>.</li>
</ol>
<b>Scheduled data pulls (CAC Agent)</b>
<ol>
<li>In SAM go to <b>Administration &gt; CAC Agent &gt; Query Maintenance</b> and click <b>Add New</b>.</li>
<li>Enter the title, paste the SQL into the Query box and <b>Save</b>.</li>
<li>In <b>Agent Maintenance</b> click <b>Add Job</b>, pick the query, set the folder path, file name (e.g. Data.csv) and time.</li>
<li>Schedule the Windows task for <i>CAS Agent Listener</i> at least one hour after the job time.</li>
</ol>
<i>Only the owner of a SAM query can overwrite it; others must save changes as a new query.</i>"""


class ReviewStep(Step):
    title = "Step 6 - Review and copy the SQL"
    intro = "The builder checks the query for problems. When it is ready, copy the SQL into SAM."
    request_save = Signal()

    def __init__(self, ctx):
        super().__init__(ctx)
        split = QSplitter(Qt.Horizontal)
        self.outer.addWidget(split, 1)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.issues = QListWidget()
        self.issues.setMaximumHeight(130)
        ll.addWidget(self.issues)
        self.privacy = QLabel()
        self.privacy.setWordWrap(True)
        self.privacy.setTextFormat(Qt.RichText)
        self.privacy.setStyleSheet("background:#FFFBEA;border:1px solid #E5D9A8;border-radius:4px;padding:6px;")
        ll.addWidget(self.privacy)
        opt = QHBoxLayout()
        self.header = QCheckBox("Include comment header (name/description)")
        self.header.setChecked(True)
        self.header.toggled.connect(self.refresh)
        opt.addWidget(self.header)
        opt.addStretch()
        self.edit_btn = QPushButton("Edit SQL by hand")
        self.edit_btn.setCheckable(True)
        self.edit_btn.toggled.connect(self._edit_mode)
        opt.addWidget(self.edit_btn)
        self.discard_btn = QPushButton("Discard manual edits")
        self.discard_btn.clicked.connect(self._discard)
        opt.addWidget(self.discard_btn)
        ll.addLayout(opt)
        self.sql = QPlainTextEdit()
        self.sql.setObjectName("sql")
        self.sql.setReadOnly(True)
        self.sql.setLineWrapMode(QPlainTextEdit.NoWrap)
        SqlHighlighter(self.sql.document())
        self.sql.textChanged.connect(self._sql_typed)
        ll.addWidget(self.sql, 1)
        btns = QHBoxLayout()
        cp = QPushButton("Copy SQL")
        cp.setObjectName("primary")
        cp.clicked.connect(self.copy)
        btns.addWidget(cp)
        sv = QPushButton("Save SQL file...")
        sv.clicked.connect(self.save_sql)
        btns.addWidget(sv)
        sq = QPushButton("Save query (to reopen later)")
        sq.clicked.connect(self.request_save)
        btns.addWidget(sq)
        btns.addStretch()
        self.copied = label("", "ok")
        btns.addWidget(self.copied)
        ll.addLayout(btns)
        split.addWidget(left)
        how = QLabel(HOW_TO)
        how.setWordWrap(True)
        how.setTextFormat(Qt.RichText)
        how.setAlignment(Qt.AlignTop)
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.addWidget(how)
        cl.addStretch()
        split.addWidget(card)
        split.setSizes([700, 330])
        self._setting = False

    def sql_text(self):
        return generate_sql(self.ctx.root, header=self.header.isChecked())

    def refresh(self):
        self.copied.setText("")
        errors, warnings = validate(self.ctx.root, self.cat)
        self.issues.clear()
        for e in errors:
            it = list_item("Problem: " + e)
            it.setForeground(Qt.red)
            self.issues.addItem(it)
        for w in warnings:
            it = list_item("Note: " + w)
            it.setForeground(Qt.darkYellow)
            self.issues.addItem(it)
        try:
            from ..privacy import html as _privacy_html
            self.privacy.setText(_privacy_html(self.ctx.root))
        except Exception as e:  # noqa: BLE001
            self.privacy.setText(f"Privacy check unavailable: {e}")
        if not errors:
            it = list_item("Ready - no problems found.")
            it.setForeground(Qt.darkGreen)
            self.issues.insertItem(0, it)
        manual = bool(self.ctx.root.sql_override.strip())
        self.discard_btn.setVisible(manual)
        self.edit_btn.blockSignals(True)
        self.edit_btn.setChecked(manual)
        self.edit_btn.blockSignals(False)
        self.sql.setReadOnly(not manual)
        self._setting = True
        self.sql.setPlainText(self.sql_text())
        self._setting = False

    def _edit_mode(self, on):
        if on:
            if QMessageBox.question(
                    self, "Edit SQL by hand",
                    "After editing by hand, changes made in Steps 1-5 will not update the SQL until you discard "
                    "your manual edits. Continue?") != QMessageBox.Yes:
                self.edit_btn.setChecked(False)
                return
            self.ctx.root.sql_override = self.sql.toPlainText()
        self.refresh()
        self.emit()

    def _discard(self):
        self.ctx.root.sql_override = ""
        self.refresh()
        self.emit()

    def _sql_typed(self):
        if self._setting or self.sql.isReadOnly():
            return
        self.ctx.root.sql_override = self.sql.toPlainText()
        self.emit()

    def copy(self):
        QGuiApplication.clipboard().setText(self.sql_text())
        self.copied.setText("Copied to clipboard.")

    def save_sql(self):
        from ..paths import queries_dir
        name = "".join(ch for ch in self.ctx.root.name if ch.isalnum() or ch in " -_").strip() or "query"
        path, _ = QFileDialog.getSaveFileName(self, "Save SQL", str(queries_dir() / f"{name}.sql"), "SQL files (*.sql)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.sql_text())
            self.copied.setText("Saved.")
