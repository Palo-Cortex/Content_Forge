from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import shutil
import tempfile

from app.src.playbook_refs import parse_playbook_refs
from app.src.repo_index import iter_playbook_files


def build_repo_graph(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    Graph keyed by playbook id (fallback to filename).
    Values contain dependency sets discovered from playbook tasks.
    """
    graph: Dict[str, Dict[str, Any]] = {}

    for pb_path in iter_playbook_files(repo_root):
        parsed = parse_playbook_refs(pb_path)

        node_id = str(parsed.get("id") or pb_path.name)
        graph[node_id] = {
            "path": str(pb_path.relative_to(repo_root)),
            "playbooks_by_id": set(parsed["refs"]["playbooks_by_id"]),
            "playbooks_by_name": set(parsed["refs"]["playbooks_by_name"]),
            "scripts": set(parsed["refs"]["scripts"]),
        }

    return graph


def compare_graphs(before, after, focus_nodes=None):
    """
    Only checks LOST edges from before -> after.
    This avoids false positives from legacy/missing/marketplace refs across the repo.
    """
    broken = []
    nodes = focus_nodes if focus_nodes else before.keys()

    for node in nodes:
        if node not in before or node not in after:
            continue

        deps_before = before[node]
        deps_after = after[node]

        lost_playbooks_by_id = deps_before.get("playbooks_by_id", set()) - deps_after.get("playbooks_by_id", set())
        lost_scripts = deps_before.get("scripts", set()) - deps_after.get("scripts", set())

        if lost_playbooks_by_id or lost_scripts:
            broken.append({
                "kind": "lost_edges",
                "node": node,
                "lost_playbooks_by_id": sorted(lost_playbooks_by_id),
                "lost_scripts": sorted(lost_scripts),
            })

    return broken


def simulate_repo_with_staging(repo_root: Path, staging_root: Path) -> Path:
    """
    Create a temp copy of repo_root and overlay staged playbooks into the target pack.
    Returns the temp repo path.
    """
    temp_dir = Path(tempfile.mkdtemp())
    dst = temp_dir / repo_root.name

    shutil.copytree(repo_root, dst)
    temp_repo = dst

    staging_playbooks = staging_root / "Playbooks"
    if staging_playbooks.exists():
        target_pack = staging_root.name.replace("_ingest", "")
        target_dir = temp_repo / "Packs" / target_pack / "Playbooks"
        target_dir.mkdir(parents=True, exist_ok=True)

        for pb in staging_playbooks.glob("*.yml"):
            shutil.copy2(pb, target_dir / pb.name)

    return temp_repo