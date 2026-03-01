from pathlib import Path
from typing import Dict, Set
import shutil
import tempfile

from app.src.playbook_refs import parse_playbook_refs
from app.src.repo_index import iter_playbook_files


def build_repo_graph(repo_root: Path) -> Dict[str, Dict[str, Set[str]]]:
    graph: Dict[str, Dict[str, Set[str]]] = {}

    for pb_path in iter_playbook_files(repo_root):
        parsed = parse_playbook_refs(pb_path)

        graph[str(pb_path.relative_to(repo_root))] = {
            "playbooks": set(parsed["refs"]["playbooks_by_id"]),
            "scripts": set(parsed["refs"]["scripts"]),
        }

    return graph


def compare_graphs(before, after):
    broken = []

    for node, deps in before.items():
        if node not in after:
            continue

        lost_playbooks = deps["playbooks"] - after[node]["playbooks"]
        lost_scripts = deps["scripts"] - after[node]["scripts"]

        if lost_playbooks or lost_scripts:
            broken.append({
                "node": node,
                "lost_playbooks": list(lost_playbooks),
                "lost_scripts": list(lost_scripts),
            })

    return broken


def simulate_repo_with_staging(repo_root: Path, staging_root: Path) -> Path:
    """
    Create a temp copy of repo_root and overlay staged playbooks.
    Returns path to temp repo.
    """
    temp_dir = Path(tempfile.mkdtemp())

    # Copy entire repo
    shutil.copytree(repo_root, temp_dir / repo_root.name)
    temp_repo = temp_dir / repo_root.name

    # Overlay staging playbooks
    staging_playbooks = staging_root / "Playbooks"
    if staging_playbooks.exists():
        target_pack = staging_root.name.replace("_ingest", "")
        target_dir = temp_repo / "Packs" / target_pack / "Playbooks"

        target_dir.mkdir(parents=True, exist_ok=True)

        for pb in staging_playbooks.glob("*.yml"):
            shutil.copy2(pb, target_dir / pb.name)

    return temp_repo