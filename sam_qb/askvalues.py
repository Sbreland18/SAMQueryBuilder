"""Fill-in values: filter conditions marked 'Ask when copying' get their value typed in each time the SQL is
copied or saved, so one saved query works all year ("Which school?", "Since which date?")."""
from __future__ import annotations

import copy

from .query_model import QueryDef


def _conds(q: QueryDef):
    for g in q.filters:
        yield from g.conditions
    for l in q.links:
        yield from l.conditions
    for p in q.union_parts:
        yield from _conds(p)


def asked(q: QueryDef) -> list[dict]:
    """One entry per distinct prompt: {'prompt', 'default', 'op', 'two'} (the same prompt in several places is
    asked once)."""
    out, seen = [], set()
    for c in _conds(q):
        if c.ask and c.ask not in seen:
            seen.add(c.ask)
            out.append({"prompt": c.ask, "default": c.value, "default2": c.value2, "op": c.op,
                        "two": c.op == "between", "alias": c.alias, "column": c.column})
    return out


def with_values(q: QueryDef, values: dict) -> QueryDef:
    """Copy of q with each asked condition's value replaced. values = {prompt: value or (value, value2)}."""
    q2 = copy.deepcopy(q)
    for c in _conds(q2):
        if c.ask and c.ask in values:
            v = values[c.ask]
            if isinstance(v, (tuple, list)):
                c.value, c.value2 = str(v[0]), str(v[1])
            else:
                c.value = str(v)
    return q2


def remember(settings: dict, values: dict):
    store = settings.setdefault("ask_values", {})
    for k, v in values.items():
        store[k] = list(v) if isinstance(v, (tuple, list)) else v
