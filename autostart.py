import sys
from pathlib import Path


def resolve_startup_launcher_file() -> Path | None:
    appdata = __import__("os").getenv("APPDATA")
    if not appdata:
        return None
    startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup_dir / "Sticky Notes Auto Start.bat"


def build_startup_command(autostart_arg: str) -> str:
    if getattr(sys, "frozen", False):
        target = str(Path(sys.executable).resolve())
        return f'start "" "{target}" {autostart_arg}'

    python_exec = Path(sys.executable).resolve()
    pythonw_exec = python_exec.with_name("pythonw.exe")
    launcher_python = pythonw_exec if pythonw_exec.exists() else python_exec
    script_path = Path(__file__).resolve().with_name("sticky_notes.py")
    return f'start "" "{launcher_python}" "{script_path}" {autostart_arg}'


def has_stickynotes_signature(content: str) -> bool:
    lower = content.lower()
    if "# stickynotes_autostart" in lower:
        return True
    return "sticky notes" in lower and (
        "sticky_notes.py" in lower
        or "stickynotes_noteonly_fix" in lower
        or "stickynotes_daeridoong" in lower
    )
