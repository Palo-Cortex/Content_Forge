from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import yaml

UUIDISH = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _dump_yaml(doc: dict, path: Path) -> None:
    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")


@dataclass
class RewriteChange:
    file: str
    kind: str
    old: str
    new: str
    location: str



def build_id_normalization_map(playbook_files: List[Path]) -> Dict[str, str]:
    """
    Option 2: normalize playbook id -> name.
    Map old_id -> playbook_name for any playbook where id != name.
    """
    mapping: Dict[str, str] = {}
    for pb in playbook_files:
        doc = _load_yaml(pb)
        pid = doc.get("id")
        name = doc.get("name")
        if not pid or not name:
            continue
        pid_s = str(pid)
        name_s = str(name)
        if pid_s == name_s:
            continue
        # Prefer UUID-ish, but keep it for any mismatch (your call).
        if UUIDISH.match(pid_s) or True:
            mapping[pid_s] = name_s
    return mapping


def apply_mapping_to_playbook(path: Path, id_map: Dict[str, str]) -> Tuple[List[RewriteChange], bool]:
    doc = _load_yaml(path)
    changes: List[RewriteChange] = []
    modified = False

    pid = doc.get("id")
    if pid is not None:
        pid_s = str(pid)
        if pid_s in id_map:
            new = id_map[pid_s]
            doc["id"] = new
            changes.append(RewriteChange(str(path), "playbook_id", pid_s, new, "root.id"))
            modified = True

    tasks = doc.get("tasks")
    if isinstance(tasks, dict):
        for tid, task in tasks.items():
            if not isinstance(task, dict):
                continue

            for key in ("playbookId", "playbookID", "playbookid"):
                v = task.get(key)
                if v is None:
                    continue
                vs = str(v)
                if vs in id_map:
                    new = id_map[vs]
                    task[key] = new
                    changes.append(RewriteChange(str(path), "task_playbookId", vs, new, f"tasks.{tid}.{key}"))
                    modified = True

            pb_name = task.get("playbookName") or task.get("playbookname")
            if pb_name is not None:
                pns = str(pb_name)
                if pns in id_map:
                    new = id_map[pns]
                    if "playbookName" in task:
                        task["playbookName"] = new
                        changes.append(RewriteChange(str(path), "task_playbookName", pns, new, f"tasks.{tid}.playbookName"))
                    else:
                        task["playbookname"] = new
                        changes.append(RewriteChange(str(path), "task_playbookName", pns, new, f"tasks.{tid}.playbookname"))
                    modified = True

    if modified:
        _dump_yaml(doc, path)

    return changes, modified


def apply_mapping_across_files(playbook_files: List[Path], id_map: Dict[str, str]) -> List[RewriteChange]:
    all_changes: List[RewriteChange] = []
    for pb in playbook_files:
        changes, _ = apply_mapping_to_playbook(pb, id_map)
        all_changes.extend(changes)
    return all_changes