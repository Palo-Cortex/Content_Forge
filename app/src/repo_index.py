from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.src.yaml_utils import load_yaml


def iter_playbook_files(root: Path):
    """
    Walk entire repo (or pack) and return all playbook YAML files.
    """
    results = []

    for yml in root.glob("**/*.yml"):
        try:
            doc = load_yaml(yml)
        except Exception:
            continue

        if not isinstance(doc, dict):
            continue

        if doc.get("type") == "playbook":
            results.append(yml)
            continue

        if isinstance(doc.get("tasks"), dict) and "name" in doc and "id" in doc:
            results.append(yml)

    return sorted(results)


def _iter_script_files(root: Path) -> List[Path]:
    """
    Accepts:
      - repo root: contains Packs/
      - Packs root: is the Packs/ directory
      - pack root: contains Scripts/
    Returns all script YAML files.
    """
    root = Path(root)

    # Case 1: pack root
    scripts_dir = root / "Scripts"
    if scripts_dir.exists() and scripts_dir.is_dir():
        paths = list(scripts_dir.glob("**/*.yml")) + list(scripts_dir.glob("**/*.yaml"))
        return sorted(paths)

    # Case 2: Packs root
    if root.name == "Packs" and root.exists() and root.is_dir():
        paths = list(root.glob("*/Scripts/**/*.yml")) + list(root.glob("*/Scripts/**/*.yaml"))
        return sorted(paths)

    # Case 3: repo root
    packs_dir = root / "Packs"
    if packs_dir.exists() and packs_dir.is_dir():
        paths = list(packs_dir.glob("*/Scripts/**/*.yml")) + list(packs_dir.glob("*/Scripts/**/*.yaml"))
        return sorted(paths)

    return []
def build_symbol_table(root: Path) -> Dict[str, Any]:
    """
    Symbol table for playbooks & scripts.
    Works when root is either a repo root or a pack root.
    Indexed by both name and id to support ref checks and rewrites.
    """
    playbooks_by_name: Dict[str, str] = {}
    playbooks_by_id: Dict[str, str] = {}
    scripts_by_name: Dict[str, str] = {}

    # Playbooks
    for yml in iter_playbook_files(root):
        doc = load_yaml(yml)
        name = doc.get("name")
        pid = doc.get("id")

        if name:
            playbooks_by_name[str(name)] = str(yml)
        if pid:
            playbooks_by_id[str(pid)] = str(yml)

    # Scripts
    for yml in _iter_script_files(root):
        doc = load_yaml(yml)
        name = doc.get("name")
        if name:
            scripts_by_name[str(name)] = str(yml)

    return {
        "playbooks_by_name": playbooks_by_name,
        "playbooks_by_id": playbooks_by_id,
        "scripts_by_name": scripts_by_name,
    }