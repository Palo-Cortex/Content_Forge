from __future__ import annotations

from pathlib import Path
from typing import List, Set


from app.src.yaml_utils import load_yaml as _load_yaml


def find_pack_playbooks_referencing_ids(pack_playbook_files: List[Path], old_ids: Set[str]) -> List[Path]:
    """
    Find playbooks in the target pack that reference any of the old IDs (playbookId fields).
    """
    impacted: List[Path] = []
    for pb in pack_playbook_files:
        doc = _load_yaml(pb)
        tasks = doc.get("tasks") or {}
        found = False
        if isinstance(tasks, dict):
            for _, task in tasks.items():
                if not isinstance(task, dict):
                    continue
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
            impacted.append(pb)
    return impacted