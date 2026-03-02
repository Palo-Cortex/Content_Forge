from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List


def ensure_staging_pack(staging_root: Path, staging_pack: str) -> Path:
    """Create minimal pack skeleton at <staging_root>/Packs/<staging_pack> and return pack root."""
    packs_root = staging_root / "Packs"
    pack_root = packs_root / staging_pack

    (pack_root / "Playbooks").mkdir(parents=True, exist_ok=True)
    (pack_root / "ReleaseNotes").mkdir(parents=True, exist_ok=True)

    meta_path = pack_root / "pack_metadata.json"
    if not meta_path.exists():
        metadata = {
            "name": staging_pack,
            "description": f"Staging pack for {staging_pack}",
            "support": "xsoar",
            "currentVersion": "1.0.0",
            "author": "Content Forge",
            "url": "",
            "email": "",
            "categories": [],
            "tags": [],
            "useCases": [],
            "keywords": [],
        }
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return pack_root


def stage_ingest_playbooks(ingest_dir: Path, staging_playbooks_dir: Path) -> List[Path]:
    """Copy .yml/.yaml files from ingest into staging Playbooks dir. Returns staged file paths."""
    staged: List[Path] = []
    staging_playbooks_dir.mkdir(parents=True, exist_ok=True)

    if not ingest_dir.exists():
        return staged

    # allow ingest to contain arbitrary subfolders
    for p in sorted(ingest_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".yml", ".yaml"):
            continue
        dest = staging_playbooks_dir / p.name
        shutil.copy2(p, dest)
        staged.append(dest)

    return staged
