from __future__ import annotations

from pathlib import Path
import yaml

def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _dump_yaml(doc: dict, path: Path) -> None:
    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")

def _t(v: str):
    try:
        parts = [int(x) for x in str(v).strip().split(".")]
        return (parts + [0,0,0])[:3]
    except Exception:
        return (0,0,0)

def fix_from_version(file_path: Path, min_version: str) -> bool:
    """Ensure playbook has fromversion/fromVersion >= min_version.

    We set both keys defensively because environments differ.
    """
    doc = _load_yaml(file_path)
    if not isinstance(doc, dict):
        return False

    cur = doc.get("fromversion") or doc.get("fromVersion")
    changed = False

    if cur is None or str(cur).strip() in ("", "0", "0.0.0"):
        doc["fromversion"] = min_version
        doc["fromVersion"] = min_version
        changed = True
    else:
        if _t(cur) < _t(min_version):
            doc["fromversion"] = min_version
            doc["fromVersion"] = min_version
            changed = True
        else:
            # ensure both exist
            if "fromversion" not in doc:
                doc["fromversion"] = str(cur)
                changed = True
            if "fromVersion" not in doc:
                doc["fromVersion"] = str(cur)
                changed = True

    if changed:
        _dump_yaml(doc, file_path)
    return changed

def heal_playbooks_min_fromversion(playbook_paths, min_version: str = "5.0.0") -> int:
    changed = 0
    for p in playbook_paths:
        fp = Path(p)
        if fp.exists() and fp.is_file():
            if fix_from_version(fp, min_version):
                changed += 1
    return changed
