"""Explicit operator corrections, matched exactly; never trains an ASR model."""
import json
import re
import unicodedata
from pathlib import Path
from ..core.config import DATA_DIR

def normalized(text):
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()).strip()

def path():
    return Path(DATA_DIR)/"local-corrections.json"

_cache, _mtime = {}, None

def read():
    global _cache, _mtime
    try:
        stamp = (str(path()), path().stat().st_mtime_ns)
        if stamp != _mtime:
            _cache = json.loads(path().read_text(encoding="utf-8"))
            if not isinstance(_cache, dict):
                _cache = {}
            _mtime = stamp
    except (OSError, ValueError):
        _cache, _mtime = {}, None
    return dict(_cache)

def lookup(text):
    return read().get(normalized(text))

def write(rows):
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)

def remember(text, reference):
    key = normalized(text)
    if len(key.split()) < 4:
        raise ValueError("Gardez une phrase d’au moins quatre mots pour éviter les rapprochements trop larges.")
    rows = read()
    rows[key] = reference
    write(dict(list(rows.items())[-200:]))
    return len(rows)
