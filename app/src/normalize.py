# app/src/normalize.py

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List


FROMVERSION_RE = re.compile(r'(?mi)^(?P<indent>\s*)fromVersion\s*:\s*(?P<val>[^\n#]+)')
FROMSERVER_RE = re.compile(r'(?mi)^(?P<indent>\s*)fromServerVersion\s*:\s*(?P<val>[^\n#]+)')
NAME_RE = re.compile(r'(?mi)^(?P<indent>\s*)name\s*:\s*(?P<val>[^\n#]+)')
ID_RE = re.compile(r'(?mi)^(?P<indent>\s*)id\s*:\s*(?P<val>[^\n#]+)')


def ensure_pack_boilerplate(pack_root: Path):
    required = {
        ".pack-ignore": "",
        ".secrets-ignore": "",
        "README.md": f"# {pack_root.name}\n",
    }

    for fname, content in required.items():
        fpath = pack_root / fname
        if not fpath.exists():
            fpath.write_text(content, encoding="utf-8")


def normalize_playbook(path: Path):
    text = path.read_text(encoding="utf-8")

    # ---- Ensure fromVersion exists and >= 5.0.0 ----
    min_version = "5.0.0"

    m_from = FROMVERSION_RE.search(text)
    if m_from:
        val = m_from.group("val").strip().strip('"').strip("'")
        if val < min_version:
            start, end = m_from.span("val")
            text = text[:start] + min_version + text[end:]
    else:
        m_server = FROMSERVER_RE.search(text)
        insert_version = min_version
        if m_server:
            server_val = m_server.group("val").strip().strip('"').strip("'")
            insert_version = max(server_val, min_version)

        # insert after version field
        lines = text.splitlines(True)
        for i, line in enumerate(lines):
            if line.lower().startswith("version:"):
                lines.insert(i + 1, f"fromVersion: {insert_version}\n")
                break
        text = "".join(lines)

    # ---- Ensure id == name ----
    m_name = NAME_RE.search(text)
    m_id = ID_RE.search(text)

    if m_name:
        name_val = m_name.group("val").strip()
        if m_id:
            id_val = m_id.group("val").strip()
            if id_val != name_val:
                start, end = m_id.span("val")
                text = text[:start] + name_val + text[end:]
        else:
            # Insert id under name
            idx = m_name.end()
            text = text[:idx] + f"\nid: {name_val}" + text[idx:]

    path.write_text(text, encoding="utf-8")


def normalize_pack(pack_root: Path, playbooks: List[Path]):
    ensure_pack_boilerplate(pack_root)

    for pb in playbooks:
        normalize_playbook(pb)