from app.src.playbook_refs import parse_playbook_refs


def snapshot_playbook(path):
    from app.src.yaml_utils import load_yaml
    data = load_yaml(path)

    parsed = parse_playbook_refs(path)

    tasks = data.get("tasks", {})

    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "subplaybooks": set(parsed["refs"]["playbooks_by_id"]),
        "scripts": set(parsed["refs"]["scripts"]),
        "task_count": len(tasks),
    }


def semantic_diff(before_snap, after_snap):
    return {
        "id_changed": before_snap["id"] != after_snap["id"],
        "name_changed": before_snap["name"] != after_snap["name"],
        "subplaybooks_added": list(after_snap["subplaybooks"] - before_snap["subplaybooks"]),
        "subplaybooks_removed": list(before_snap["subplaybooks"] - after_snap["subplaybooks"]),
        "scripts_added": list(after_snap["scripts"] - before_snap["scripts"]),
        "scripts_removed": list(before_snap["scripts"] - after_snap["scripts"]),
        "tasks_added": max(0, after_snap["task_count"] - before_snap["task_count"]),
        "tasks_removed": max(0, before_snap["task_count"] - after_snap["task_count"]),
    }