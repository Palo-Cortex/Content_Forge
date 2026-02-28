from __future__ import annotations

import shutil
import json
from pathlib import Path
from typing import List


def ensure_staging_pack(repo_dir: Path, staging_pack: str) -> Path:
    """
    Ensure a valid staging pack skeleton exists.
    Pure filesystem creation. No demisto-sdk init.
    """

    packs_root = repo_dir / "Packs"
    pack_root = packs_root / staging_pack

    packs_root.mkdir(parents=True, exist_ok=True)
    pack_root.mkdir(parents=True, exist_ok=True)

    # Required subfolders
    (pack_root / "Playbooks").mkdir(parents=True, exist_ok=True)
    (pack_root / "ReleaseNotes").mkdir(parents=True, exist_ok=True)

    # Required pack_metadata.json (PA107 compliant)
    pack_meta = pack_root / "pack_metadata.json"

    metadata = {
        "name": staging_pack,
        "description": "Auto-generated staging pack",
        "support": "xsoar",
        "currentVersion": "1.0.0",
        "author": "Content Forge",
        "url": "https://internal.local/staging",
        "categories": ["Security"],
        "tags": ["SOC"],
        "useCases": ["SOC"],
        "keywords": ["SOC", "Automation"],
        "marketplaces": ["xsoar", "marketplacev2"]
    }

    pack_meta.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8"
    )

    # Required support files
    (pack_root / "README.md").touch(exist_ok=True)
    (pack_root / ".pack-ignore").touch(exist_ok=True)
    (pack_root / ".secrets-ignore").touch(exist_ok=True)

    return pack_root


def stage_ingest_playbooks(ingest_dir: Path, staging_playbooks_dir: Path) -> List[Path]:
    """
    Copy YAML files from ingest into the staging Playbooks directory.
    Returns a list of staged file paths (never None).
    """
    staged: List[Path] = []
    staging_playbooks_dir.mkdir(parents=True, exist_ok=True)

    if not ingest_dir.exists():
        return staged

    for p in sorted(ingest_dir.glob("**/*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".yml", ".yaml"):
            continue

        dest = staging_playbooks_dir / p.name
        shutil.copy2(p, dest)
        staged.append(dest)

    return staged