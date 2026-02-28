from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List


def ensure_staging_pack(repo_dir: Path, staging_pack: str) -> Path:
    """
    Ensure a valid pack skeleton exists so demisto-sdk validate can run on it.
    Creates Packs/<staging_pack> via demisto-sdk init if missing.
    """
    packs_root = repo_dir / "Packs"
    pack_root = packs_root / staging_pack

    packs_root.mkdir(parents=True, exist_ok=True)

    if not pack_root.exists():
        env = os.environ.copy()
        env["DEMISTO_SDK_CONTENT_PATH"] = str(repo_dir)
        env.setdefault("DEMISTO_SDK_IGNORE_CONTENT_WARNING", "true")

        # demisto-sdk init creates pack skeleton under Packs/<pack>.
        # If your SDK uses different flags, the error output will show the correct usage.
        cmd = ["demisto-sdk", "init", "--pack", staging_pack]
        p = subprocess.run(
            cmd,
            cwd=str(repo_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if p.returncode != 0:
            raise RuntimeError(f"Failed to init staging pack:\n{p.stdout}")

    (pack_root / "Playbooks").mkdir(parents=True, exist_ok=True)
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