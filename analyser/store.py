"""Tiny JSON persistence. A missing or corrupted file never crashes the app."""
import json
import os
import time

DATA_DIR = os.environ.get("ANALYSER_DATA_DIR", "data")
RULES_PATH = os.path.join(DATA_DIR, "rules.json")
OVERRIDES_PATH = os.path.join(DATA_DIR, "overrides.json")
CACHE_PATH = os.path.join(DATA_DIR, "llm_cache.json")
DEFAULT_RULES_PATH = "default_rules.json"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # Keep the broken file for inspection instead of silently overwriting it.
        try:
            os.replace(path, f"{path}.corrupt-{int(time.time())}")
        except OSError:
            pass
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)  # atomic: a crash mid-write cannot leave half a file
