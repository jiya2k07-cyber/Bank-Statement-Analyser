"""Keyword rules. A rule = keyword + category (+ optional whole_word).

Conflict policy (design Q3): the LONGEST matching keyword wins, because a longer keyword is
more specific ("RELIANCE JIO" beats "RELIANCE"). A tie is broken by list order (earlier rule
wins), so the result is always deterministic."""
import re

from .categories import CATEGORIES


def sanitize(rules):
    seen, out = set(), []
    for r in rules or []:
        kw = str(r.get("keyword") or "").strip()
        cat = r.get("category")
        if not kw or cat not in CATEGORIES or (kw.lower(), cat) in seen:
            continue
        seen.add((kw.lower(), cat))
        out.append({"keyword": kw, "category": cat, "whole_word": bool(r.get("whole_word", False))})
    return out


def _hit(kw: str, low: str, whole_word: bool) -> bool:
    if whole_word:
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", low) is not None
    return kw in low


def match_rule(narration: str, rules):
    """Index of the winning rule, or None."""
    low = str(narration).lower()
    best = None
    for idx, r in enumerate(rules):
        kw = r["keyword"].strip().lower()
        if kw and _hit(kw, low, r.get("whole_word", False)):
            key = (len(kw), -idx)
            if best is None or key > best[0]:
                best = (key, idx)
    return best[1] if best else None


def apply_rules(narrations, rules):
    return [match_rule(n, rules) for n in narrations]


def short_keyword_warnings(rules, min_len=4):
    return [r["keyword"] for r in rules if len(r["keyword"].strip()) < min_len and not r.get("whole_word")]
