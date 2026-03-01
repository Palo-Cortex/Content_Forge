from pathlib import Path
import re
import subprocess


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

BA106_RE = re.compile(r"(Packs/[^:]+):.*?\[BA106\].*?need at least (\d+\.\d+\.\d+)", re.IGNORECASE)
BA101_RE = re.compile(r"(Packs/[^:]+):.*?\[BA101\]", re.IGNORECASE)
PA128_RE = re.compile(r"(Packs/[^:]+):.*?\[PA128\]", re.IGNORECASE)
BA102_RE = re.compile(r"(Packs/[^:]+):.*?\[BA102\]", re.IGNORECASE)


def strip_ansi(line: str) -> str:
    return ANSI_RE.sub("", line)


# -------------------------
# BA106 — fromversion
# -------------------------

def fix_fromversion(file_path: Path, min_version: str):
    try:
        doc = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            return False

        if doc.get("fromversion") != min_version:
            doc["fromversion"] = min_version
            file_path.write_text(
                yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            return True

        return False

    except Exception:
        return False


# -------------------------
# BA101 — name must equal id
# -------------------------

import yaml


import yaml


def fix_id_equals_name(file_path: Path):
    try:
        doc = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            return False

        name = doc.get("name")
        if not name:
            return False

        if doc.get("id") != name:
            doc["id"] = name
            file_path.write_text(
                yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            return True

        return False

    except Exception:
        return False


# -------------------------
# PA128 — required pack files
# -------------------------

def ensure_pack_files(pack_root: Path):
    changed = False

    required = {
        ".pack-ignore": "# auto-generated\n",
        ".secrets-ignore": "",
        "README.md": f"# {pack_root.name}\n",
    }

    for fname, content in required.items():
        fpath = pack_root / fname
        if not fpath.exists():
            fpath.write_text(content, encoding="utf-8")
            changed = True

    return changed


# -------------------------
# BA102 — formatting
# -------------------------

def run_format(file_path: Path):
    cmd = [
        "demisto-sdk",
        "format",
        "-i",
        str(file_path),
        "--assume-yes",
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    return result.returncode == 0


# -------------------------
# Main Repair Loop
# -------------------------

def run_fixes(repo_root: Path, validate_output: str) -> int:
    changed = 0

    for raw in validate_output.splitlines():
        line = strip_ansi(raw)

        # BA106
        m = BA106_RE.search(line)
        if m:
            rel_path, min_ver = m.groups()
            file_path = repo_root / rel_path
            if file_path.exists() and fix_fromversion(file_path, min_ver):
                changed += 1
            continue

        # BA101
        m = BA101_RE.search(line)
        if m:
            rel_path = m.group(1)
            file_path = repo_root / rel_path
            if file_path.exists() and fix_id_equals_name(file_path):
                changed += 1
            continue

        # PA128
        m = PA128_RE.search(line)
        if m:
            rel_path = m.group(1)
            pack_root = repo_root / rel_path
            if pack_root.exists() and ensure_pack_files(pack_root):
                changed += 1
            continue

        # BA102
        m = BA102_RE.search(line)
        if m:
            rel_path = m.group(1)
            file_path = repo_root / rel_path
            if file_path.exists() and run_format(file_path):
                changed += 1
            continue

    return changed