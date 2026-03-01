from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.src.yaml_utils import load_yaml


def iter_playbook_files(root: Path) -> List[Path]:
    """
    If root is a repo root (contains Packs/), iterate all playbooks in Packs/*/Playbooks/*.yml.
    If root is a pack root (contains Playbooks/), iterate Playbooks/*.yml.
    Returns a sorted list of Paths.
    """
    root = Path(root)

    packs_dir = root / "Packs"
    if packs_dir.exists() and packs_dir.is_dir():
        return sorted(packs_dir.glob("*/Playbooks/*.yml"))

    pb_dir = root / "Playbooks"
    if pb_dir.exists() and pb_dir.is_dir():
        return sorted(pb_dir.glob("*.yml"))

    return []


def _iter_script_files(root: Path) -> List[Path]:
    """
    If root is a repo root, iterate Packs/*/Scripts/**/*.yml.
    If root is a pack root, iterate Scripts/**/*.yml.
    """
    root = Path(root)

    packs_dir = root / "Packs"
    if packs_dir.exists() and packs_dir.is_dir():
        return sorted(packs_dir.glob("*/Scripts/**/*.yml"))

    scripts_dir = root / "Scripts"
    if scripts_dir.exists() and scripts_dir.is_dir():
        return sorted(scripts_dir.glob("**/*.yml"))

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