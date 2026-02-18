import os


DEFAULT_CONFIG = {
    "github": {
        "token_env": "GITHUB_TOKEN",
        "cache_ttl_hours": 24,
        "per_handle_max_repos": 12,
        "request_timeout_sec": 20,
    },
    "scoring": {
        "weights": {
            "engineering": 40,
            "impact": 30,
            "activity": 15,
            "ai_productivity": 15,
        }
    },
    "resume_samples": {
        "enable_storage": True,
        "store_full_text": False,
    },
    "output": {
        "top_n": 10,
    },
    "activity": {
        "window_days": 90,
    },
    "processing": {
        "batch_size": 20,
        "batch_deviation_threshold": 0.2,
    },
}


def load_config(path):
    if not path or not os.path.exists(path):
        return DEFAULT_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    data = _load_yaml(raw)
    merged = _merge_dicts(DEFAULT_CONFIG, data)
    return merged


def merge_config(base, override):
    if not override:
        return base
    return _merge_dicts(base, override)


def _merge_dicts(base, override):
    result = {}
    for key, value in base.items():
        if isinstance(value, dict):
            result[key] = _merge_dicts(value, override.get(key, {}))
        else:
            result[key] = override.get(key, value)
    for key, value in override.items():
        if key not in result:
            result[key] = value
    return result


def _load_yaml(raw):
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return _parse_simple_yaml(raw)


def _parse_simple_yaml(raw):
    data = {}
    stack = [(0, data)]
    for line in raw.splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if ":" not in line:
            continue
        key, value = line.lstrip().split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and indent < stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if value == "":
            new_map = {}
            current[key] = new_map
            stack.append((indent + 2, new_map))
        else:
            current[key] = _coerce_value(value)
    return data


def _coerce_value(value):
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")
