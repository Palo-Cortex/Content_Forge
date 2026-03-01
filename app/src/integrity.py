import re
import yaml


def analyze_playbook_integrity(before_path, after_path):
    before = yaml.safe_load(before_path.read_text())
    after_text = after_path.read_text()
    after = yaml.safe_load(after_text)

    report = {}

    # -------------------------------------------------
    # ID / Name Changes
    # -------------------------------------------------
    old_id = before.get("id")
    new_id = after.get("id")

    report["id_changed"] = old_id != new_id
    report["name_changed"] = before.get("name") != after.get("name")

    # -------------------------------------------------
    # HARD FAIL: Dangling old UUID reference
    # -------------------------------------------------
    if old_id and old_id in after_text and old_id != new_id:
        report["dangling_old_id_reference"] = True
    else:
        report["dangling_old_id_reference"] = False

    # -------------------------------------------------
    # Inputs (Warning Only)
    # -------------------------------------------------
    declared_inputs = set(
        i.get("name") for i in after.get("inputs", []) if i.get("name")
    )

    used_inputs = set(
        re.findall(r"\${inputs\.([a-zA-Z0-9_]+)}", after_text)
    )

    report["unused_inputs"] = list(declared_inputs - used_inputs)

    # -------------------------------------------------
    # Outputs (optional warning only)
    # -------------------------------------------------
    declared_outputs = set(
        o.get("name") for o in after.get("outputs", []) if o.get("name")
    )

    # You can refine this later if needed
    written_outputs = set(
        re.findall(r"SOCFramework\.([a-zA-Z0-9_]+)", after_text)
    )

    report["unused_outputs"] = list(declared_outputs - written_outputs)

    return report