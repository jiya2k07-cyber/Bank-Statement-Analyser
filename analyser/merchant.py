"""Pull a clean merchant name out of a raw narration (one extractor per format)."""
import re

IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
NOISE = {"BPAY", "ONL", "INFT", "BIL", "NEFT", "IMPS", "RTGS", "UPI", "CR", "DR"}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" -/.,:*").upper()


def _looks_like_ref(p: str) -> bool:
    return (" " not in p and len(p) >= 8 and any(c.isdigit() for c in p)
            and re.fullmatch(r"[A-Za-z0-9]+", p) is not None)


def _first_name(parts):
    for p in parts:
        p = p.strip()
        if (not p or p.isdigit() or IFSC.match(p.upper()) or _looks_like_ref(p)
                or p.upper() in NOISE):
            continue
        return p
    return ""


def extract_merchant(narration: str) -> str:
    n = (narration or "").strip()
    u = n.upper()
    name = ""
    if u.startswith("UPI"):
        # UPI-<NAME><vpa@bank>-<IFSC>-<ref>-<remark>. Name and VPA are glued together;
        # the VPA is lowercase, so split where the lowercase run that ends in @bank starts.
        parts = n.split("-")
        seg = parts[1] if len(parts) > 1 else ""
        m = re.match(r"^(.*?)\s*[a-z0-9._]+@[A-Za-z0-9]+$", seg)
        name = m.group(1) if m else seg
    elif u.startswith("POS"):
        m = re.search(r"\d{4,6}[X*]{4,}\d{2,4}\s+(.*?)\s*POS\s*DEBIT", n, re.I)
        if m:
            name = m.group(1)
        else:
            name = re.sub(r"\s*POS\s*DEBIT\s*$", "", re.sub(r"^POS\s*", "", n, flags=re.I), flags=re.I)
    elif u.startswith(("NEFT", "IMPS", "RTGS")):
        name = _first_name(re.split(r"[-/]", n)[1:])
    elif u.startswith("ACH"):
        name = _first_name(re.sub(r"^ACH\s*[DC]\s*-\s*", "", n, flags=re.I).split("-"))
    elif u.startswith("BIL") or u.startswith("BPAY"):
        name = _first_name(re.split(r"[/-]", n))
    elif u.startswith("ATW") or u.startswith("ATM"):
        name = "ATM CASH"
    if not _clean(name):
        # Unrecognised format (e.g. plain-text bank charges): drop digits/dates, keep first words.
        words = [w for w in re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", " ", n).split() if not re.search(r"\d", w)]
        name = " ".join(words[:4]) or n[:30]
    return _clean(name) or "UNKNOWN"


def cache_key(merchant: str, direction: str) -> str:
    """Digit runs are masked so names that change per transaction (IDs, order numbers)
    collapse into one key instead of defeating the cache."""
    masked = re.sub(r"\d{3,}", "#", merchant)
    return f"{direction}|{masked}"
