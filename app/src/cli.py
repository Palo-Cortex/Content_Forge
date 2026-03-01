import json
import re
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
from app.src.diff import hash_playbooks, compute_diff
from app.src.integrity import analyze_playbook_integrity
from app.src.semantic_diff import snapshot_playbook, semantic_diff
from app.src.platform_allowlist import DEFAULT_ALLOWLIST
from app.src.graph import (
    build_repo_graph,
    compare_graphs,
    simulate_repo_with_staging,
)

BASE_DIR = Path(os.environ.get("BASE_DIR", Path.cwd()))

REPO_DIR = Path(os.environ.get("REPO_DIR", BASE_DIR / "secops-framework"))
INGEST_SUBMISSION = os.environ.get("INGEST_SUBMISSION", "").strip()

# Ingest
DEFAULT_INGEST_DIR = BASE_DIR / "ingest"
if INGEST_SUBMISSION:
    INGEST_DIR = Path(os.environ.get("INGEST_DIR", DEFAULT_INGEST_DIR / "submissions" / INGEST_SUBMISSION))
else:
    INGEST_DIR = Path(os.environ.get("INGEST_DIR", DEFAULT_INGEST_DIR))

# Output (namespaced by submission to avoid collisions)
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
if INGEST_SUBMISSION:
    OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", DEFAULT_OUTPUT_DIR / "submissions" / INGEST_SUBMISSION))
else:
    OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", DEFAULT_OUTPUT_DIR))

TARGET_PACK = os.environ.get("TARGET_PACK", "soc-optimization-unified")
STAGING_PACK = os.environ.get("STAGING_PACK", f"{TARGET_PACK}_ingest")

# ------------------------------------------------------------
# Repo-global acceptance controls
# ------------------------------------------------------------
# Default: exclude fixtures packs from repo-impact checks unless explicitly testing.
INCLUDE_FIXTURES = os.environ.get("INCLUDE_FIXTURES", "0").strip() == "1"
_DEFAULT_EXCLUDE = "content-forge-fixtures,content-forge-fixtures_ingest"
_excl_raw = os.environ.get("EXCLUDE_PACKS", "" if INCLUDE_FIXTURES else _DEFAULT_EXCLUDE)
EXCLUDE_PACKS = {p.strip() for p in _excl_raw.split(",") if p.strip()}

# Never exclude the active target/staging packs (avoid self-exclusion when testing fixtures)
EXCLUDE_PACKS.discard(TARGET_PACK)
EXCLUDE_PACKS.discard(STAGING_PACK)



# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _resolve_ingest_dir() -> Path:
    """Resolve INGEST_DIR per submission.

    If INGEST_DIR is set:
      - absolute: treat as ingest root
      - relative: treat as BASE_DIR/<INGEST_DIR>
    If INGEST_SUBMISSION is set, namespace under <root>/submissions/<submission>,
    unless the provided INGEST_DIR already points to that submission folder.
    """
    base = Path(os.environ.get("BASE_DIR", Path.cwd()))
    default_root = base / "ingest"

    raw = os.environ.get("INGEST_DIR", "")
    if raw:
        root = Path(raw)
        if not root.is_absolute():
            root = base / root
    else:
        root = default_root

    sub = os.environ.get("INGEST_SUBMISSION", "").strip()
    if sub:
        root_str = str(root).replace("\\", "/")
        if root_str.endswith(f"/submissions/{sub}") or root_str.endswith(f"submissions/{sub}"):
            return root
        return root / "submissions" / sub

    return root

def _resolve_output_dir() -> Path:
    """Resolve OUTPUT_DIR per submission to avoid collisions.

    If OUTPUT_DIR is explicitly set in env, treat it as the root and still namespace
    under OUTPUT_DIR/submissions/<submission> when INGEST_SUBMISSION is set.
    """
    base = Path(os.environ.get("BASE_DIR", Path.cwd()))
    default_root = base / "output"

    out_root = Path(os.environ.get("OUTPUT_DIR", str(default_root)))
    submission = os.environ.get("INGEST_SUBMISSION", "").strip()

    if submission:
        # If caller already pointed OUTPUT_DIR at a submission folder, honor it.
        out_str = str(out_root).replace("\\", "/")
        if out_str.endswith(f"/submissions/{submission}") or out_str.endswith(f"submissions/{submission}"):
            return out_root
        return out_root / "submissions" / submission

    return out_root


def _find_quoted_header_ids(playbook_path: Path, max_lines: int = 80) -> bool:
    """Return True if playbook header contains a quoted id: value (id: "..." or id: '...')."""
    try:
        lines = playbook_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    for line in lines[:max_lines]:
        # Stop early once tasks begin (header finished)
        if line.startswith("tasks:"):
            break
        if re.match(r'^id:\s*["\']', line.strip()):
            return True
    return False


def _is_in_excluded_pack(path: Path) -> bool:
    p = str(path).replace("\\", "/")
    return any(f"/Packs/{name}/" in p for name in EXCLUDE_PACKS)

def _stage_fresh_playbooks(staging_root: Path) -> list[Path]:
    staging_playbooks_dir = staging_root / "Playbooks"

    if staging_playbooks_dir.exists():
        shutil.rmtree(staging_playbooks_dir)
    staging_playbooks_dir.mkdir(parents=True, exist_ok=True)

    staged_files = stage_ingest_playbooks(INGEST_DIR, staging_playbooks_dir)
    return [p for p in staged_files if is_playbook_yaml(p)]


# ------------------------------------------------------------
# Doctor (analysis only, no mutation)
# ------------------------------------------------------------

def doctor() -> int:
    global INGEST_DIR
    INGEST_DIR = _resolve_ingest_dir()
    global OUTPUT_DIR
    OUTPUT_DIR = _resolve_output_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pack_root = REPO_DIR / "Packs" / TARGET_PACK
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_root = ensure_staging_pack(REPO_DIR, STAGING_PACK)
    staged_playbooks = _stage_fresh_playbooks(staging_root)

    pack_playbooks = list(iter_playbook_files(pack_root))
    repo_playbooks = [
        p for p in list(iter_playbook_files(REPO_DIR))
        if f"/Packs/{STAGING_PACK}/" not in str(p).replace("\\", "/")
        and not _is_in_excluded_pack(p)
    ]

    id_map = build_id_normalization_map(repo_playbooks + staged_playbooks)
    old_ids = set(id_map.keys())

    impacted_repo_playbooks = find_pack_playbooks_referencing_ids(repo_playbooks, old_ids)

    missing: list[dict] = []
    platform_refs: list[dict] = []
    external_refs: list[dict] = []

    allow = DEFAULT_ALLOWLIST
    symbol_table = build_symbol_table(REPO_DIR / "Packs")

    # Backwards-compatible aliases (doctor may reference these names)
    allow = DEFAULT_ALLOWLIST
    PLATFORM_SCRIPTS = allow.platform_scripts
    EXTERNAL_PLAYBOOKS_BY_NAME = allow.external_playbooks_by_name


    for pb in staged_playbooks:
        parsed = parse_playbook_refs(pb)

        for sub_id in parsed["refs"]["playbooks_by_id"]:
            if sub_id not in symbol_table["playbooks_by_id"] and sub_id not in id_map:
                missing.append({"file": str(pb), "type": "playbook_id", "ref": sub_id})

        for sub_name in parsed["refs"]["playbooks_by_name"]:
            if sub_name in EXTERNAL_PLAYBOOKS_BY_NAME:
                external_refs.append({"file": str(pb), "type": "playbook_name", "ref": sub_name})
                continue
            if sub_name not in symbol_table["playbooks_by_name"]:
                missing.append({"file": str(pb), "type": "playbook_name", "ref": sub_name})

        for scr in parsed["refs"]["scripts"]:
            if scr in PLATFORM_SCRIPTS:
                platform_refs.append({"file": str(pb), "type": "script", "ref": scr})
                continue
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

    out = OUTPUT_DIR / "doctor_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote: {out}")
    print(f"Missing refs: {len(missing)} | Platform refs: {len(platform_refs)} | External refs: {len(external_refs)}")
    return 0


# ------------------------------------------------------------
# Fix (mutates staging only)
# ------------------------------------------------------------

def fix() -> int:
    global INGEST_DIR
    INGEST_DIR = _resolve_ingest_dir()
    global OUTPUT_DIR
    OUTPUT_DIR = _resolve_output_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pack_root = REPO_DIR / "Packs" / TARGET_PACK
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_root = ensure_staging_pack(REPO_DIR, STAGING_PACK)
    staged_playbooks = _stage_fresh_playbooks(staging_root)

    pack_playbooks = iter_playbook_files(pack_root)
    id_map = build_id_normalization_map(pack_playbooks + staged_playbooks)

    if id_map:
        print("\nID Normalization Map:")
        for old, new in id_map.items():
            print(f"  {old}  →  {new}")
    else:
        print("\nNo UUID → name normalization needed.")

    apply_mapping_across_files(staged_playbooks, id_map)

    normalize_pack(staging_root, staged_playbooks)

    code, validate_out = run_validate(REPO_DIR, f"Packs/{STAGING_PACK}")
    (OUTPUT_DIR / "fix_validate_output.txt").write_text(validate_out, encoding="utf-8")

    if code == 0:
        print("Nothing to fix. Staging validate clean.")
        return 0

    print("Running internal fixer...")
    changed = run_fixes(REPO_DIR, validate_out)
    print(f"Files modified: {changed}")
    # --------------------------------------------------
    # Guardrail: prevent quoted id: in playbook headers (causes key churn)
    # --------------------------------------------------
    quoted = [str(pb) for pb in staged_playbooks if _find_quoted_header_ids(pb)]
    if quoted:
        outp = OUTPUT_DIR / "quoted_id_playbooks.json"
        outp.write_text(json.dumps(quoted, indent=2), encoding="utf-8")
        print("ABORTING: Detected quoted id: in playbook header(s). See:", outp)
        for q in quoted:
            print("  -", q)
        return 6


    code, validate_out = run_validate(REPO_DIR, f"Packs/{STAGING_PACK}")
    (OUTPUT_DIR / "fix_validate_output_after.txt").write_text(validate_out, encoding="utf-8")

    if code != 0:
        print("Still failing after fix.")
        return code

    print("Fix successful. Staging pack clean.")
    return 0


# ------------------------------------------------------------
# Promote (safe promotion with diff + optional force)
# ------------------------------------------------------------

def promote(force: bool = False, dry_run: bool = False) -> int:
    global INGEST_DIR
    INGEST_DIR = _resolve_ingest_dir()
    global OUTPUT_DIR
    OUTPUT_DIR = _resolve_output_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pack_root = REPO_DIR / "Packs" / TARGET_PACK
    if not pack_root.exists():
        print(f"[ERROR] Target pack not found: {pack_root}")
        return 2

    staging_root = ensure_staging_pack(REPO_DIR, STAGING_PACK)
    staging_playbooks_dir = staging_root / "Playbooks"

    if not staging_playbooks_dir.exists():
        print("[ERROR] Staging Playbooks missing. Run `fix` first.")
        return 2

    staged_playbooks = [
        p for p in staging_playbooks_dir.glob("*.yml") if is_playbook_yaml(p)
    ]

    # --------------------------------------------------
    # Validate staging pack
    # --------------------------------------------------
    code, validate_out = run_validate(REPO_DIR, f"Packs/{STAGING_PACK}")
    if code != 0:
        print("Staging validate FAILED. Run fix first.")
        return code

    # --------------------------------------------------
    # Diff safety
    # --------------------------------------------------
    before_hashes = hash_playbooks(pack_root)
    after_hashes = hash_playbooks(staging_root)

    diff = compute_diff(before_hashes, after_hashes)
    total_changes = len(diff["added"]) + len(diff["modified"])

    diff_report = {
        "added": diff["added"],
        "modified": diff["modified"],
        "unchanged": diff["unchanged"],
        "total_changes": total_changes,
    }

    diff_path = OUTPUT_DIR / "promotion_diff.json"
    diff_path.write_text(json.dumps(diff_report, indent=2), encoding="utf-8")

    print(f"Promotion diff written to: {diff_path}")
    print(f"Total Changes: {total_changes}")

    MAX_ALLOWED_CHANGES = 20

    if total_changes > MAX_ALLOWED_CHANGES and not force:
        print(f"ABORTING: Too many changes ({total_changes})")
        print("Re-run with --force to override.")
        return 3

    # --------------------------------------------------
    # Repository Graph Integrity Check (SIMULATED)
    # --------------------------------------------------
    # --------------------------------------------------
    # Repository Graph Integrity Check (SIMULATED)
    # --------------------------------------------------
    print("Running repository graph integrity check...")

    before_graph = build_repo_graph(REPO_DIR)

    temp_repo = simulate_repo_with_staging(REPO_DIR, staging_root)

    # ---- Apply ID→Name mapping to impacted playbooks in the TEMP repo ----
    repo_playbooks = [
        p for p in iter_playbook_files(REPO_DIR)
        if f"/Packs/{STAGING_PACK}/" not in str(p).replace("\\", "/")
    ]

    # Ignore excluded packs for repo-impact checks
    repo_playbooks = [p for p in repo_playbooks if not _is_in_excluded_pack(p)]
    id_map = build_id_normalization_map(repo_playbooks + staged_playbooks)
    old_ids = set(id_map.keys())

    impacted_repo_playbooks = find_pack_playbooks_referencing_ids(repo_playbooks, old_ids)

    # Map impacted real paths to their equivalents in temp_repo and rewrite there
    temp_impacted: list[Path] = []
    for p in impacted_repo_playbooks:
        try:
            rel = p.relative_to(REPO_DIR)
        except ValueError:
            continue
        tp = temp_repo / rel
        if tp.exists():
            temp_impacted.append(tp)

    dependent_changes = []
    if temp_impacted and id_map:
        dependent_changes = apply_mapping_across_files(temp_impacted, id_map)

    # ---- Write reports for visibility ----
    impacted_report = {
        "id_map_count": len(id_map),
        "impacted_repo_playbooks_count": len(impacted_repo_playbooks),
        "impacted_repo_playbooks": [str(p) for p in impacted_repo_playbooks],
        "temp_impacted_count": len(temp_impacted),
        "temp_impacted": [str(p) for p in temp_impacted],
        "dependent_changes_count": len(dependent_changes),
    }
    (OUTPUT_DIR / "impacted_dependents.json").write_text(
        json.dumps(impacted_report, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "dependent_rewrite_changes.json").write_text(
        json.dumps([c.__dict__ for c in dependent_changes], indent=2),
        encoding="utf-8",
    )

    # ---- Policy: if dependents exist, abort unless --force ----
    if impacted_repo_playbooks and not force and id_map:
        print("Detected dependent playbooks that reference old IDs.")
        print(f"Wrote: {OUTPUT_DIR / 'impacted_dependents.json'}")
        print("ABORTING (run with --force to proceed).")
        return 6

    # IMPORTANT: Build after_graph *after* rewriting dependents in temp_repo
    after_graph = build_repo_graph(temp_repo)

    # Restrict graph comparison to only what we touched (staged + impacted)
    focus_nodes = set()

    # staged playbooks ids
    for pb in staged_playbooks:
        d = parse_playbook_refs(pb)
        if d.get("id"):
            focus_nodes.add(str(d["id"]))

    # impacted dependents ids (repo originals)
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

    semantic_report = {}

    for pb in staged_playbooks:
        real_path = pack_root / "Playbooks" / pb.name

        if real_path.exists():
            before_snap = snapshot_playbook(real_path)
            after_snap = snapshot_playbook(pb)

            diff = semantic_diff(before_snap, after_snap)

            if any(
                    diff[k]
                    for k in diff
            ):
                semantic_report[pb.name] = diff
        else:
            semantic_report[pb.name] = {"new_playbook": True}

    semantic_path = OUTPUT_DIR / "semantic_diff.json"
    semantic_path.write_text(
        json.dumps(semantic_report, indent=2),
        encoding="utf-8",
    )

    print(f"Semantic diff written to: {semantic_path}")


    # --------------------------------------------------
    # Playbook Integrity Check
    # --------------------------------------------------
    print("Running playbook integrity checks...")

    integrity_report = {}
    hard_fail = False

    for pb in staged_playbooks:
        real_path = pack_root / "Playbooks" / pb.name

        if real_path.exists():
            integrity = analyze_playbook_integrity(real_path, pb)

            # Hard fail condition
            if integrity.get("dangling_old_id_reference"):
                hard_fail = True

            # Record if anything interesting changed
            if any(integrity.values()):
                integrity_report[pb.name] = integrity

    integrity_path = OUTPUT_DIR / "integrity_report.json"
    integrity_path.write_text(
        json.dumps(integrity_report, indent=2),
        encoding="utf-8"
    )

    print(f"Integrity report written to: {integrity_path}")

    if hard_fail:
        print("ABORTING: Dangling old playbook ID detected.")
        return 5


    # --------------------------------------------------
    # COPY INTO REAL PACK  (REAL MUTATION POINT)
    # --------------------------------------------------
    if dry_run:
        print("DRY RUN: skipping copy into real pack and final pack validate.")
        return 0

    real_pb_dir = pack_root / "Playbooks"
    real_pb_dir.mkdir(parents=True, exist_ok=True)

    for pb in staged_playbooks:
        shutil.copy2(pb, real_pb_dir / pb.name)

    # Final validate
    final_code, final_out = run_validate(REPO_DIR, f"Packs/{TARGET_PACK}")
    print(final_out)
    print(f"Final validate exit code: {final_code}")

    return final_code


# ------------------------------------------------------------
# Entry
# ------------------------------------------------------------



# ------------------------------------------------------------
# Accept (doctor + fix + promote wrapper)
# ------------------------------------------------------------

def accept(apply: bool = False) -> int:
    global INGEST_DIR
    INGEST_DIR = _resolve_ingest_dir()
    global OUTPUT_DIR
    OUTPUT_DIR = _resolve_output_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Running doctor...")
    d_code = doctor()
    if d_code != 0:
        print("Doctor failed.")
        return d_code

    # Read doctor report
    doctor_report_path = OUTPUT_DIR / "doctor_report.json"
    doctor_report = {}
    if doctor_report_path.exists():
        import json
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

    # Write acceptance receipt
    receipt = {
        "target_pack": TARGET_PACK,
        "staging_pack": STAGING_PACK,
        "apply": apply,
        "doctor_counts": doctor_report.get("counts", {}),
        "receipt_version": 1,
          "submission": INGEST_SUBMISSION if "INGEST_SUBMISSION" in globals() and INGEST_SUBMISSION else None,
    }

    import json
    receipt_path = OUTPUT_DIR / "acceptance_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print(f"Acceptance receipt written to: {receipt_path}")
    print("ACCEPT complete.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.src.cli <command> [--force]")
        print("Commands: doctor, fix, promote")
        return 2

    cmd = sys.argv[1].lower()

    # accept: doctor + fix + promote wrapper

    if cmd == "accept":

        apply = "--apply" in sys.argv

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