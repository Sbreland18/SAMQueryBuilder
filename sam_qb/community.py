"""Community query library: a district shares a useful ad hoc query, you review it, and it ships to every
district in a data update (as a template in the 'Community queries' category).

Sharing never includes data - only the query's design. District-specific values (email domains, district name)
are replaced with district-setting placeholders that every district fills in when it opens the template."""
from __future__ import annotations

import copy
import json
import re

from .app_config import GITHUB_REPO
from .query_model import QueryDef

CATEGORY = "Community queries"
MARK = "samq-community"


def _walk_text(d: dict, fn):
    for c in d.get("columns", []):
        for p in c.get("parts", []):
            if p.get("kind") == "text":
                p["value"] = fn(p.get("value", ""))
        if c.get("kind") == "raw":
            c["column"] = fn(c.get("column", ""))
    for g in d.get("filters", []):
        for cnd in g.get("conditions", []):
            cnd["value"] = fn(str(cnd.get("value", "")))
            cnd["value2"] = fn(str(cnd.get("value2", "")))
    for l in d.get("links", []):
        for cnd in l.get("conditions", []):
            cnd["value"] = fn(str(cnd.get("value", "")))
    for u in d.get("union_parts", []):
        _walk_text(u, fn)


def prepare(q: QueryDef, settings: dict) -> tuple[dict, list[str]]:
    """(query dict ready to share, notes for the person sharing)."""
    from . import district
    ds = district.get(settings)
    d = copy.deepcopy(q.to_dict())
    for k in ("created", "modified"):
        d[k] = ""
    notes = []
    repl = []
    for key, var in (("staff_email_domain", "{{STAFF_EMAIL_DOMAIN}}"), ("student_email_domain",
                                                                          "{{STUDENT_EMAIL_DOMAIN}}")):
        dom = str(ds.get(key) or "").strip()
        if dom:
            repl.append((dom, var))
    codes = str(ds.get("enrolled_status_codes") or "").strip()
    changed = []

    def fn(text):
        out = text
        for dom, var in repl:
            if dom and dom.lower() in out.lower():
                out = re.sub(re.escape(dom), var, out, flags=re.I)
        if out != text:
            changed.append(text)
        return out
    _walk_text(d, fn)
    if changed:
        notes.append("Your email domain was replaced with a district-setting placeholder, so other districts get "
                     "their own domain.")
    for g in d.get("filters", []):
        for cnd in g.get("conditions", []):
            if cnd.get("column") == "SchoolID" and str(cnd.get("value", "")).strip():
                notes.append(f"A filter uses your SchoolID(s) {cnd['value']} - other districts will need to change "
                             "it (or remove that filter before sharing).")
            if cnd.get("column") == "EnrollmentStatus" and codes and str(cnd.get("value")) == codes:
                cnd["value"] = "{{ENROLLED_STATUS_CODES}}"
                notes.append("Your enrolled-status code was replaced with the district-setting placeholder.")
    if d.get("sql_override", "").strip():
        notes.append("This query's SQL was edited by hand - the hand-edited SQL is shared as it is.")
    return d, notes


def compose(d: dict, title: str, description: str, author: str) -> tuple[str, str]:
    d = dict(d)
    d["name"] = title.strip() or d.get("name", "Shared query")
    d["description"] = description.strip() or d.get("description", "")
    d["author"] = author.strip()
    d["category"] = CATEGORY
    body = [f"**Shared query:** {d['name']}", "", d["description"] or "-", "",
            f"**Shared by:** {author.strip() or '-'}", "",
            "Maintainer: copy this whole issue (or the JSON below) into Build GUI > Data > "
            "'Add community query' to review and publish it.", "",
            f"```json {MARK}", json.dumps(d, separators=(",", ":")), "```"]
    return f"[Community query] {d['name']}"[:120], "\n".join(body)


def fits_in_url(title: str, body: str) -> bool:
    import urllib.parse
    from .bugreport import MAX_URL
    return len(urllib.parse.quote(title)) + len(urllib.parse.quote(body)) + 120 <= MAX_URL


def github_url(title: str, body: str, repo: str = GITHUB_REPO) -> str:
    """Never cut the query in half: when it's too long for a link, the issue opens with a note and the person
    pastes the full text (put on the clipboard by the dialog)."""
    from .bugreport import github_issue_url
    if not fits_in_url(title, body):
        body = ("**The shared query is too long for a link - paste it here (it's on your clipboard), replacing "
                "this line.**")
    return github_issue_url(title, body, repo).replace("labels=bug", "labels=community-query")


def parse_submission(text: str) -> dict:
    """The query dict from a shared report (issue text, email body or a .samq file's contents)."""
    m = re.search(r"```json[^\n]*\n(.*?)```", text, re.S)
    raw = m.group(1) if m else text
    start = raw.find("{")
    if start < 0:
        raise ValueError("No query found - paste the whole shared report, including the JSON part.")
    d = json.loads(raw[start:raw.rfind("}") + 1])
    if not d.get("tables") and not d.get("sql_override"):
        raise ValueError("That doesn't look like a SAM Ad Hoc Query Builder query.")
    QueryDef.from_dict(d)  # validates the structure
    d["category"] = CATEGORY
    d.setdefault("author", "")
    return d
