from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from app.src.fixer import run_fixes
from app.src.impact import find_pack_playbooks_referencing_ids
from app.src.normalize import normalize_pack
from app.src.playbook_refs import is_playbook_yaml, parse_playbook_refs
from app.src.repo_index import build_symbol_table, iter_playbook_files
from app.src.rewrite import apply_mapping_across_files, build_id_normalization_map
from app.src.sdk_gate import run_validate
from app.src.staging import ensure_staging_pack, stage_ingest_playbooks

REPO_DIR = Path(os.environ.get("REPO_DIR", "/workspace/secops-framework"))
INGEST_DIR = Path(os.environ.get("INGEST_DIR", "/workspace/ingest"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/workspace/output"))
TARGET_PACK = os.environ.get("TARGET_PACK", "soc-optimization-unified")
STAGING_PACK = os.environ.get("STAGING_PACK", f"{TARGET_PACK}_ingest")


def _stage_fresh_playbooks(staging_root: Path) -> list[Path]:
    """
    Recreate staging Playbooks/ from INGEST_DIR and return staged YAML paths.
    This is the ONLY place we delete/recreate staging Playbooks.
    """
    staging_playbooks_dir = staging_root / "Playbooks"

    if staging_playbooks_dir.exists():
        shutil.rmtree(staging_playbooks_dir)
    staging_playbooks_dir.mkdir(parents=True, exist_ok=True)

    staged_files = stage_ingest_playbooks(INGEST_DIR, staging_playbooks_dir)
    staged_playbooks = [p for p in staged_files if is_playbook_yaml(p)]
    return staged_playbooks


def doctor() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pack_root = REPO_DIR / "Packs" / TARGET_PACK
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_root = ensure_staging_pack(REPO_DIR, STAGING_PACK)
    staged_playbooks = _stage_fresh_playbooks(staging_root)

    pack_playbooks = iter_playbook_files(pack_root)

    id_map = build_id_normalization_map(pack_playbooks + staged_playbooks)
    old_ids = set(id_map.keys())
    impacted_pack_playbooks = find_pack_playbooks_referencing_ids(pack_playbooks, old_ids)

    missing: list[dict] = []
    symbol_table = build_symbol_table(pack_root)

    for pb in staged_playbooks:
        parsed = parse_playbook_refs(pb)

        for sub_id in parsed["refs"]["playbooks_by_id"]:
            if sub_id not in symbol_table["playbooks_by_id"] and sub_id not in id_map:
                missing.append({"file": str(pb), "type": "playbook_id", "ref": sub_id})

        for sub_name in parsed["refs"]["playbooks_by_name"]:
            if sub_name not in symbol_table["playbooks_by_name"]:
                missing.append({"file": str(pb), "type": "playbook_name", "ref": sub_name})

        for scr in parsed["refs"]["scripts"]:
            if scr not in symbol_table["scripts_by_name"]:
                missing.append({"file": str(pb), "type": "script", "ref": scr})

    report = {
        "mode": "doctor",
        "target_pack": TARGET_PACK,
        "staging_pack": STAGING_PACK,
        "counts": {
            "staged_playbooks": len(staged_playbooks),
            "pack_playbooks": len(pack_playbooks),
            "id_mappings": len(id_map),
            "impacted_pack_playbooks": len(impacted_pack_playbooks),
            "missing_refs": len(missing),
        },
        "id_map_sample": list(id_map.items())[:25],
        "impacted_pack_playbooks": [str(p) for p in impacted_pack_playbooks],
        "missing": missing,
    }

    out = OUTPUT_DIR / "doctor_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote: {out}")
    print(f"Staged playbooks: {len(staged_playbooks)}")
    print(f"ID mappings: {len(id_map)}")
    print(f"Impacted pack playbooks: {len(impacted_pack_playbooks)}")
    print(f"Missing refs: {len(missing)}")
    return 0


def fix() -> int:
    """
    The ONLY command that mutates staging content.
    - stages fresh from ingest
    - normalizes IDs / names and other rewrites
    - runs validate
    - runs internal fixer (run_fixes) using validate output
    - re-validates
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pack_root = REPO_DIR / "Packs" / TARGET_PACK
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_root = ensure_staging_pack(REPO_DIR, STAGING_PACK)
    staged_playbooks = _stage_fresh_playbooks(staging_root)

    # Build id normalization map using real pack + staged playbooks
    pack_playbooks = iter_playbook_files(pack_root)
    id_map = build_id_normalization_map(pack_playbooks + staged_playbooks)

    # Rewrite staged playbooks (ID/name normalization etc.)
    apply_mapping_across_files(staged_playbooks, id_map)

    # Copy impacted pack playbooks into staging, rewrite copies (so validate sees consistent refs)
    old_ids = set(id_map.keys())
    impacted_pack_playbooks = find_pack_playbooks_referencing_ids(pack_playbooks, old_ids)

    staged_impacted_dir = staging_root / "_impacted_pack_playbooks"
    if staged_impacted_dir.exists():
        shutil.rmtree(staged_impacted_dir)
    staged_impacted_dir.mkdir(parents=True, exist_ok=True)

    impacted_copies: list[Path] = []
    for pb in impacted_pack_playbooks:
        dest = staged_impacted_dir / Path(pb).name
        shutil.copy2(pb, dest)
        impacted_copies.append(dest)

    apply_mapping_across_files(impacted_copies, id_map)

    # Normalize pack metadata / required files etc. before validate
    normalize_pack(staging_root, staged_playbooks)

    # Validate staging pack
    code, validate_out = run_validate(REPO_DIR, f"Packs/{STAGING_PACK}")
    (OUTPUT_DIR / "fix_validate_output.txt").write_text(validate_out, encoding="utf-8")

    if code == 0:
        print("Nothing to fix. Staging validate clean.")
        return 0

    # Run internal fixer against validate output (BA106 etc.)
    print("Running internal fixer...")
    changed = run_fixes(REPO_DIR, validate_out)
    print(f"Files modified: {changed}")

    # Re-validate
    code, validate_out = run_validate(REPO_DIR, f"Packs/{STAGING_PACK}")
    (OUTPUT_DIR / "fix_validate_output_after.txt").write_text(validate_out, encoding="utf-8")

    if code != 0:
        print("Still failing after fix.")
        print(f"See: {OUTPUT_DIR / 'fix_validate_output_after.txt'}")
        return code

    print("Fix successful. Staging pack clean.")
    return 0


def promote() -> int:
    """
    Promote assumes staging is already prepared (typically by `fix`).
    It DOES NOT restage from ingest, and DOES NOT re-run fixers.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pack_root = REPO_DIR / "Packs" / TARGET_PACK
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_root = ensure_staging_pack(REPO_DIR, STAGING_PACK)
    staging_playbooks_dir = staging_root / "Playbooks"

    if not staging_playbooks_dir.exists() or not any(staging_playbooks_dir.glob("*.yml")):
        print("[ERROR] Staging Playbooks are missing/empty. Run `fix` first.")
        return 2

    staged_playbooks = [p for p in staging_playbooks_dir.glob("*.yml") if is_playbook_yaml(p)]

    # Validate staging pack (again) before touching real pack
    code, validate_out = run_validate(REPO_DIR, f"Packs/{STAGING_PACK}")
    (OUTPUT_DIR / "staging_validate_output.txt").write_text(validate_out, encoding="utf-8")

    if code != 0:
        print("Staging validate FAILED. Not touching real pack.")
        print(f"See: {OUTPUT_DIR / 'staging_validate_output.txt'}")
        return code

    # Promote staged playbooks into real pack
    real_pb_dir = pack_root / "Playbooks"
    real_pb_dir.mkdir(parents=True, exist_ok=True)

    for pb in staged_playbooks:
        shutil.copy2(pb, real_pb_dir / pb.name)

    # Final validate on real pack
    final_code, final_out = run_validate(REPO_DIR, f"Packs/{TARGET_PACK}")
    (OUTPUT_DIR / "final_validate_output.txt").write_text(final_out, encoding="utf-8")
    print(final_out)
    print(f"Final validate exit code: {final_code}")
    return final_code


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.src.cli <command>\nCommands: doctor, fix, promote")
        return 2

    cmd = sys.argv[1].lower()
    if cmd == "doctor":
        return doctor()
    if cmd == "fix":
        return fix()
    if cmd == "promote":
        return promote()

    print(f"Unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())