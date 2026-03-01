from pathlib import Path
from typing import Dict, Any, Set

from app.src.yaml_utils import load_yaml as _load_yaml


def is_playbook_yaml(path: Path) -> bool:
    doc = _load_yaml(path)
    if doc.get("type") == "playbook":
        return True
    if isinstance(doc.get("tasks"), dict) and "name" in doc and "id" in doc:
        return True
    return False


def parse_playbook_refs(path: Path) -> Dict[str, Any]:
    doc = _load_yaml(path)
    tasks = doc.get("tasks") or {}

    playbooks_by_name: Set[str] = set()
    playbooks_by_id: Set[str] = set()
    scripts: Set[str] = set()
    commands: Set[str] = set()

    for _, t in tasks.items():
        if not isinstance(t, dict):
            continue

        # XSOAR: most fields are under t["task"]
        inner = t.get("task") if isinstance(t.get("task"), dict) else {}
        candidates = (t, inner)

        for task in candidates:
            pb_name = task.get("playbookName") or task.get("playbookname")
            if pb_name and pb_name != "-":
                playbooks_by_name.add(str(pb_name))

            pb_id = task.get("playbookId") or task.get("playbookID") or task.get("playbookid")
            if pb_id and pb_id != "-":
                playbooks_by_id.add(str(pb_id))

            script_block = task.get("script")
            if isinstance(script_block, dict):
                sn = script_block.get("scriptName") or script_block.get("scriptname")
                if sn and sn != "-":
                    scripts.add(str(sn))

                cmd = script_block.get("command")
                if cmd and cmd != "-":
                    commands.add(str(cmd))

            sn2 = task.get("scriptName") or task.get("scriptname")
            if sn2 and sn2 != "-":
                scripts.add(str(sn2))

    return {
        "file": str(path),
        "name": doc.get("name"),
        "id": doc.get("id"),
        "refs": {
            "playbooks_by_name": sorted(playbooks_by_name),
            "playbooks_by_id": sorted(playbooks_by_id),
            "scripts": sorted(scripts),
            "commands": sorted(commands),
        },
    }