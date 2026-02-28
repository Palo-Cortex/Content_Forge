from pathlib import Path
import re


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

BA106_RE = re.compile(
    r"(Packs/[^:]+):.*?\[BA106\].*?need at least (\d+\.\d+\.\d+)",
    re.IGNORECASE,
)


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def fix_fromversion(file_path: Path, min_version: str):
    lines = file_path.read_text(encoding="utf-8").splitlines()

    # If fromversion already exists, update it
    for i, line in enumerate(lines):
        if line.strip().startswith("fromversion:"):
            lines[i] = f"fromversion: {min_version}"
            file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

    # Otherwise insert after id: line
    for i, line in enumerate(lines):
        if line.strip().startswith("id:"):
            lines.insert(i + 1, f"fromversion: {min_version}")
            file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return


def run_fixes(repo_root: Path, validate_output: str):
    changed = 0

    for raw_line in validate_output.splitlines():
        line = strip_ansi(raw_line)

        m = BA106_RE.search(line)
        if not m:
            continue

        rel_path = m.group(1)
        min_ver = m.group(2)

        file_path = repo_root / rel_path

        if file_path.exists():
            fix_fromversion(file_path, min_ver)
            changed += 1

    return changed