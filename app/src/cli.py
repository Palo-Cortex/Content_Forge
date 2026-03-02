from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from app.src.diff import compute_diff, hash_playbooks
from app.src.graph import build_repo_graph, compare_graphs, simulate_repo_with_staging
from app.src.impact import find_pack_playbooks_referencing_ids
from app.src.integrity import analyze_playbook_integrity
from app.src.normalize import normalize_pack
from app.src.playbook_refs import is_playbook_yaml, parse_playbook_refs
from app.src.platform_allowlist import DEFAULT_ALLOWLIST
from app.src.repo_index import build_symbol_table, iter_playbook_files
from app.src.rewrite import apply_mapping_across_files, build_id_normalization_map
from app.src.sdk_gate import run_validate
from app.src.semantic_diff import semantic_diff, snapshot_playbook
from app.src.staging import ensure_staging_pack, stage_ingest_playbooks
from app.src.fixer import heal_playbooks_min_fromversion


# -------------------------
# Path resolution
# -------------------------

def _resolve_submission() -> str:
    return (os.environ.get("INGEST_SUBMISSION") or os.environ.get("SUBMISSION") or "default").strip() or "default"


def _resolve_ingest_dir() -> Path:
    sub = _resolve_submission()
    raw = os.environ.get("INGEST_DIR") or os.environ.get("ingest_dir")
    if raw:
        return Path(raw)
    return Path("/workspace/ingest") / sub


def _resolve_staging_dir() -> Path:
    sub = _resolve_submission()
    raw = os.environ.get("STAGING_DIR") or os.environ.get("staging_dir")
    if raw:
        p = Path(raw)
        return p if p.name == sub else p / sub
    return Path("/workspace/staging") / sub


def _resolve_output_dir() -> Path:
    sub = _resolve_submission()
    raw = os.environ.get("OUTPUT_DIR") or os.environ.get("output_dir")
    if raw:
        p = Path(raw)
        return p if p.name == sub else p / sub
    return Path("/workspace/output") / sub


def _repo_dir() -> Path:
    return Path(os.environ.get("REPO_DIR") or "/workspace/secops-framework")


def _target_pack() -> str:
    return os.environ.get("TARGET_PACK", "soc-optimization-unified")


def _staging_pack() -> str:
    target = _target_pack()
    return os.environ.get("STAGING_PACK", f"{target}_ingest")


def _exclude_packs() -> set[str]:
    include_fixtures = os.environ.get("INCLUDE_FIXTURES", "0").strip() == "1"
    default_exclude = "content-forge-fixtures,content-forge-fixtures_ingest"
    raw = os.environ.get("EXCLUDE_PACKS", "" if include_fixtures else default_exclude)
    s = {p.strip() for p in raw.split(",") if p.strip()}
    s.discard(_target_pack())
    s.discard(_staging_pack())
    return s


def _is_in_excluded_pack(path: Path) -> bool:
    p = str(path).replace("\\", "/")
    for name in _exclude_packs():
        if f"/Packs/{name}/" in p:
            return True
    return False


def _find_quoted_header_ids(playbook_path: Path, max_lines: int = 80) -> bool:
    try:
        lines = playbook_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    for line in lines[:max_lines]:
        if line.startswith("tasks:"):
            break
        if line.strip().startswith("id:") and ('"' in line or "'" in line):
            return True
    return False


# -------------------------
# Commands
# -------------------------

def doctor() -> int:
    repo_dir = _repo_dir()
    ingest_dir = _resolve_ingest_dir()
    staging_dir = _resolve_staging_dir()
    output_dir = _resolve_output_dir()

    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    target_pack = _target_pack()
    staging_pack = _staging_pack()

    pack_root = repo_dir / "Packs" / target_pack
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_pack_root = ensure_staging_pack(staging_dir, staging_pack)

    # Stage (read-only behavior relative to ingest; we overwrite staging playbooks each time)
    staging_playbooks_dir = staging_pack_root / "Playbooks"
    if staging_playbooks_dir.exists():
        shutil.rmtree(staging_playbooks_dir)
    staging_playbooks_dir.mkdir(parents=True, exist_ok=True)

    staged_paths = stage_ingest_playbooks(ingest_dir, staging_playbooks_dir)
    staged_playbooks = [p for p in staged_paths if is_playbook_yaml(p)]

    pack_playbooks = list(iter_playbook_files(pack_root))
    repo_playbooks = [
        p for p in list(iter_playbook_files(repo_dir))
        if f"/Packs/{staging_pack}/" not in str(p).replace("\\", "/")
        and not _is_in_excluded_pack(p)
    ]

    id_map = build_id_normalization_map(repo_playbooks + staged_playbooks)
    old_ids = set(id_map.keys())
    impacted_repo_playbooks = find_pack_playbooks_referencing_ids(repo_playbooks, old_ids)

    missing: list[dict] = []
    platform_refs: list[dict] = []
    external_refs: list[dict] = []

    allow = DEFAULT_ALLOWLIST
    symbol_table = build_symbol_table(repo_dir / "Packs")

    platform_scripts = allow.platform_scripts
    external_playbooks_by_name = allow.external_playbooks_by_name

    for pb in staged_playbooks:
        parsed = parse_playbook_refs(pb)

        for sub_id in parsed["refs"]["playbooks_by_id"]:
            if sub_id not in symbol_table["playbooks_by_id"] and sub_id not in id_map:
                missing.append({"file": str(pb), "type": "playbook_id", "ref": sub_id})

        for sub_name in parsed["refs"]["playbooks_by_name"]:
            if sub_name in external_playbooks_by_name:
                external_refs.append({"file": str(pb), "type": "playbook_name", "ref": sub_name})
                continue
            if sub_name not in symbol_table["playbooks_by_name"]:
                missing.append({"file": str(pb), "type": "playbook_name", "ref": sub_name})

        for scr in parsed["refs"]["scripts"]:
            if scr in platform_scripts:
                platform_refs.append({"file": str(pb), "type": "script", "ref": scr})
                continue
            if scr not in symbol_table["scripts_by_name"]:
                missing.append({"file": str(pb), "type": "script", "ref": scr})

    report = {
        "mode": "doctor",
        "target_pack": target_pack,
        "staging_pack": staging_pack,
        "submission": _resolve_submission(),
        "counts": {
            "staged_playbooks": len(staged_playbooks),
            "pack_playbooks": len(pack_playbooks),
            "id_mappings": len(id_map),
            "impacted_repo_playbooks": len(impacted_repo_playbooks),
            "missing_refs": len(missing),
            "platform_refs": len(platform_refs),
            "external_refs": len(external_refs),
        },
        "missing": missing,
        "platform": platform_refs,
        "external": external_refs,
        "impacted_repo_playbooks": [str(p) for p in impacted_repo_playbooks],
    }

    out = output_dir / "doctor_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote: {out}")
    print(f"Missing refs: {len(missing)} | Platform refs: {len(platform_refs)} | External refs: {len(external_refs)}")
    return 0


def fix() -> int:
    repo_dir = _repo_dir()
    ingest_dir = _resolve_ingest_dir()
    staging_dir = _resolve_staging_dir()
    output_dir = _resolve_output_dir()

    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    target_pack = _target_pack()
    staging_pack = _staging_pack()

    pack_root = repo_dir / "Packs" / target_pack
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_pack_root = ensure_staging_pack(staging_dir, staging_pack)

    # Always restage fresh from ingest
    staging_playbooks_dir = staging_pack_root / "Playbooks"
    if staging_playbooks_dir.exists():
        shutil.rmtree(staging_playbooks_dir)
    staging_playbooks_dir.mkdir(parents=True, exist_ok=True)

    staged_paths = stage_ingest_playbooks(ingest_dir, staging_playbooks_dir)
    staged_playbooks = [p for p in staged_paths if is_playbook_yaml(p)]

    # Normalize IDs and references on staged playbooks
    pack_playbooks = list(iter_playbook_files(pack_root))
    id_map = build_id_normalization_map(pack_playbooks + staged_playbooks)

    if id_map:
        print("\nID Normalization Map:")
        for old, new in id_map.items():
            print(f"  {old}  →  {new}")
    else:
        print("\nNo UUID → name normalization needed.")

    apply_mapping_across_files(staged_playbooks, id_map)

    # Normalize pack boilerplate + playbook headers
    normalize_pack(staging_pack_root, staged_playbooks)

    # Deterministic BA106 healing on staged playbooks (prevents promote loop)
    healed = heal_playbooks_min_fromversion(staged_playbooks, min_version="5.0.0")
    if healed:
        print(f"Healed fromversion on {healed} staged playbook(s).")

    # Guardrail: prevent quoted id: in playbook headers
    quoted = [str(pb) for pb in staged_playbooks if _find_quoted_header_ids(pb)]
    if quoted:
        outp = output_dir / "quoted_id_playbooks.json"
        outp.write_text(json.dumps(quoted, indent=2), encoding="utf-8")
        print("ABORTING: Detected quoted id: in playbook header(s). See:", outp)
        for q in quoted:
            print("  -", q)
        return 6

    # Validate staging pack (must be clean to promote)
    code, validate_out = run_validate(staging_dir, f"Packs/{staging_pack}")
    (output_dir / "fix_validate_output.txt").write_text(validate_out, encoding="utf-8")

    if code != 0:
        print(validate_out)
        print("Staging validate FAILED after fix.")
        return code

    print("Fix successful. Staging pack clean.")
    return 0


def promote(force: bool = False, dry_run: bool = False) -> int:
    repo_dir = _repo_dir()
    staging_dir = _resolve_staging_dir()
    output_dir = _resolve_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    target_pack = _target_pack()
    staging_pack = _staging_pack()

    pack_root = repo_dir / "Packs" / target_pack
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_pack_root = ensure_staging_pack(staging_dir, staging_pack)
    staging_playbooks_dir = staging_pack_root / "Playbooks"
    if not staging_playbooks_dir.exists():
        print("[ERROR] Staging Playbooks missing. Run `fix` first.")
        return 2

    staged_playbooks = [p for p in sorted(staging_playbooks_dir.glob("*.yml")) if is_playbook_yaml(p)]

    # Validate staging pack before promoting (should already be clean)
    code, validate_out = run_validate(staging_dir, f"Packs/{staging_pack}")
    (output_dir / "promote_validate_staging.txt").write_text(validate_out, encoding="utf-8")
    if code != 0:
        print("Staging validate FAILED. Run fix first.")
        return code

    # Diff safety
    before_hashes = hash_playbooks(pack_root)
    after_hashes = hash_playbooks(staging_pack_root)
    diff = compute_diff(before_hashes, after_hashes)
    total_changes = len(diff["added"]) + len(diff["modified"])

    diff_report = {
        "added": diff["added"],
        "modified": diff["modified"],
        "unchanged": diff["unchanged"],
        "total_changes": total_changes,
    }
    diff_path = output_dir / "promotion_diff.json"
    diff_path.write_text(json.dumps(diff_report, indent=2), encoding="utf-8")
    print(f"Promotion diff written to: {diff_path}")
    print(f"Total Changes: {total_changes}")

    max_allowed = int(os.environ.get("MAX_ALLOWED_CHANGES", "20"))
    if total_changes > max_allowed and not force:
        print(f"ABORTING: Too many changes ({total_changes})")
        print("Re-run with --force to override.")
        return 3

    # Graph integrity simulation
    print("Running repository graph integrity check...")
    before_graph = build_repo_graph(repo_dir)
    temp_repo = simulate_repo_with_staging(repo_dir, staging_pack_root)

    repo_playbooks = [
        p for p in iter_playbook_files(repo_dir)
        if f"/Packs/{staging_pack}/" not in str(p).replace("\\", "/")
    ]
    repo_playbooks = [p for p in repo_playbooks if not _is_in_excluded_pack(p)]

    id_map = build_id_normalization_map(repo_playbooks + staged_playbooks)
    old_ids = set(id_map.keys())
    impacted_repo_playbooks = find_pack_playbooks_referencing_ids(repo_playbooks, old_ids)

    # Rewrite dependents in temp repo for graph check only
    temp_impacted: list[Path] = []
    for p in impacted_repo_playbooks:
        try:
            rel = p.relative_to(repo_dir)
        except ValueError:
            continue
        tp = temp_repo / rel
        if tp.exists():
            temp_impacted.append(tp)

    if temp_impacted and id_map:
        _ = apply_mapping_across_files(temp_impacted, id_map)

    if impacted_repo_playbooks and not force and id_map:
        print("Detected dependent playbooks that reference old IDs.")
        (output_dir / "impacted_dependents.json").write_text(
            json.dumps([str(p) for p in impacted_repo_playbooks], indent=2),
            encoding="utf-8",
        )
        print("ABORTING (run with --force to proceed).")
        return 6

    after_graph = build_repo_graph(temp_repo)

    focus_nodes = set()
    for pb in staged_playbooks:
        d = parse_playbook_refs(pb)
        if d.get("id"):
            focus_nodes.add(str(d["id"]))
    for p in impacted_repo_playbooks:
        d = parse_playbook_refs(p)
        if d.get("id"):
            focus_nodes.add(str(d["id"]))

    broken = compare_graphs(before_graph, after_graph, focus_nodes=focus_nodes)
    if broken:
        print("Graph integrity violation detected:")
        for b in broken:
            print(b)
        print("ABORTING due to broken dependency edges.")
        return 4
    print("Graph integrity check passed.")

    # Semantic diff
    semantic_report = {}
    real_pb_dir = pack_root / "Playbooks"
    for pb in staged_playbooks:
        real_path = real_pb_dir / pb.name
        if real_path.exists():
            before_snap = snapshot_playbook(real_path)
            after_snap = snapshot_playbook(pb)
            d = semantic_diff(before_snap, after_snap)
            if any(d[k] for k in d):
                semantic_report[pb.name] = d
        else:
            semantic_report[pb.name] = {"new_playbook": True}

    semantic_path = output_dir / "semantic_diff.json"
    semantic_path.write_text(json.dumps(semantic_report, indent=2), encoding="utf-8")
    print(f"Semantic diff written to: {semantic_path}")

    # Integrity report
    print("Running playbook integrity checks...")
    integrity_report = {}
    hard_fail = False
    for pb in staged_playbooks:
        real_path = real_pb_dir / pb.name
        if real_path.exists():
            integrity = analyze_playbook_integrity(real_path, pb)
            if integrity.get("dangling_old_id_reference"):
                hard_fail = True
            if any(integrity.values()):
                integrity_report[pb.name] = integrity

    integrity_path = output_dir / "integrity_report.json"
    integrity_path.write_text(json.dumps(integrity_report, indent=2), encoding="utf-8")
    print(f"Integrity report written to: {integrity_path}")

    if hard_fail:
        print("ABORTING: Dangling old playbook ID detected.")
        return 5

    if dry_run:
        print("DRY RUN: skipping copy into real pack and final pack validate.")
        return 0

    # Copy staged playbooks into repo pack (real mutation point)
    real_pb_dir.mkdir(parents=True, exist_ok=True)
    for pb in staged_playbooks:
        shutil.copy2(pb, real_pb_dir / pb.name)

    # Final validate of target pack in repo (should pass; promote does not "fix")
    final_code, final_out = run_validate(repo_dir, f"Packs/{target_pack}")
    (output_dir / "promote_validate_repo.txt").write_text(final_out, encoding="utf-8")
    print(final_out)
    print(f"Final validate exit code: {final_code}")
    return final_code


def accept(apply: bool = False) -> int:
    output_dir = _resolve_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Running doctor...")
    d_code = doctor()
    if d_code != 0:
        print("Doctor failed.")
        return d_code

    doctor_report_path = output_dir / "doctor_report.json"
    doctor_report = {}
    if doctor_report_path.exists():
        doctor_report = json.loads(doctor_report_path.read_text(encoding="utf-8"))

    missing = doctor_report.get("counts", {}).get("missing_refs", 0)
    if missing > 0:
        print(f"Blocking accept: {missing} missing refs.")
        return 4

    print("Running fix...")
    f_code = fix()
    if f_code != 0:
        print("Fix/validate failed.")
        return f_code

    print("Running promote...")
    promote_code = promote(force=False, dry_run=not apply)
    if promote_code != 0:
        print("Promote failed.")
        return promote_code

    receipt = {
        "target_pack": _target_pack(),
        "staging_pack": _staging_pack(),
        "apply": apply,
        "doctor_counts": doctor_report.get("counts", {}),
        "receipt_version": 1,
        "submission": _resolve_submission(),
    }

    receipt_path = output_dir / "acceptance_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"Acceptance receipt written to: {receipt_path}")
    print("ACCEPT complete.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.src.cli <command> [--force] [--dry-run] [--apply]")
        print("Commands: doctor, fix, promote, accept")
        return 2

    cmd = sys.argv[1].lower()

    if cmd == "accept":
        apply = "--apply" in sys.argv[2:]
        return accept(apply=apply)

    force = "--force" in sys.argv[2:]
    dry_run = "--dry-run" in sys.argv[2:]

    if cmd == "doctor":
        return doctor()
    if cmd == "fix":
        return fix()
    if cmd == "promote":
        return promote(force=force, dry_run=dry_run)

    print(f"Unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
