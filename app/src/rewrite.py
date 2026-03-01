import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import yaml  # <-- you need this for safe_dump

from app.src.yaml_utils import load_yaml as _load_yaml


UUIDISH = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


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
    Normalize playbook id -> name.
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

        # Keep only UUID-ish ids (recommended) OR map all mismatches (set to True).
        if UUIDISH.match(pid_s):
            mapping[pid_s] = name_s

        # If you truly want *all* mismatches, replace the above with:
        # mapping[pid_s] = name_s

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
            inner = task.get("task") if isinstance(task.get("task"), dict) else None
            targets = [task]
            if inner is not None:
                targets.append(inner)

            for target in targets:
                for key in ("playbookId", "playbookID", "playbookid"):
                    v = target.get(key)
                    if v is None:
                        continue
                    vs = str(v)
                    if vs in id_map:
                        new = id_map[vs]
                        target[key] = new
                        changes.append(RewriteChange(str(path), "task_playbookId", vs, new, f"tasks.{tid}.{'task.' if target is inner else ''}{key}"))
                        modified = True

                pb_name = target.get("playbookName") or target.get("playbookname")
                if pb_name is not None:
                    pns = str(pb_name)
                    if pns in id_map:
                        new = id_map[pns]
                        if "playbookName" in target:
                            target["playbookName"] = new
                        else:
                            target["playbookname"] = new
                        changes.append(RewriteChange(str(path), "task_playbookName", pns, new, f"tasks.{tid}.{'task.' if target is inner else ''}playbookName"))
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