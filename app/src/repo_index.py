from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import yaml


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def iter_playbook_files(pack_root: Path):
    pb_dir = pack_root / "Playbooks"
    if not pb_dir.exists():
        return []
    return sorted(pb_dir.glob("*.yml"))


def build_symbol_table(pack_root: Path) -> Dict[str, Any]:
    """
    Symbol table for playbooks & scripts in a pack.
    Indexed by both name and id to support ref checks and rewrites.
    """
    playbooks_by_name: Dict[str, str] = {}
    playbooks_by_id: Dict[str, str] = {}
    scripts_by_name: Dict[str, str] = {}

    for yml in iter_playbook_files(pack_root):
        doc = _load_yaml(yml)
        name = doc.get("name")
        pid = doc.get("id")
        if name:
            playbooks_by_name[str(name)] = str(yml)
        if pid:
            playbooks_by_id[str(pid)] = str(yml)

    scripts_dir = pack_root / "Scripts"
    if scripts_dir.exists():
        for yml in scripts_dir.glob("**/*.yml"):
            doc = _load_yaml(yml)
            name = doc.get("name")
            if name:
                scripts_by_name[str(name)] = str(yml)

    return {
        "playbooks_by_name": playbooks_by_name,
        "playbooks_by_id": playbooks_by_id,
        "scripts_by_name": scripts_by_name,
    }