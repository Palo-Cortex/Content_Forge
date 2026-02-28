import subprocess
from pathlib import Path
from typing import Tuple


def run_validate(content_repo_root: Path, validate_target: str) -> Tuple[int, str]:

    # IMPORTANT:
    # - Run from repo root
    # - Pass relative path
    # - Do NOT pass absolute path
    # - Do NOT use content-path flag

    relative_target = str(validate_target)

    cmd = [
        "demisto-sdk",
        "validate",
        "-i",
        relative_target,
    ]

    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(content_repo_root),  # THIS IS THE KEY
    )

    return p.returncode, p.stdout