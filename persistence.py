import json
import os
from pathlib import Path
from typing import Any


def resolve_data_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        data_dir = Path(appdata) / "Sticky Notes"
    else:
        data_dir = Path.home() / ".sticky_notes"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def resolve_data_file() -> Path:
    return resolve_data_dir() / "notes_data.json"


def resolve_crash_log_file() -> Path:
    return resolve_data_dir() / "last_crash.log"


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def atomic_write_json(path: Path, payload: Any) -> None:
    tmp_file = path.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp_file, path)
