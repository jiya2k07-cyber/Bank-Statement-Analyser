"""LLM layer: batched, cached by merchant, closed category list, may answer Uncategorized."""
import json
import os
import re

from .categories import CATEGORIES

MODEL = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
BATCH_SIZE = 40


def build_system_prompt() -> str:
    lines = []
    for name, (inc, exc) in CATEGORIES.items():
        lines.append(f"- {name}: {inc}" + (f" NOT: {exc}" if exc else ""))
    cats = "\n".join(lines)
    return f"""You categorise bank-statement transactions for a personal finance app.

You receive a JSON list of objects: {{"id": int, "narration": str, "direction": "debit"|"credit"}}.
"debit" is money going out, "credit" is money coming in. The narration is the raw bank text.

Choose exactly ONE category per item from this closed list (spell it exactly):
{cats}

Rules:
- Use only the narration text and direction. Do not invent facts about the merchant.
- If the narration gives no real information about what the money was for (for example only a
  person's name, a QR/terminal code, or an opaque ID), answer "Uncategorized". A wrong confident
  label is worse than "Uncategorized". Being hard to classify is not a reason to guess.
- Money sent to or received from an individual person with no clear purpose is "Uncategorized",
  unless the text itself says what it is for.
- A credit that is clearly a refund or reversal takes the category of the original purchase.
- Bank-originated interest credited is "Income". Bank-levied charges and penalties are "Fees & Charges".
- Company legal names, abbreviations and payment-processor prefixes should be decoded using
  your general knowledge of what type of business that is.

Respond with ONLY a JSON array, no prose and no code fences, one object per input id:
[{{"id": 0, "category": "<one category>", "reason": "<one short line>"}}]"""


def _extract_json_array(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array in response")
    return json.loads(text[start:end + 1])


def parse_response(text: str):
    """-> ({id: {category, reason}}, n_rejected). Any category outside the closed list is rejected."""
    results, rejected = {}, 0
    for item in _extract_json_array(text):
        try:
            i = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        cat, reason = item.get("category"), str(item.get("reason", ""))[:200]
        if cat not in CATEGORIES:
            rejected += 1
            cat, reason = "Uncategorized", f"rejected invalid label {cat!r}"
        results[i] = {"category": cat, "reason": reason}
    return results, rejected


def anthropic_call(system: str, user: str) -> str:
    import anthropic  # imported lazily: the app works without the package/key
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    resp = client.messages.create(model=MODEL, max_tokens=4096, system=system,
                                  messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in resp.content if b.type == "text")


def api_key_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def categorise_pending(pending: dict, cache: dict, call_fn=anthropic_call, batch_size=BATCH_SIZE):
    """pending: {cache_key: (narration, direction)}. Fills `cache` in place for answered
    merchants and returns run stats. Unanswered merchants are NOT cached (they can be retried)."""
    stats = {"api_calls": 0, "merchants_sent": 0, "rejected": 0, "unanswered": 0, "error": None}
    todo = [k for k in pending if k not in cache]
    system = build_system_prompt()
    for s in range(0, len(todo), batch_size):
        remaining = dict(enumerate(todo[s:s + batch_size]))
        stats["merchants_sent"] += len(remaining)
        for _attempt in range(2):                      # first try + one retry
            if not remaining:
                break
            payload = [{"id": i, "narration": pending[k][0], "direction": pending[k][1]}
                       for i, k in remaining.items()]  # nothing else leaves the machine
            try:
                stats["api_calls"] += 1
                text = call_fn(system, json.dumps(payload, ensure_ascii=False))
                results, rej = parse_response(text)
                stats["rejected"] += rej
            except Exception as e:                      # bad JSON, network, auth...
                stats["error"] = str(e)[:200]
                continue
            for i in list(remaining):
                if i in results:
                    cache[remaining.pop(i)] = results[i]
        stats["unanswered"] += len(remaining)
    return stats
