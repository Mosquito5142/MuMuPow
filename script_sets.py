import copy
import json
import re
from pathlib import Path


def safe_set_slug(name):
    slug = str(name or "").strip().replace("\\", "/").split("/")[-1]
    slug = slug[:-5] if slug.lower().endswith(".json") else slug
    slug = re.sub(r"\s+", "_", slug)
    slug = re.sub(r'[<>:"|?*]', "", slug).strip("._ ")
    return slug or "set"


def build_run_set_step(set_name):
    name = str(set_name or "").strip()
    return {
        "type": "run_set",
        "set": name,
        "desc": f"Use set: {name}",
    }


def load_script_set(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    name = str(data.get("name") or Path(path).stem).strip()
    steps = data.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("Script set steps must be a list")
    return {"name": name, "steps": steps}


def save_script_set(path, name, steps):
    if not isinstance(steps, list):
        raise ValueError("Script set steps must be a list")
    data = {"name": str(name or "").strip() or Path(path).stem, "steps": steps}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def expand_steps_with_sets(steps, resolver, stack=None):
    stack = list(stack or [])
    expanded = []
    for step in steps:
        if step.get("type") != "run_set":
            expanded.append(copy.deepcopy(step))
            continue

        set_name = str(step.get("set") or step.get("text") or "").strip()
        if not set_name:
            raise ValueError("Script set name is required")
        if set_name in stack:
            chain = " -> ".join(stack + [set_name])
            raise ValueError(f"Script set cycle detected: {chain}")

        set_steps = resolver(set_name)
        if set_steps is None:
            raise ValueError(f"Script set not found: {set_name}")
        expanded.extend(expand_steps_with_sets(set_steps, resolver, stack + [set_name]))
    return expanded
