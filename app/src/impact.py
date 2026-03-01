from __future__ import annotations

from pathlib import Path
from typing import List, Set

from app.src.yaml_utils import load_yaml as _load_yaml


def find_pack_playbooks_referencing_ids(pack_playbook_files: List[Path], old_ids: Set[str]) -> List[Path]:
    """
    Find playbooks that reference any of the old IDs in playbookId fields.

    Supports both:
      - tasks.<tid>.playbookId
      - tasks.<tid>.task.playbookId   (common XSOAR structure)
    """
    impacted: List[Path] = []

    if not old_ids:
        return impacted

    for pb in pack_playbook_files:
        doc = _load_yaml(pb)
        tasks = doc.get("tasks") or {}
        found = False

        if isinstance(tasks, dict):
            for _, t in tasks.items():
                if not isinstance(t, dict):
                    continue

                inner = t.get("task") if isinstance(t.get("task"), dict) else None
                candidates = [t]
                if inner is not None:
                    candidates.append(inner)

                for task in candidates:
                    for key in ("playbookId", "playbookID", "playbookid"):
                        v = task.get(key)
                        if v is None:
                            continue
                        if str(v) in old_ids:
                            found = True
                            break
                    if found:
                        break

                if found:
                    break

        if found:
            impacted.append(pb)

    return impacted