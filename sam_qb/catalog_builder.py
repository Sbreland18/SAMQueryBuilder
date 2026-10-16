"""Builds data/catalog.json from the SAMS Object Browser export + catalog_overrides.json.

The Object Browser export is a "wide" CSV: every column header is a table name and the
cells below it are that table's column names. Relationships are inferred from naming
conventions (a column named XyzID links to the table whose first column is XyzID) and
then merged with the hand-curated links in catalog_overrides.json.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def read_wide_csv(path: str | Path) -> dict[str, list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return {}
    header = rows[0]
    tables: dict[str, list[str]] = {}
    for i, name in enumerate(header):
        name = name.strip()
        if not name:
            continue
        cols = []
        for r in rows[1:]:
            if i < len(r) and r[i].strip() and r[i].strip() not in cols:
                cols.append(r[i].strip())
        tables[name] = cols
    return tables


def split_camel(name: str) -> str:
    name = re.sub(r"^(lookup|Lookup|LookUp|lookUp)", "", name)
    name = name.replace("_", " ")
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _canonical_score(table: str, pk: str, hidden: bool) -> int:
    stem = pk[:-2].lower()
    t = table.lower()
    score = 0
    if t == stem:
        score += 100
    elif t.startswith(stem):
        score += 60
    elif stem in t:
        score += 30
    if hidden:
        score -= 200
    if "_" in table:
        score -= 40
    score -= len(table) // 4
    return score


def build_catalog(csv_path: str | Path, overrides_path: str | Path, data_version: str | None = None) -> dict:
    tables = read_wide_csv(csv_path)
    ov = json.loads(Path(overrides_path).read_text(encoding="utf-8"))

    hidden_res = [re.compile(p) for p in ov.get("hidden_patterns", [])]
    cat_rules = [(re.compile(p), c) for p, c in ov.get("category_rules", [])]
    common = [t for t in ov.get("common_tables", []) if t in tables]
    tmeta = ov.get("tables", {})

    out_tables = {}
    for name, cols in sorted(tables.items(), key=lambda kv: kv[0].lower()):
        hidden = any(r.search(name) for r in hidden_res)
        category = "Other"
        for rx, c in cat_rules:
            if rx.search(name):
                category = c
                break
        meta = tmeta.get(name, {})
        out_tables[name] = {
            "columns": cols,
            "category": meta.get("category", category),
            "friendly": meta.get("friendly", split_camel(name)),
            "description": meta.get("description", ""),
            "hidden": bool(meta.get("hidden", hidden)),
            "common": name in common,
        }

    # ---- inferred relationships -------------------------------------------------
    pk_owners: dict[str, list[str]] = defaultdict(list)
    for name, info in out_tables.items():
        cols = info["columns"]
        if cols and cols[0].lower().endswith("id") and cols[0].lower() not in ("luid", "id"):
            pk_owners[cols[0].lower()].append(name)
    canonical = {}
    for pk, owners in pk_owners.items():
        best = max(owners, key=lambda t: _canonical_score(t, pk, out_tables[t]["hidden"]))
        if not out_tables[best]["hidden"]:
            canonical[pk] = best

    rels = []
    seen = set()

    def add(ft, fc, tt, tc, label, weight, lookup=False, source="inferred"):
        if ft not in out_tables or tt not in out_tables or ft == tt:
            return
        key = (ft, fc.lower(), tt, tc.lower())
        rkey = (tt, tc.lower(), ft, fc.lower())
        if key in seen or rkey in seen:
            return
        seen.add(key)
        rels.append({"from_table": ft, "from_col": fc, "to_table": tt, "to_col": tc,
                     "label": label, "weight": weight, "lookup": lookup, "source": source})

    # curated first so they win de-duplication
    for r in ov.get("relationships", []):
        ft, fc = r["from"].split(".", 1)
        tt, tc = r["to"].split(".", 1)
        add(ft, fc, tt, tc, r.get("label", f"{ft} to {tt}"), r.get("weight", 1), r.get("lookup", False), "curated")

    for name, info in out_tables.items():
        if info["hidden"]:
            continue
        for i, col in enumerate(info["columns"]):
            lc = col.lower()
            if i == 0 and lc in canonical and canonical[lc] == name:
                continue
            target = canonical.get(lc)
            if target and target != name:
                w = 2 if (info["common"] or out_tables[target]["common"]) else 3
                add(name, col, target, out_tables[target]["columns"][0],
                    f"{info['friendly']} to {out_tables[target]['friendly']}", w)

    return {
        "data_version": data_version or datetime.now().strftime("%Y.%m.%d.1"),
        "generated": datetime.now().isoformat(timespec="seconds"),
        "tables": out_tables,
        "column_notes": ov.get("columns", {}),
        "sensitive_columns": ov.get("sensitive_columns", []),
        "common_tables": common,
        "relationships": rels,
    }


def write_catalog(csv_path, overrides_path, out_path, data_version=None) -> dict:
    cat = build_catalog(csv_path, overrides_path, data_version)
    Path(out_path).write_text(json.dumps(cat, indent=1), encoding="utf-8")
    return cat
