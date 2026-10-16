"""Command-line catalog rebuild.  Usage:
    python tools/build_catalog.py [--csv PATH] [--data-version 2026.10.15.1]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sam_qb.catalog_builder import write_catalog  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "SAMS Database Object Browser - Tables.csv"))
    ap.add_argument("--overrides", default=str(ROOT / "data" / "catalog_overrides.json"))
    ap.add_argument("--out", default=str(ROOT / "data" / "catalog.json"))
    ap.add_argument("--data-version", default=None)
    a = ap.parse_args()
    cat = write_catalog(a.csv, a.overrides, a.out, a.data_version)
    vis = sum(1 for t in cat["tables"].values() if not t["hidden"])
    print(f"Wrote {a.out}: {len(cat['tables'])} tables ({vis} visible), "
          f"{len(cat['relationships'])} links, data_version {cat['data_version']}")
