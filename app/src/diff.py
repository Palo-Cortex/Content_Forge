import hashlib
from pathlib import Path
from typing import Dict


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def hash_playbooks(pack_root: Path) -> Dict[str, str]:
    pb_dir = pack_root / "Playbooks"
    hashes = {}

    if not pb_dir.exists():
        return hashes

    for p in sorted(pb_dir.glob("*.yml")):
        hashes[p.name] = file_hash(p)

    return hashes


def compute_diff(before: Dict[str, str], after: Dict[str, str]):
    added = []
    modified = []
    unchanged = []

    for name, new_hash in after.items():
        if name not in before:
            added.append(name)
        elif before[name] != new_hash:
            modified.append(name)
        else:
            unchanged.append(name)

    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "unchanged": sorted(unchanged),
    }