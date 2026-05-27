import json
import os
import shutil
import sys
import time
import uuid
import webbrowser
import ctypes
import threading
import traceback
import re
import base64
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

try:
    from PIL import Image, ImageGrab, ImageTk
    PILLOW_AVAILABLE = True
except ImportError:
    Image = None
    ImageGrab = None
    ImageTk = None
    PILLOW_AVAILABLE = False

from autostart import build_startup_command, has_stickynotes_signature, resolve_startup_launcher_file
from instance_control import already_running, notify_existing_instance
from persistence import atomic_write_json, read_json_file, resolve_crash_log_file, resolve_data_file
from tray import create_tray_image
from windows.global_settings import GlobalSettingsDialog as AppGlobalSettingsDialog
from windows.note_settings import NoteSettingsDialog as AppNoteSettingsDialog

try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    pystray = None
    TRAY_AVAILABLE = False


def _resolve_data_file() -> Path:
    return resolve_data_file()


def _resolve_startup_launcher_file() -> Path | None:
    return resolve_startup_launcher_file()


DATA_FILE = _resolve_data_file()
APP_ICON = Path(__file__).with_name("sticky_note.ico")
SINGLE_INSTANCE_MUTEX_NAME = "Local\\StickyNotesAppSingleInstanceV1"
ACTIVATE_EVENT_NAME = "Local\\StickyNotesAppActivateEventV1"
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0


def _legacy_data_candidates() -> list[Path]:
    candidates = []

    # Script location during dev runs.
    candidates.append(Path(__file__).with_name("notes_data.json"))

    # Current working directory (when launched from a folder).
    candidates.append(Path.cwd() / "notes_data.json")

    # Frozen executable directory (PyInstaller onefile/onedir).
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "notes_data.json")

    # Workspace fallback used in this project.
    candidates.append(Path(r"c:\Sticky Notes\notes_data.json"))

    unique = []
    seen = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


DEFAULT_COLORS = [
    "#FFF9A8",  # yellow
    "#FFD7BA",  # peach
    "#C8F7C5",  # mint
    "#BFE3FF",  # blue
    "#F8CBFF",  # pink
]

DEFAULT_NOTE_WIDTH = 260
DEFAULT_NOTE_HEIGHT = 260
MIN_NOTE_WIDTH = 180
MIN_NOTE_HEIGHT = 120
AUTOSTART_ARG = "--autostart"
APP_DISPLAY_NAME = "StickyNotes_DaeriDoong"
APP_SIGNATURE_NAME = "DaeriDoong"
APP_BRAND_NAME = f"{APP_DISPLAY_NAME} - {APP_SIGNATURE_NAME}"


def _resolve_crash_log_file() -> Path:
    return resolve_crash_log_file()


CRASH_LOG_FILE = _resolve_crash_log_file()
EMBEDDED_IMG_PREFIX = "[[IMG:"
EMBEDDED_TABLE_PREFIX = "[[TABLE:"
EMBEDDED_MARKER_SUFFIX = "]]"
DEBUG_LOG_FILE = DATA_FILE.parent / "debug_session.log"
DEBUG_LOG_ENABLED = os.getenv("STICKY_DEBUG", "1") != "0"


def _debug_log(message: str) -> None:
    if not DEBUG_LOG_ENABLED:
        return
    try:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
        with DEBUG_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        return


def _resolve_media_dir() -> Path:
    media_dir = DATA_FILE.parent / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir


def _copy_media_file(source_path: str) -> Path:
    src = Path(source_path)
    ext = src.suffix.lower() or ".png"
    safe_ext = ext if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"} else ".png"
    dest = _resolve_media_dir() / f"image_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}{safe_ext}"
    shutil.copy2(src, dest)
    return dest


def _write_crash_log(exc: BaseException) -> None:
    try:
        lines = [
            f"timestamp={time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"python={sys.version}",
            "",
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        ]
        CRASH_LOG_FILE.write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        return


HELP_NOTE_CONTENT = """안녕하세요, DaeriDoong입니다.

StickyNotes_DaeriDoong 사용설명서(최신)

1) 기본 사용
- 이 앱은 여러 개의 스티커 노트를 동시에 띄워 빠르게 메모하는 데스크톱 앱입니다.
- 노트 본문은 입력 즉시 자동 저장됩니다.
- 상단 버튼에서 새 노트, 접기/펴기, 숨기기, 삭제, 전체 복사, 붙여넣기를 실행할 수 있습니다.

2) 노트 관리
- 노트 목록 창에서 열기, 숨기기, 삭제, 검색(제목+본문)을 한 번에 처리할 수 있습니다.
- 노트 이름은 목록 창 또는 노트 창에서 F2, 더블클릭, 우클릭 메뉴로 변경할 수 있습니다.
- 정렬 기능으로 가로/세로/바둑판 정렬을 빠르게 적용할 수 있습니다.

3) 편집/삽입 기능
- 표 삽입: 셀 추가, 삭제, 병합, 분할 후 삽입할 수 있습니다.
- 표 재편집: 노트 안에 삽입된 표를 직접 수정하면 변경 사항이 저장됩니다.
- 이미지 삽입: 그림 파일을 앱 미디어 폴더로 복사해 참조 삽입합니다.
- 그림 그리기: 간단한 스케치를 이미지로 노트에 삽입할 수 있습니다.
- 삽입된 표/이미지는 텍스트가 아닌 실제 임베드 요소로 표시됩니다.

4) 설정 기능
- 노트별 설정: 배경색, 글꼴 크기, 투명도
- 전역 설정: 자동실행, 시작 동작, 항상 위, 백업/복원

5) 사용 팁
- 접기 기능으로 제목줄만 남겨 화면 점유를 줄일 수 있습니다.
- 빈 메모는 닫을 때 자동 정리되어 임시 메모 작성이 편합니다.
- 마지막 상태(크기, 위치, 표시 상태)는 다음 실행 시 복원됩니다.
- 한글 입력 안정화를 적용해 IME 전환 흔들림을 줄였습니다.

공식 배포 경로
- GitHub Releases

개발자의 다른 앱
1. 업무 카메라(업무 사진 정리)
https://play.google.com/store/apps/details?id=com.milemilesmile.work_camera_v2

2. 멍냥이피아노
https://play.google.com/store/apps/details?id=com.milemilesmile.myapplication

3. 멍냥이슬라이드
https://play.google.com/store/apps/details?id=com.axlose.meow_woof_slide
"""


def _apply_window_icon(window: tk.Misc) -> None:
    if not APP_ICON.exists():
        return
    try:
        window.iconbitmap(default=str(APP_ICON))
    except (tk.TclError, OSError):
        # Some environments may reject icon setting; ignore safely.
        return


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def _mix_color(color: str, target: str, ratio: float) -> str:
    base_rgb = _hex_to_rgb(color)
    target_rgb = _hex_to_rgb(target)
    mixed = tuple(
        int(base_value + (target_value - base_value) * ratio)
        for base_value, target_value in zip(base_rgb, target_rgb)
    )
    return _rgb_to_hex(mixed)


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window = None

        self.widget.bind("<Enter>", self._show, add="+")
        self.widget.bind("<Leave>", self._hide, add="+")
        self.widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self.tip_window or not self.text:
            return

        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.attributes("-topmost", True)

        label = tk.Label(
            self.tip_window,
            text=self.text,
            bg="#fffdf2",
            fg="#4d4638",
            bd=1,
            relief="solid",
            padx=8,
            pady=4,
            font=("Segoe UI", 9),
        )
        label.pack()

        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip_window.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event=None) -> None:
        if self.tip_window and self.tip_window.winfo_exists():
            self.tip_window.destroy()
        self.tip_window = None

    def set_text(self, text: str) -> None:
        self.text = text
        self._hide()


class StickyNotesApp:
    def __init__(self, root: tk.Tk, activation_event_handle=None, launched_from_autostart: bool = False) -> None:
        self.root = root
        self.root.withdraw()

        self.notes = {}
        self.note_windows = {}
        self._save_job = None
        self.manager_dialog = None
        self.settings_dialog = None
        self.global_settings_dialog = None
        self.help_window = None
        self._last_created_note_id = None
        self._loaded_new_data = False
        self._last_active_note_id = None
        self._activation_event_handle = activation_event_handle
        self._launched_from_autostart = launched_from_autostart
        self._is_quitting = False
        self._tray_icon = None
        self._tray_thread = None
        self.auto_start_enabled = True
        self.autostart_force_show_if_all_hidden = True
        self.always_on_top = True
        self.app_state = {
            "manager": {"visible": False, "geometry": ""},
            "settings": {"visible": False, "geometry": "", "note_id": None},
            "open_note_ids": [],
            "last_active_note_id": None,
            "preferences": {
                "auto_start_enabled": True,
                "autostart_force_show_if_all_hidden": True,
                "always_on_top": True,
            },
        }

        self._load_notes()
        self._sync_windows_startup_registration()
        self._cleanup_empty_hidden_notes()
        self._open_all_visible_notes()
        self._restore_app_state()
        if self._launched_from_autostart:
            self._restore_autostart_visible_notes()
        else:
            self._force_show_startup_note()

        self._setup_tray_icon()
        self._start_activation_event_poll()
        self._apply_always_on_top_setting()
        self.root.protocol("WM_DELETE_WINDOW", self._quit_app)

    def _create_tray_image(self):
        return create_tray_image()

    def _setup_tray_icon(self) -> None:
        if not TRAY_AVAILABLE:
            return

        def on_open(_icon, _item) -> None:
            self.root.after(0, self._restore_from_activation_signal)

        def on_new_note(_icon, _item) -> None:
            self.root.after(0, self.create_note)

        def on_quit(_icon, _item) -> None:
            self.root.after(0, self._quit_app)

        def on_open_crash_log(_icon, _item) -> None:
            self.root.after(0, self._open_last_crash_log)

        try:
            menu = pystray.Menu(
                pystray.MenuItem("열기", on_open, default=True),
                pystray.MenuItem("새 노트", on_new_note),
                pystray.MenuItem("마지막 크래시 로그", on_open_crash_log),
                pystray.MenuItem("종료", on_quit),
            )
            self._tray_icon = pystray.Icon("sticky_notes_tray", self._create_tray_image(), APP_BRAND_NAME, menu)
            self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
            self._tray_thread.start()
        except Exception:
            # Keep the app usable even if tray integration fails on a machine.
            self._tray_icon = None
            self._tray_thread = None

    def _stop_tray_icon(self) -> None:
        if self._tray_icon is None:
            return
        try:
            self._tray_icon.stop()
        except Exception:
            pass
        self._tray_icon = None

    def _start_activation_event_poll(self) -> None:
        if not self._activation_event_handle:
            return
        self.root.after(250, self._poll_activation_event)

    def _poll_activation_event(self) -> None:
        if self._is_quitting or not self._activation_event_handle:
            return

        result = ctypes.windll.kernel32.WaitForSingleObject(self._activation_event_handle, 0)
        if result == WAIT_OBJECT_0:
            self._restore_from_activation_signal()

        self.root.after(250, self._poll_activation_event)

    def _restore_from_activation_signal(self) -> None:
        if not self.notes:
            self.create_note()
            return

        target_note_id = self._last_active_note_id if self._last_active_note_id in self.notes else None
        if not target_note_id:
            target_note_id = next(iter(self.notes.keys()))

        self.open_note_window(target_note_id)
        win = self.note_windows.get(target_note_id)
        if win and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.focus_force()
        self._keep_panels_on_top()

    def _open_last_crash_log(self) -> None:
        if not CRASH_LOG_FILE.exists():
            messagebox.showinfo(APP_BRAND_NAME, "저장된 크래시 로그가 없습니다.")
            return

        try:
            os.startfile(str(CRASH_LOG_FILE))
        except OSError:
            messagebox.showerror(APP_BRAND_NAME, f"크래시 로그를 열지 못했습니다.\n{CRASH_LOG_FILE}")

    def _force_show_startup_note(self) -> None:
        if not self.notes:
            self.create_note()

        target_note_id = self._last_active_note_id if self._last_active_note_id in self.notes else None
        if not target_note_id:
            target_note_id = next(iter(self.notes.keys()))

        self.open_note_window(target_note_id)
        win = self.note_windows.get(target_note_id)
        if not win or not win.winfo_exists():
            return

        # Startup should always present a visible sticker window to the user.
        win.deiconify()
        win.update_idletasks()

        if win.state() == "iconic":
            win.state("normal")

        if win.winfo_width() < MIN_NOTE_WIDTH or win.winfo_height() < MIN_NOTE_HEIGHT:
            note = self.notes.get(target_note_id, {})
            self._normalize_note_geometry(note)
            win.geometry(f"{note['width']}x{note['height']}+{note['x']}+{note['y']}")

        win.lift()
        win.focus_force()

    def _restore_autostart_visible_notes(self) -> None:
        # Autostart should restore only windows that were visible before shutdown.
        visible_note_windows = [
            win for win in self.note_windows.values() if win.winfo_exists() and win.state() != "withdrawn"
        ]
        if not visible_note_windows:
            if self.autostart_force_show_if_all_hidden:
                self._force_show_startup_note()
            return

        for win in visible_note_windows:
            try:
                win.deiconify()
            except tk.TclError:
                continue

    def _default_note(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "title": "New Note",
            "content": "",
            "x": 200,
            "y": 200,
            "width": DEFAULT_NOTE_WIDTH,
            "height": DEFAULT_NOTE_HEIGHT,
            "expanded_height": DEFAULT_NOTE_HEIGHT,
            "bg": DEFAULT_COLORS[0],
            "font_size": 11,
            "opacity": 1.0,
            "visible": True,
            "collapsed": False,
        }

    def _load_notes(self) -> None:
        if not DATA_FILE.exists():
            for candidate in _legacy_data_candidates():
                if candidate.exists() and candidate != DATA_FILE:
                    try:
                        shutil.copy2(candidate, DATA_FILE)
                        break
                    except OSError:
                        continue

        raw = read_json_file(DATA_FILE, [])
        if isinstance(raw, dict):
            items = raw.get("notes", [])
            state = raw.get("app_state", {})
            if isinstance(state, dict):
                self.app_state.update(state)
                self._last_active_note_id = state.get("last_active_note_id")
                preferences = state.get("preferences", {})
                if isinstance(preferences, dict):
                    self.auto_start_enabled = bool(preferences.get("auto_start_enabled", True))
                    self.autostart_force_show_if_all_hidden = bool(
                        preferences.get("autostart_force_show_if_all_hidden", True)
                    )
                    self.always_on_top = bool(preferences.get("always_on_top", True))
        elif isinstance(raw, list):
            items = raw
        else:
            items = []

        if not items:
            first = self._default_note()
            self.notes[first["id"]] = first
            self._loaded_new_data = True
            self._queue_save()
            return

        for raw in items:
            note = self._default_note()
            note.update(raw)
            note.pop("art_enabled", None)
            self.notes[note["id"]] = note

    def _save_notes(self) -> None:
        self._snapshot_runtime_state()
        payload = {
            "notes": list(self.notes.values()),
            "app_state": self._collect_app_state(),
        }
        try:
            atomic_write_json(DATA_FILE, payload)
        except OSError as exc:
            messagebox.showerror("Save Error", f"Failed to save notes:\n{exc}")

    def _collect_app_state(self) -> dict:
        manager_visible = bool(self.manager_dialog and self.manager_dialog.winfo_exists() and self.manager_dialog.state() != "withdrawn")
        manager_geometry = self.manager_dialog.geometry() if self.manager_dialog and self.manager_dialog.winfo_exists() else ""

        settings_visible = bool(self.settings_dialog and self.settings_dialog.winfo_exists() and self.settings_dialog.state() != "withdrawn")
        settings_geometry = self.settings_dialog.geometry() if self.settings_dialog and self.settings_dialog.winfo_exists() else ""
        settings_note_id = self.settings_dialog.note_id if self.settings_dialog and self.settings_dialog.winfo_exists() else None
        open_note_ids = []
        for note_id, win in list(self.note_windows.items()):
            if not win.winfo_exists() or win.state() == "withdrawn":
                continue
            open_note_ids.append(note_id)

        return {
            "manager": {
                "visible": manager_visible,
                "geometry": manager_geometry,
            },
            "settings": {
                "visible": settings_visible,
                "geometry": settings_geometry,
                "note_id": settings_note_id,
            },
            "open_note_ids": open_note_ids,
            "last_active_note_id": self._last_active_note_id,
            "preferences": {
                "auto_start_enabled": self.auto_start_enabled,
                "autostart_force_show_if_all_hidden": self.autostart_force_show_if_all_hidden,
                "always_on_top": self.always_on_top,
            },
        }

    def _snapshot_runtime_state(self) -> None:
        self.reconcile_notes_with_windows()

    def _restore_app_state(self) -> None:
        manager_state = self.app_state.get("manager", {}) if isinstance(self.app_state, dict) else {}
        settings_state = self.app_state.get("settings", {}) if isinstance(self.app_state, dict) else {}
        if isinstance(self.app_state, dict):
            self._last_active_note_id = self.app_state.get("last_active_note_id")
        restored_note_ids = []

        for note_id in self.app_state.get("open_note_ids", []):
            if note_id in self.notes:
                self.open_note_window(note_id)
                restored_note_ids.append(note_id)

        if not restored_note_ids:
            for note_id, note in self.notes.items():
                if note.get("visible", True):
                    self.open_note_window(note_id)

        if manager_state.get("visible"):
            self._ensure_single_manager_dialog()
            if self.manager_dialog and self.manager_dialog.winfo_exists():
                geometry = manager_state.get("geometry")
                if geometry:
                    try:
                        self.manager_dialog.geometry(geometry)
                    except tk.TclError:
                        pass
                self.manager_dialog.deiconify()
                self.manager_dialog.lift()
                self.manager_dialog.refresh()

        settings_note_id = settings_state.get("note_id")
        if settings_state.get("visible") and settings_note_id in self.notes:
            self.open_note_settings(settings_note_id)
            if self.settings_dialog and self.settings_dialog.winfo_exists():
                geometry = settings_state.get("geometry")
                if geometry:
                    try:
                        self.settings_dialog.geometry(geometry)
                    except tk.TclError:
                        pass

    def _resolve_startup_cleanup_targets(self) -> list[Path]:
        launcher = _resolve_startup_launcher_file()
        if not launcher:
            return []
        return [
            launcher,
            launcher.parent / "StickyNotes Auto Start.bat",
            launcher.parent / "Sticky Notes AutoStart.bat",
        ]

    def _iter_startup_sticky_launchers(self) -> list[Path]:
        launcher = _resolve_startup_launcher_file()
        if not launcher:
            return []

        startup_dir = launcher.parent
        if not startup_dir.exists():
            return []

        matched = []
        for path in startup_dir.glob("*.bat"):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            lower = content.lower()
            if has_stickynotes_signature(content):
                matched.append(path)
                continue

        return matched

    def _remove_windows_startup_registration(self) -> None:
        candidates = self._resolve_startup_cleanup_targets() + self._iter_startup_sticky_launchers()
        for path in candidates:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                continue

    def _sync_windows_startup_registration(self) -> None:
        launcher = _resolve_startup_launcher_file()
        if not launcher:
            return

        if not self.auto_start_enabled:
            self._remove_windows_startup_registration()
            return

        try:
            launcher.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return

        command = build_startup_command(AUTOSTART_ARG)

        content = "@echo off\n# StickyNotes_AutoStart\n" + command + "\n"
        try:
            launcher.write_text(content, encoding="utf-8")
        except OSError:
            return

        stale_candidates = self._resolve_startup_cleanup_targets() + self._iter_startup_sticky_launchers()
        for stale_path in stale_candidates:
            if stale_path == launcher:
                continue
            try:
                if stale_path.exists():
                    stale_path.unlink()
            except OSError:
                continue

    def set_auto_start_enabled(self, enabled: bool) -> None:
        next_value = bool(enabled)
        if self.auto_start_enabled == next_value:
            return
        self.auto_start_enabled = next_value
        self._sync_windows_startup_registration()
        self._queue_save()

    def set_always_on_top(self, enabled: bool) -> None:
        next_value = bool(enabled)
        if self.always_on_top == next_value:
            return
        self.always_on_top = next_value
        self._apply_always_on_top_setting()
        self._queue_save()

    def _apply_always_on_top_setting(self) -> None:
        for win in list(self.note_windows.values()):
            if not win.winfo_exists():
                continue
            try:
                win.attributes("-topmost", self.always_on_top)
            except tk.TclError:
                continue

        for panel in (self.manager_dialog, self.settings_dialog, self.global_settings_dialog, self.help_window):
            if not panel or not panel.winfo_exists():
                continue
            try:
                panel.attributes("-topmost", self.always_on_top)
            except tk.TclError:
                continue

    def export_backup_file(self) -> None:
        target = filedialog.asksaveasfilename(
            title="메모 백업 저장",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
            initialfile=f"sticky_notes_backup_{time.strftime('%Y%m%d_%H%M%S')}.json",
        )
        if not target:
            return
        try:
            self._save_notes()
            shutil.copy2(DATA_FILE, Path(target))
            messagebox.showinfo("백업", "백업 파일을 저장했습니다.")
        except OSError as exc:
            messagebox.showerror("백업", f"백업 저장 실패:\n{exc}")

    def import_backup_file(self) -> None:
        source = filedialog.askopenfilename(
            title="메모 백업 불러오기",
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
        )
        if not source:
            return
        try:
            raw = json.loads(Path(source).read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or "notes" not in raw:
                raise ValueError("Invalid backup format")
            Path(DATA_FILE).write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("백업", f"백업 불러오기 실패:\n{exc}")
            return

        messagebox.showinfo("백업", "백업 복원이 완료되었습니다. 앱을 다시 시작합니다.")
        self._quit_app()

    def _queue_save(self) -> None:
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(250, self._save_and_clear_job)

    def _save_and_clear_job(self) -> None:
        self._save_job = None
        self._save_notes()

    def _cleanup_empty_hidden_notes(self) -> None:
        for note_id in list(self.notes.keys()):
            note = self.notes.get(note_id, {})
            is_visible = bool(note.get("visible", True))
            has_content = bool((note.get("content") or "").strip())
            if is_visible or has_content:
                continue
            self.notes.pop(note_id, None)

        if not self.notes:
            first = self._default_note()
            self.notes[first["id"]] = first

    def _open_all_visible_notes(self) -> None:
        for note_id, note in self.notes.items():
            if note.get("visible", True):
                self.open_note_window(note_id)

    def _refresh_note_list(self) -> None:
        if self.manager_dialog and self.manager_dialog.winfo_exists():
            self.manager_dialog.refresh()

    def _ensure_single_manager_dialog(self) -> None:
        found = []
        for child in self.root.winfo_children():
            if isinstance(child, NotesManagerDialog) and child.winfo_exists():
                found.append(child)

        if not found:
            self.manager_dialog = NotesManagerDialog(self)
            self.manager_dialog.withdraw()
            return

        primary = found[0]
        for extra in found[1:]:
            try:
                extra.destroy()
            except tk.TclError:
                pass
        self.manager_dialog = primary

    def _sync_note_from_window(self, note_id: str) -> None:
        win = self.note_windows.get(note_id)
        note = self.notes.get(note_id)
        if not win or not note or not win.winfo_exists():
            return

        note["content"] = win.text.get("1.0", "end-1c")
        note["title"] = win.title() or note.get("title", "New Note")
        note["x"] = win.winfo_x()
        note["y"] = win.winfo_y()
        note["width"] = win.winfo_width()
        note["height"] = win.winfo_height()
        if not win._is_collapsed:
            note["expanded_height"] = win.winfo_height()

    def _is_note_empty(self, note_id: str) -> bool:
        note = self.notes.get(note_id)
        if not note:
            return True
        return not note.get("content", "").strip()

    def note_preview(self, note_id: str, max_chars: int = 80) -> str:
        note = self.notes.get(note_id, {})
        content = (note.get("content") or "").strip()
        if not content:
            return "(empty)"

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return "(empty)"

        preview = " / ".join(lines[:2])
        if len(preview) > max_chars:
            return preview[: max_chars - 1] + "..."
        return preview

    def reconcile_notes_with_windows(self) -> None:
        # Guard against stale state: ensure any live note window has a matching note record.
        for note_id, win in list(self.note_windows.items()):
            if not win.winfo_exists():
                self.note_windows.pop(note_id, None)
                continue
            if note_id in self.notes:
                continue

            self.notes[note_id] = {
                **self._default_note(),
                "id": note_id,
                "title": win.title() or "New Note",
                "content": win.text.get("1.0", "end-1c") if hasattr(win, "text") else "",
                "x": win.winfo_x(),
                "y": win.winfo_y(),
                "width": win.winfo_width(),
                "height": win.winfo_height(),
                "visible": True,
            }

            self._sync_note_from_window(note_id)

        for note_id, win in list(self.note_windows.items()):
            if not win.winfo_exists() or note_id not in self.notes:
                continue
            self._sync_note_from_window(note_id)
            self.notes[note_id]["visible"] = (win.state() != "withdrawn")

    def create_note(self) -> None:
        note = self._default_note()
        note["x"] += 30 * (len(self.notes) % 7)
        note["y"] += 30 * (len(self.notes) % 7)
        self.notes[note["id"]] = note
        self._last_created_note_id = note["id"]
        self.open_note_window(note["id"])
        self._refresh_note_list()
        self._queue_save()

    def open_note_window(self, note_id: str) -> None:
        if note_id in self.note_windows:
            win = self.note_windows[note_id]
            win.deiconify()
            win.lift()
            if note_id in self.notes:
                self.notes[note_id]["visible"] = True
            self._refresh_note_list()
            self._queue_save()
            return

        note = self.notes[note_id]
        self._normalize_note_geometry(note)
        win = NoteWindow(self, note)
        self.note_windows[note_id] = win
        note["visible"] = True
        self._refresh_note_list()
        self._queue_save()

    def _normalize_note_geometry(self, note: dict) -> None:
        screen_w = max(self.root.winfo_screenwidth(), MIN_NOTE_WIDTH)
        screen_h = max(self.root.winfo_screenheight(), MIN_NOTE_HEIGHT)

        width = int(note.get("width", DEFAULT_NOTE_WIDTH) or DEFAULT_NOTE_WIDTH)
        height = int(note.get("height", DEFAULT_NOTE_HEIGHT) or DEFAULT_NOTE_HEIGHT)
        expanded_height = int(note.get("expanded_height", DEFAULT_NOTE_HEIGHT) or DEFAULT_NOTE_HEIGHT)
        x = int(note.get("x", 200) or 200)
        y = int(note.get("y", 200) or 200)

        width = max(width, MIN_NOTE_WIDTH)
        height = max(height, MIN_NOTE_HEIGHT)
        expanded_height = max(expanded_height, MIN_NOTE_HEIGHT)

        max_x = max(screen_w - width, 0)
        max_y = max(screen_h - height, 0)
        x = min(max(x, 0), max_x)
        y = min(max(y, 0), max_y)

        note["width"] = width
        note["height"] = height
        note["expanded_height"] = expanded_height
        note["x"] = x
        note["y"] = y

    def hide_note_window(self, note_id: str) -> None:
        self.hide_note_window_internal(note_id, quit_if_no_visible_ui=False)

    def hide_note_window_internal(self, note_id: str, quit_if_no_visible_ui: bool) -> None:
        self._sync_note_from_window(note_id)
        if self._is_note_empty(note_id):
            self.delete_note(note_id, confirm=False)
            if quit_if_no_visible_ui:
                self._quit_if_no_visible_ui()
            return

        win = self.note_windows.get(note_id)
        if win:
            win.withdraw()
        if note_id in self.notes:
            self.notes[note_id]["visible"] = False
        self._refresh_note_list()
        self._save_notes()
        if quit_if_no_visible_ui:
            self._quit_if_no_visible_ui()

    def close_note_window(self, note_id: str) -> None:
        self._sync_note_from_window(note_id)
        if self._is_note_empty(note_id):
            self.delete_note(note_id, confirm=False)
            self._quit_if_no_visible_ui()
            return
        self.hide_note_window_internal(note_id, quit_if_no_visible_ui=True)

    def _quit_if_no_visible_ui(self) -> None:
        visible_notes = any(
            note.get("visible", True)
            for note in self.notes.values()
        )
        manager_visible = bool(
            self.manager_dialog
            and self.manager_dialog.winfo_exists()
            and self.manager_dialog.state() != "withdrawn"
        )
        settings_visible = bool(
            self.settings_dialog
            and self.settings_dialog.winfo_exists()
            and self.settings_dialog.state() != "withdrawn"
        )
        global_settings_visible = bool(
            self.global_settings_dialog
            and self.global_settings_dialog.winfo_exists()
            and self.global_settings_dialog.state() != "withdrawn"
        )
        help_visible = bool(
            self.help_window
            and self.help_window.winfo_exists()
            and self.help_window.state() != "withdrawn"
        )

        if not visible_notes and not manager_visible and not settings_visible and not global_settings_visible and not help_visible:
            self._quit_app()

    def delete_note(self, note_id: str, confirm: bool = True) -> None:
        if note_id not in self.notes:
            return

        title = self.notes[note_id]["title"]
        if confirm:
            ok = messagebox.askyesno("Delete Note", f"Delete '{title}'?")
            if not ok:
                return

        win = self.note_windows.pop(note_id, None)
        if win:
            win.destroy()

        if self.settings_dialog and self.settings_dialog.winfo_exists():
            if self.settings_dialog.note_id == note_id:
                self.settings_dialog.destroy()
                self.settings_dialog = None

        self.notes.pop(note_id, None)

        if not self.notes:
            new_note = self._default_note()
            self.notes[new_note["id"]] = new_note
            self.open_note_window(new_note["id"])

        self._refresh_note_list()
        self._save_notes()

    def update_note(self, note_id: str, refresh_list: bool = True, **changes) -> None:
        if note_id not in self.notes:
            return
        self.notes[note_id].update(changes)
        if refresh_list:
            self._refresh_note_list()
        self._queue_save()

    def rename_note(self, note_id: str, title: str) -> None:
        clean = title.strip() or "(Untitled)"
        self.update_note(note_id, title=clean)
        win = self.note_windows.get(note_id)
        if win and win.winfo_exists():
            if hasattr(win, "update_title_display"):
                win.update_title_display(clean)
            else:
                win.title(clean)

    def apply_note_color(self, note_id: str, color: str) -> None:
        self.update_note(note_id, bg=color)
        win = self.note_windows.get(note_id)
        if win and win.winfo_exists():
            win.apply_theme(color)

    def apply_note_appearance(self, note_id: str, font_size: int | None = None, opacity: float | None = None) -> None:
        note = self.notes.get(note_id)
        if not note:
            return

        changes = {}
        if font_size is not None:
            safe_size = max(8, min(24, int(font_size)))
            changes["font_size"] = safe_size
        if opacity is not None:
            safe_opacity = max(0.45, min(1.0, float(opacity)))
            changes["opacity"] = round(safe_opacity, 2)

        if changes:
            self.update_note(note_id, **changes)

        win = self.note_windows.get(note_id)
        if win and win.winfo_exists():
            win.apply_text_style()

    def show_all_notes(self) -> None:
        for note_id in list(self.notes.keys()):
            self.open_note_window(note_id)

    def close_all_notes(self) -> None:
        for note_id in list(self.notes.keys()):
            if note_id in self.note_windows:
                self._sync_note_from_window(note_id)

            if self._is_note_empty(note_id):
                self.delete_note(note_id, confirm=False)
                continue

            if note_id in self.notes:
                self.notes[note_id]["visible"] = False
            win = self.note_windows.get(note_id)
            if win and win.winfo_exists():
                win.withdraw()
        self._refresh_note_list()
        self._save_notes()

    def _visible_note_windows(self) -> list[NoteWindow]:
        windows = []
        for note_id in self.notes:
            if not self.notes[note_id].get("visible", True):
                continue
            win = self.note_windows.get(note_id)
            if win and win.winfo_exists():
                windows.append(win)
        return windows

    def arrange_notes(self, layout: str) -> None:
        windows = self._visible_note_windows()
        if not windows:
            self.show_all_notes()
            windows = self._visible_note_windows()
        if not windows:
            return

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        margin_x = 24
        margin_y = 56
        gap = 14
        usable_width = max(screen_width - margin_x * 2, 320)
        usable_height = max(screen_height - margin_y * 2, 220)
        count = len(windows)

        if layout == "horizontal":
            columns = count
            rows = 1
        elif layout == "vertical":
            columns = 1
            rows = count
        else:
            columns = max(1, int(count ** 0.5))
            while columns * columns < count:
                columns += 1
            rows = (count + columns - 1) // columns

        tile_width = DEFAULT_NOTE_WIDTH
        tile_height = DEFAULT_NOTE_HEIGHT

        for index, win in enumerate(windows):
            row = index // columns
            column = index % columns
            x = margin_x + column * (tile_width + gap)
            y = margin_y + row * (tile_height + gap)
            win._is_collapsed = False
            if win.note_id in self.notes:
                self.notes[win.note_id]["expanded_height"] = tile_height
            win.deiconify()
            win.geometry(f"{tile_width}x{tile_height}+{x}+{y}")
            win._apply_collapsed_state()
            self._sync_note_from_window(win.note_id)

        self._refresh_note_list()
        self._save_notes()

    def _keep_panels_on_top(self) -> None:
        for panel in (self.manager_dialog, self.settings_dialog, self.global_settings_dialog):
            if not panel or not panel.winfo_exists() or panel.state() == "withdrawn":
                continue
            try:
                panel.attributes("-topmost", True)
                panel.lift()
            except tk.TclError:
                continue

    def open_manager_dialog(self) -> None:
        self._ensure_single_manager_dialog()
        self.reconcile_notes_with_windows()
        if self.manager_dialog.state() != "withdrawn":
            self.hide_manager_dialog()
            return

        self.manager_dialog.deiconify()
        self.manager_dialog.lift()
        self.manager_dialog.focus_force()
        self.manager_dialog.refresh()
        self._keep_panels_on_top()
        self._queue_save()

    def hide_manager_dialog(self) -> None:
        if self.manager_dialog and self.manager_dialog.winfo_exists():
            self.manager_dialog.withdraw()
            self._queue_save()

    def open_note_settings(self, note_id: str) -> None:
        if self.settings_dialog and self.settings_dialog.winfo_exists():
            # Toggle behavior: same note + visible settings -> hide settings.
            is_visible = self.settings_dialog.state() != "withdrawn"
            if self.settings_dialog.note_id == note_id and is_visible:
                self.hide_settings_dialog()
                return

            self.settings_dialog.note_id = note_id
            self.settings_dialog.deiconify()
            self.settings_dialog.lift()
            self.settings_dialog.focus_force()
            self.settings_dialog.refresh()
            self._keep_panels_on_top()
            self._queue_save()
            return
        self.settings_dialog = AppNoteSettingsDialog(self, note_id, APP_ICON, DEFAULT_COLORS)
        self._keep_panels_on_top()
        self._queue_save()

    def hide_settings_dialog(self) -> None:
        if self.settings_dialog and self.settings_dialog.winfo_exists():
            self.settings_dialog.withdraw()
            self._queue_save()

    def open_help_window(self) -> None:
        if self.help_window and self.help_window.winfo_exists():
            self.help_window.deiconify()
            self.help_window.lift()
            self.help_window.focus_force()
            return
        self.help_window = HelpNoteWindow(self)

    def open_global_settings(self) -> None:
        if self.global_settings_dialog and self.global_settings_dialog.winfo_exists():
            if self.global_settings_dialog.state() != "withdrawn":
                self.hide_global_settings()
                return
            self.global_settings_dialog.deiconify()
            self.global_settings_dialog.lift()
            self.global_settings_dialog.focus_force()
            self.global_settings_dialog.refresh()
            self._keep_panels_on_top()
            self._queue_save()
            return

        self.global_settings_dialog = AppGlobalSettingsDialog(self, APP_ICON)
        self._keep_panels_on_top()
        self._queue_save()

    def hide_global_settings(self) -> None:
        if self.global_settings_dialog and self.global_settings_dialog.winfo_exists():
            self.global_settings_dialog.withdraw()
            self._queue_save()

    def _quit_app(self) -> None:
        if self._is_quitting:
            return
        self._is_quitting = True
        self._snapshot_runtime_state()
        self._save_notes()
        self._stop_tray_icon()
        self.root.destroy()


class NoteWindow(tk.Toplevel):
    def __init__(self, app: StickyNotesApp, note: dict) -> None:
        super().__init__(app.root)
        self.app = app
        self.note_id = note["id"]
        self._geometry_job = None
        self._is_collapsed = bool(note.get("collapsed", False))
        self._toast_window = None
        self._table_dialog = None
        self._drawing_dialog = None
        self._embedded_images = []
        self._embedded_widgets = []
        self._suspend_text_change = False
        self._collapsed_header_pack = []
        self._embedded_marker_seq = 0
        self._table_sync_jobs = {}
        self._resize_drag_start = None
        self._preferred_hkl = None
        self._prefer_korean_layout = False
        self._last_embedded_widget_count = 0

        self.title(note["title"])
        self.geometry(f"{note['width']}x{note['height']}+{note['x']}+{note['y']}")
        self.configure(bg=note["bg"])
        self.minsize(MIN_NOTE_WIDTH, MIN_NOTE_HEIGHT)
        self.attributes("-topmost", self.app.always_on_top)
        _apply_window_icon(self)

        self._build_ui(note)
        self._build_system_menu()

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.bind("<Configure>", self._on_configure)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<F2>", self._prompt_rename_note)
        self.after(150, self._apply_collapsed_state)
        self.after(220, self._ensure_visible_geometry)
        _debug_log(f"note_window_open note_id={self.note_id} title={self.title()}")

    def _ensure_visible_geometry(self) -> None:
        if not self.winfo_exists() or self._is_collapsed:
            return

        width = self.winfo_width()
        height = self.winfo_height()
        if width >= MIN_NOTE_WIDTH and height >= MIN_NOTE_HEIGHT:
            return

        note = self.app.notes.get(self.note_id)
        if not note:
            return

        self.app._normalize_note_geometry(note)
        self.geometry(
            f"{note['width']}x{note['height']}+{note['x']}+{note['y']}"
        )

    def _build_ui(self, note: dict) -> None:
        self.header = tk.Frame(self, bg=note["bg"], padx=8, pady=7)
        self.header.pack(fill="x")

        icon_font = ("Segoe UI Symbol", 10, "bold")
        self.fold_btn = self._create_header_button("—", "접기", self._toggle_collapse, icon_font)
        self.fold_btn.pack(side="left")
        self.new_btn = self._create_header_button("✚", "새 노트", self.app.create_note, icon_font)
        self.new_btn.pack(side="left", padx=(4, 0))
        self.copy_btn = self._create_header_button("⧉", "전체 복사", self._copy_note_content, icon_font)
        self.copy_btn.pack(side="left", padx=(4, 0))
        self.paste_btn = self._create_header_button("⎘", "붙여넣기", self._paste_note_content, icon_font)
        self.paste_btn.pack(side="left", padx=(4, 0))
        self.list_btn = self._create_header_button("☰", "노트 목록", self.app.open_manager_dialog, icon_font)
        self.list_btn.pack(side="left", padx=(4, 0))
        self.hide_btn = self._create_header_button("⤓", "숨기기", self._hide, icon_font)
        self.hide_btn.pack(side="left", padx=(4, 0))
        self.delete_btn = self._create_header_button("✕", "삭제", self._delete, icon_font)
        self.delete_btn.pack(side="left", padx=(4, 0))
        self.sticker_btn = self._create_header_button("🗒", "스티커 설정", lambda: self.app.open_note_settings(self.note_id), icon_font)
        self.sticker_btn.pack(side="left", padx=(4, 0))
        self.image_btn = self._create_header_button("🖼", "이미지 삽입", self._insert_image_file, icon_font)
        self.image_btn.pack(side="left", padx=(4, 0))
        self.draw_btn = self._create_header_button("✎", "그림 그리기", self._open_drawing_editor, icon_font)
        self.draw_btn.pack(side="left", padx=(4, 0))
        self.table_btn = self._create_header_button("▦", "표 입력", self._open_table_editor, icon_font)
        self.table_btn.pack(side="left", padx=(4, 0))
        self.global_btn = self._create_header_button("⚙", "전역 설정", self.app.open_global_settings, icon_font)
        self.global_btn.pack(side="left", padx=(4, 0))
        self.help_btn = self._create_header_button("?", "사용안내", self.app.open_help_window, icon_font)
        self.help_btn.pack(side="right")

        self.title_var = tk.StringVar(value=note["title"])
        self.title_label = tk.Label(
            self.header,
            textvariable=self.title_var,
            bg=note["bg"],
            fg="#4f473b",
            font=("Segoe UI", 9, "bold"),
            anchor="e",
            cursor="hand2",
        )
        self.title_label.pack(side="right", padx=(0, 8))
        self.title_label.bind("<Double-Button-1>", self._prompt_rename_note, add="+")
        self.title_label.bind("<Button-3>", self._show_note_context_menu, add="+")

        self.note_context_menu = tk.Menu(self, tearoff=0)
        self.note_context_menu.add_command(label="이름 변경 (F2)", command=self._prompt_rename_note)

        self.body = tk.Frame(self, bg=note["bg"])
        self.body.pack(fill="both", expand=True)

        self.text = tk.Text(
            self.body,
            wrap="word",
            undo=True,
            bg=note["bg"],
            relief="flat",
            padx=12,
            pady=12,
            font=("Segoe Print", 11),
            insertbackground="#554f42",
            highlightthickness=0,
        )
        self.text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.text.tag_configure("embedded_marker", elide=True)
        self._render_note_content(note["content"])
        self.text.bind("<KeyRelease>", self._on_text_change)
        self.text.bind("<FocusIn>", self._on_text_focus_in, add="+")
        self.text.bind("<KeyPress>", self._on_text_key_press, add="+")
        self.text.bind("<KeyRelease>", self._on_text_key_release_ime, add="+")

        self.resize_grip = tk.Label(
            self.body,
            text="◢",
            fg="#8a7f6d",
            bg=note["bg"],
            cursor="size_nw_se",
            font=("Segoe UI", 10, "bold"),
            padx=2,
            pady=0,
        )
        self.resize_grip.place(relx=1.0, rely=1.0, anchor="se", x=-3, y=-3)
        ToolTip(self.resize_grip, "드래그해서 크기 조절")
        self.resize_grip.bind("<ButtonPress-1>", self._on_resize_grip_press, add="+")
        self.resize_grip.bind("<B1-Motion>", self._on_resize_grip_drag, add="+")
        self.resize_grip.bind("<ButtonRelease-1>", self._on_resize_grip_release, add="+")

        self.apply_text_style()

        self._style_icon_buttons(note["bg"])

    def _build_system_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="저장", command=self._save_now)
        file_menu.add_separator()
        file_menu.add_command(label="새 노트", command=self.app.create_note)
        file_menu.add_command(label="백업 내보내기", command=self.app.export_backup_file)
        file_menu.add_command(label="백업 불러오기", command=self.app.import_backup_file)
        file_menu.add_separator()
        file_menu.add_command(label="닫기", command=self._on_window_close)
        file_menu.add_command(label="앱 종료", command=self.app._quit_app)
        menu_bar.add_cascade(label="파일", menu=file_menu)

        edit_menu = tk.Menu(menu_bar, tearoff=0)
        edit_menu.add_command(label="이름 바꾸기", command=self._prompt_rename_note)
        edit_menu.add_command(label="전체 복사", command=self._copy_note_content)
        edit_menu.add_command(label="붙여넣기", command=self._paste_note_content)
        menu_bar.add_cascade(label="편집", menu=edit_menu)

        insert_menu = tk.Menu(menu_bar, tearoff=0)
        insert_menu.add_command(label="이미지 삽입", command=self._insert_image_file)
        insert_menu.add_command(label="표 삽입", command=self._open_table_editor)
        insert_menu.add_command(label="그림 그리기", command=self._open_drawing_editor)
        menu_bar.add_cascade(label="삽입", menu=insert_menu)

        view_menu = tk.Menu(menu_bar, tearoff=0)
        view_menu.add_command(label="접기/펴기", command=self._toggle_collapse)
        view_menu.add_command(label="노트 목록", command=self.app.open_manager_dialog)
        menu_bar.add_cascade(label="보기", menu=view_menu)

        self.config(menu=menu_bar)
        self._menu_bar = menu_bar

    def _create_header_button(self, text: str, tooltip: str, command, font) -> tk.Button:
        button = tk.Button(
            self.header,
            text=text,
            width=3,
            font=font,
            command=command,
            cursor="hand2",
            takefocus=0,
        )
        button._tooltip = ToolTip(button, tooltip)
        return button

    def _save_now(self) -> None:
        self.app._sync_note_from_window(self.note_id)
        self.app._snapshot_runtime_state()
        self.app._save_notes()
        self._show_inline_toast("저장 완료", duration_ms=900)

    def _on_resize_grip_press(self, event=None) -> None:
        if event is None or self._is_collapsed:
            return
        self._resize_drag_start = (
            event.x_root,
            event.y_root,
            self.winfo_width(),
            self.winfo_height(),
        )

    def _on_resize_grip_drag(self, event=None) -> None:
        if event is None or self._is_collapsed or not self._resize_drag_start:
            return
        start_x, start_y, start_w, start_h = self._resize_drag_start
        delta_x = event.x_root - start_x
        delta_y = event.y_root - start_y
        new_w = max(MIN_NOTE_WIDTH, start_w + delta_x)
        new_h = max(MIN_NOTE_HEIGHT, start_h + delta_y)
        self.geometry(f"{new_w}x{new_h}+{self.winfo_x()}+{self.winfo_y()}")

    def _on_resize_grip_release(self, _event=None) -> None:
        self._resize_drag_start = None

    def _on_text_change(self, _event=None) -> None:
        if self._suspend_text_change:
            return

        alive_count = len([w for w in self._embedded_widgets if w.winfo_exists()])
        if alive_count < self._last_embedded_widget_count:
            _debug_log(
                f"embedded_widget_count_drop note_id={self.note_id} prev={self._last_embedded_widget_count} now={alive_count}"
            )
        self._last_embedded_widget_count = alive_count

        content = self.text.get("1.0", "end-1c")
        # Avoid refreshing the manager list on every keystroke to keep IME typing smooth.
        self.app.update_note(self.note_id, content=content, refresh_list=False)

    def _is_korean_hkl(self, hkl) -> bool:
        if not hkl:
            return False
        return (int(hkl) & 0xFFFF) == 0x0412

    def _current_hkl(self):
        try:
            return ctypes.windll.user32.GetKeyboardLayout(0)
        except Exception:
            return None

    def _sync_preferred_layout_from_system(self) -> None:
        hkl = self._current_hkl()
        if not hkl:
            return
        self._preferred_hkl = hkl
        self._prefer_korean_layout = self._is_korean_hkl(hkl)

    def _apply_preferred_korean_layout(self) -> None:
        if not self._prefer_korean_layout or not self._preferred_hkl:
            return
        try:
            current = self._current_hkl()
            if current and self._is_korean_hkl(current):
                return
            ctypes.windll.user32.ActivateKeyboardLayout(self._preferred_hkl, 0)
        except Exception:
            return

    def _on_text_focus_in(self, _event=None) -> None:
        self._sync_preferred_layout_from_system()
        self._apply_preferred_korean_layout()

    def _on_text_key_press(self, _event=None) -> None:
        self._apply_preferred_korean_layout()

    def _on_text_key_release_ime(self, event=None) -> None:
        if event is None:
            return
        keysym = (getattr(event, "keysym", "") or "").lower()
        keycode = int(getattr(event, "keycode", 0) or 0)
        state = int(getattr(event, "state", 0) or 0)

        # If the user intentionally changes input mode, accept the new layout.
        if keysym in {"hangul", "kanji", "hanguel"} or keycode in {21}:
            self.after(10, self._sync_preferred_layout_from_system)
            return

        # ALT/SHIFT transitions can indicate language switching.
        if keysym in {"alt_l", "alt_r", "shift_l", "shift_r", "control_l", "control_r"} or (state & 0x0001 and state & 0x0008):
            self.after(10, self._sync_preferred_layout_from_system)

    def _copy_note_content(self) -> None:
        content = self.text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()

    def _paste_note_content(self) -> None:
        if self._is_collapsed:
            self._show_inline_toast("노트를 펼친 뒤 붙여넣기 할 수 있습니다.")
            return

        try:
            clipboard_text = self.clipboard_get()
        except tk.TclError:
            clipboard_text = ""

        if not clipboard_text:
            return

        self.text.insert("insert", clipboard_text)
        self._on_text_change()

    def _open_table_editor(self) -> None:
        if self._is_collapsed:
            self._show_inline_toast("노트를 펼친 뒤 표를 삽입할 수 있습니다.")
            return

        if self._table_dialog and self._table_dialog.winfo_exists():
            self._table_dialog.deiconify()
            self._table_dialog.lift()
            self._table_dialog.focus_force()
            return

        self._table_dialog = TableEditorDialog(self)

    def _insert_image_file(self) -> None:
        if self._is_collapsed:
            self._show_inline_toast("노트를 펼친 뒤 이미지를 삽입할 수 있습니다.")
            return

        file_path = filedialog.askopenfilename(
            parent=self,
            title="이미지 선택",
            filetypes=[
                ("이미지 파일", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("모든 파일", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            copied = _copy_media_file(file_path)
            self.insert_image_reference(copied)
        except OSError as exc:
            messagebox.showerror("이미지 삽입", f"이미지를 복사하지 못했습니다.\n{exc}", parent=self)

    def _open_drawing_editor(self) -> None:
        if self._is_collapsed:
            self._show_inline_toast("노트를 펼친 뒤 그림을 삽입할 수 있습니다.")
            return

        if self._drawing_dialog and self._drawing_dialog.winfo_exists():
            self._drawing_dialog.deiconify()
            self._drawing_dialog.lift()
            self._drawing_dialog.focus_force()
            return

        self._drawing_dialog = DrawingEditorDialog(self)

    def insert_image_reference(self, image_path: Path) -> None:
        path_text = image_path.as_posix()
        marker = f"{EMBEDDED_IMG_PREFIX}{path_text}{EMBEDDED_MARKER_SUFFIX}"
        self._insert_hidden_marker("insert", marker)
        if not self._create_embedded_image("insert", path_text):
            self.text.insert("insert", f"[이미지 로드 실패] {path_text}")
        self.text.insert("insert", "\n")
        self._on_text_change()

    def insert_table_rows(self, rows: list[list[str]], merged_ranges: list[dict] | None = None) -> None:
        clean_rows = [[str(cell or "") for cell in row] for row in rows if row]
        if not clean_rows:
            return

        col_count = max((len(row) for row in clean_rows), default=0)
        normalized_merges = self._normalize_merged_ranges(merged_ranges or [], len(clean_rows), col_count)

        payload = base64.urlsafe_b64encode(
            json.dumps({"rows": clean_rows, "merged_ranges": normalized_merges}, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        marker = f"{EMBEDDED_TABLE_PREFIX}{payload}{EMBEDDED_MARKER_SUFFIX}"
        marker_name = self._insert_hidden_marker("insert", marker)
        if not self._create_embedded_table("insert", clean_rows, marker_name, normalized_merges):
            self.text.insert("insert", self._rows_to_markdown(clean_rows))
        self.text.insert("insert", "\n")
        self._on_text_change()

    def _rows_to_markdown(self, rows: list[list[str]]) -> str:
        if not rows:
            return ""
        col_count = len(rows[0])
        header = rows[0]
        body_rows = rows[1:] if len(rows) > 1 else []
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join(["---"] * col_count) + " |")
        for row in body_rows:
            padded = row + [""] * max(0, col_count - len(row))
            lines.append("| " + " | ".join(padded[:col_count]) + " |")
        return "\n".join(lines)

    def _insert_hidden_marker(self, index: str, marker: str) -> str:
        marker_index = self.text.index(index)
        self.text.insert(index, marker + "\n", ("embedded_marker",))
        marker_name = f"_embed_marker_{self._embedded_marker_seq}"
        self._embedded_marker_seq += 1
        self.text.mark_set(marker_name, marker_index)
        self.text.mark_gravity(marker_name, tk.LEFT)
        marker_type = "table" if marker.startswith(EMBEDDED_TABLE_PREFIX) else "image"
        _debug_log(f"marker_insert note_id={self.note_id} marker={marker_name} type={marker_type} index={marker_index}")
        return marker_name

    def _clear_embedded_objects(self) -> None:
        for job in self._table_sync_jobs.values():
            if job is None:
                continue
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._table_sync_jobs.clear()

        for mark_name in list(self.text.mark_names()):
            if mark_name.startswith("_embed_marker_"):
                try:
                    self.text.mark_unset(mark_name)
                except tk.TclError:
                    pass

        self._embedded_images.clear()
        self._embedded_widgets.clear()

    def _render_note_content(self, content: str) -> None:
        self._suspend_text_change = True
        _debug_log(f"render_start note_id={self.note_id} chars={len(content)}")
        try:
            self.text.delete("1.0", "end")
            self._clear_embedded_objects()
            lines = content.splitlines()
            idx = 0
            while idx < len(lines):
                line = lines[idx]

                if self._render_embedded_marker_from_line(line):
                    idx += 1
                    continue

                if self._render_markdown_image_line(line):
                    idx += 1
                    continue

                table_rows, consumed = self._parse_markdown_table(lines, idx)
                if table_rows and consumed > 0:
                    payload = base64.urlsafe_b64encode(
                        json.dumps({"rows": table_rows, "merged_ranges": []}, ensure_ascii=False).encode("utf-8")
                    ).decode("ascii")
                    marker = f"{EMBEDDED_TABLE_PREFIX}{payload}{EMBEDDED_MARKER_SUFFIX}"
                    marker_name = self._insert_hidden_marker("end", marker)
                    if not self._create_embedded_table("end", table_rows, marker_name, []):
                        self.text.insert("end", self._rows_to_markdown(table_rows))
                    self.text.insert("end", "\n")
                    idx += consumed
                    continue

                self.text.insert("end", line + "\n")
                idx += 1
        finally:
            self._suspend_text_change = False
            alive_count = len([w for w in self._embedded_widgets if w.winfo_exists()])
            self._last_embedded_widget_count = alive_count
            _debug_log(f"render_end note_id={self.note_id} embedded_widgets={alive_count}")

    def _render_markdown_image_line(self, line: str) -> bool:
        stripped = line.strip()
        match = re.fullmatch(r"!\[[^\]]*\]\((.+)\)", stripped)
        if not match:
            return False

        path_text = match.group(1).strip()
        marker = f"{EMBEDDED_IMG_PREFIX}{path_text}{EMBEDDED_MARKER_SUFFIX}"
        self._insert_hidden_marker("end", marker)
        if not self._create_embedded_image("end", path_text):
            self.text.insert("end", f"[이미지 로드 실패] {path_text}")
        self.text.insert("end", "\n")
        return True

    def _parse_markdown_table(self, lines: list[str], start_index: int) -> tuple[list[list[str]] | None, int]:
        if start_index + 1 >= len(lines):
            return None, 0

        header_line = lines[start_index].strip()
        sep_line = lines[start_index + 1].strip()
        if not self._looks_like_table_row(header_line):
            return None, 0
        if not self._looks_like_table_separator(sep_line):
            return None, 0

        rows = [self._split_table_row(header_line)]
        consumed = 2
        cursor = start_index + 2
        while cursor < len(lines):
            row_line = lines[cursor].strip()
            if not self._looks_like_table_row(row_line):
                break
            rows.append(self._split_table_row(row_line))
            consumed += 1
            cursor += 1

        if len(rows) < 1:
            return None, 0
        return rows, consumed

    def _looks_like_table_row(self, line: str) -> bool:
        return line.startswith("|") and line.endswith("|") and "|" in line[1:-1]

    def _looks_like_table_separator(self, line: str) -> bool:
        if not self._looks_like_table_row(line):
            return False
        cells = self._split_table_row(line)
        if not cells:
            return False
        for cell in cells:
            token = cell.replace(":", "").replace("-", "").strip()
            if token:
                return False
            if "-" not in cell:
                return False
        return True

    def _split_table_row(self, line: str) -> list[str]:
        core = line.strip()[1:-1]
        return [part.strip() for part in core.split("|")]

    def _render_embedded_marker_from_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped.endswith(EMBEDDED_MARKER_SUFFIX):
            return False

        if stripped.startswith(EMBEDDED_IMG_PREFIX):
            path_text = stripped[len(EMBEDDED_IMG_PREFIX):-len(EMBEDDED_MARKER_SUFFIX)]
            self._insert_hidden_marker("end", stripped)
            if not self._create_embedded_image("end", path_text):
                self.text.insert("end", f"[이미지 로드 실패] {path_text}")
            self.text.insert("end", "\n")
            return True

        if stripped.startswith(EMBEDDED_TABLE_PREFIX):
            payload = stripped[len(EMBEDDED_TABLE_PREFIX):-len(EMBEDDED_MARKER_SUFFIX)]
            rows, merged_ranges = self._decode_table_rows(payload)
            if rows is None:
                return False
            marker_name = self._insert_hidden_marker("end", stripped)
            if not self._create_embedded_table("end", rows, marker_name, merged_ranges):
                self.text.insert("end", self._rows_to_markdown(rows))
            self.text.insert("end", "\n")
            return True

        return False

    def _decode_table_rows(self, payload: str) -> tuple[list[list[str]] | None, list[dict]]:
        try:
            decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
            data = json.loads(decoded)
        except Exception:
            return None, []

        merged_ranges: list[dict] = []
        if isinstance(data, dict):
            rows_raw = data.get("rows")
            merged_ranges_raw = data.get("merged_ranges") or []
        else:
            rows_raw = data
            merged_ranges_raw = []

        if not isinstance(rows_raw, list):
            return None, []
        rows = []
        for row in rows_raw:
            if isinstance(row, list):
                rows.append([str(cell) for cell in row])
        if not rows:
            return None, []

        col_count = max((len(row) for row in rows), default=0)
        merged_ranges = self._normalize_merged_ranges(merged_ranges_raw, len(rows), col_count)
        return rows, merged_ranges

    def _normalize_merged_ranges(self, merged_ranges: list[dict], row_count: int, col_count: int) -> list[dict]:
        normalized = []
        if row_count <= 0 or col_count <= 0:
            return normalized

        for merge in merged_ranges:
            if not isinstance(merge, dict):
                continue
            try:
                r = int(merge.get("r", -1))
                c = int(merge.get("c", -1))
                rowspan = int(merge.get("rowspan", 1))
                colspan = int(merge.get("colspan", 1))
            except Exception:
                continue

            if r < 0 or c < 0 or rowspan < 2 or colspan < 2:
                continue
            if r >= row_count or c >= col_count:
                continue

            max_rowspan = row_count - r
            max_colspan = col_count - c
            rowspan = min(rowspan, max_rowspan)
            colspan = min(colspan, max_colspan)
            if rowspan < 2 and colspan < 2:
                continue

            normalized.append({"r": r, "c": c, "rowspan": rowspan, "colspan": colspan})

        return normalized

    def _create_embedded_image(self, index: str, path_text: str) -> bool:
        if not PILLOW_AVAILABLE or not Image or not ImageTk:
            return False
        try:
            image_path = Path(path_text)
            if not image_path.exists():
                return False
            image = Image.open(image_path)
            image.thumbnail((360, 220))
            photo = ImageTk.PhotoImage(image)
            self._embedded_images.append(photo)
            self.text.image_create(index, image=photo, padx=3, pady=3)
            return True
        except Exception:
            return False

    def _create_embedded_table(self, index: str, rows: list[list[str]], marker_name: str, merged_ranges: list[dict] | None = None) -> bool:
        if not rows:
            return False
        try:
            col_count = max(len(row) for row in rows)
            data_rows = [row + [""] * (col_count - len(row)) for row in rows]
            normalized_merges = self._normalize_merged_ranges(merged_ranges or [], len(data_rows), col_count)

            frame = tk.Frame(self.text, bg="#d8ccb8", bd=1, relief="solid")
            frame._table_id = uuid.uuid4().hex[:8]
            frame._table_rows = data_rows
            frame._table_merges = normalized_merges
            frame._table_entries = {}
            frame._table_vars = {}

            # Disable double-click gestures on embedded tables to avoid
            # accidental event paths that can destabilize widget state.
            frame.bind("<Double-Button-1>", lambda _event: "break", add="+")
            frame.bind("<Triple-Button-1>", lambda _event: "break", add="+")

            _debug_log(
                f"table_create note_id={self.note_id} table_id={frame._table_id} marker={marker_name} rows={len(data_rows)} cols={col_count} merges={len(normalized_merges)}"
            )

            def merge_at_top_left(rr: int, cc: int):
                for merge in frame._table_merges:
                    if merge["r"] == rr and merge["c"] == cc:
                        return merge
                return None

            def hidden_by_merge(rr: int, cc: int) -> bool:
                for merge in frame._table_merges:
                    if merge["r"] <= rr < merge["r"] + merge["rowspan"] and merge["c"] <= cc < merge["c"] + merge["colspan"]:
                        return not (merge["r"] == rr and merge["c"] == cc)
                return False

            for r, row in enumerate(data_rows):
                for c in range(col_count):
                    if hidden_by_merge(r, c):
                        continue
                    merge = merge_at_top_left(r, c)
                    rowspan = merge["rowspan"] if merge else 1
                    colspan = merge["colspan"] if merge else 1

                    cell_text = row[c]
                    bg = "#fff9e3" if r == 0 else "#fffdf6"
                    cell_var = tk.StringVar(value=cell_text)
                    entry = tk.Entry(
                        frame,
                        textvariable=cell_var,
                        relief="flat",
                        bd=0,
                        bg=bg,
                        fg="#4a4236",
                        width=12,
                        justify="left",
                    )
                    entry.grid(row=r, column=c, rowspan=rowspan, columnspan=colspan, sticky="nsew", padx=1, pady=1, ipadx=3, ipady=2)
                    frame._table_entries[(r, c)] = entry
                    frame._table_vars[(r, c)] = cell_var
                    entry.bind("<Double-Button-1>", lambda _event: "break", add="+")
                    entry.bind("<Triple-Button-1>", lambda _event: "break", add="+")
                    cell_var.trace_add(
                        "write",
                        lambda *_args, mark=marker_name, table_frame=frame, rr=r, cc=c, var=cell_var: self._on_embedded_table_var_change(mark, table_frame, rr, cc, var),
                    )
                    entry.bind(
                        "<KeyRelease>",
                        lambda _event, mark=marker_name, table_frame=frame, rr=r, cc=c: self._on_embedded_table_entry_change(mark, table_frame, rr, cc),
                        add="+",
                    )
                    entry.bind(
                        "<FocusOut>",
                        lambda _event, mark=marker_name, table_frame=frame, rr=r, cc=c: self._on_embedded_table_entry_change(mark, table_frame, rr, cc),
                        add="+",
                    )
                frame.grid_rowconfigure(r, weight=1)
            for c in range(col_count):
                frame.grid_columnconfigure(c, weight=1)

            self.text.window_create(index, window=frame, padx=2, pady=2)
            self._embedded_widgets.append(frame)
            frame.bind(
                "<Destroy>",
                lambda _event, table_id=frame._table_id, mark=marker_name: _debug_log(
                    f"table_destroy note_id={self.note_id} table_id={table_id} marker={mark}"
                ),
                add="+",
            )
            return True
        except Exception:
            _debug_log(f"table_create_error note_id={self.note_id} marker={marker_name}")
            return False

    def _on_embedded_table_entry_change(self, marker_name: str, frame: tk.Frame, row: int, col: int) -> None:
        try:
            entry = frame._table_entries.get((row, col))
            if entry is None:
                return
            frame._table_rows[row][col] = entry.get().strip()
        except Exception:
            return
        self._queue_sync_embedded_table_marker(marker_name, frame)

    def _on_embedded_table_var_change(self, marker_name: str, frame: tk.Frame, row: int, col: int, var: tk.StringVar) -> None:
        try:
            frame._table_rows[row][col] = var.get().strip()
        except Exception:
            return
        self._queue_sync_embedded_table_marker(marker_name, frame)

    def _queue_sync_embedded_table_marker(self, marker_name: str, frame: tk.Frame | list[list[tk.Entry]]) -> None:
        prev_job = self._table_sync_jobs.get(marker_name)
        if prev_job is not None:
            try:
                self.after_cancel(prev_job)
            except Exception:
                pass
        self._table_sync_jobs[marker_name] = self.after(
            220,
            lambda mark=marker_name, table_frame=frame: self._sync_embedded_table_marker(mark, table_frame),
        )

    def _sync_embedded_table_marker(self, marker_name: str, frame: tk.Frame | list[list[tk.Entry]]) -> None:
        self._table_sync_jobs[marker_name] = None
        if marker_name not in self.text.mark_names():
            _debug_log(f"table_sync_skip_missing_marker note_id={self.note_id} marker={marker_name}")
            return

        rows: list[list[str]] = []
        merged_ranges: list[dict] = []
        if isinstance(frame, list):
            try:
                for row_entries in frame:
                    rows.append([entry.get().strip() for entry in row_entries])
            except Exception:
                return
        else:
            try:
                rows = [[str(cell or "") for cell in row] for row in frame._table_rows]
                merged_ranges = self._normalize_merged_ranges(frame._table_merges, len(rows), len(rows[0]) if rows else 0)
            except Exception:
                return

        payload = base64.urlsafe_b64encode(
            json.dumps({"rows": rows, "merged_ranges": merged_ranges}, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        marker = f"{EMBEDDED_TABLE_PREFIX}{payload}{EMBEDDED_MARKER_SUFFIX}"

        alive_count_before = len([w for w in self._embedded_widgets if w.winfo_exists()])
        _debug_log(
            f"table_sync_start note_id={self.note_id} marker={marker_name} rows={len(rows)} cols={(len(rows[0]) if rows else 0)} alive_before={alive_count_before}"
        )

        marker_index = self.text.index(marker_name)
        line_end = self.text.index(f"{marker_index} lineend")

        self._suspend_text_change = True
        try:
            # Replace only marker text. Deleting the trailing newline can also
            # consume adjacent embedded windows in the next visual line.
            self.text.delete(marker_index, line_end)
            self.text.insert(marker_index, marker, ("embedded_marker",))
            self.text.mark_set(marker_name, marker_index)
            self.text.mark_gravity(marker_name, tk.LEFT)
        finally:
            self._suspend_text_change = False

        alive_count_after = len([w for w in self._embedded_widgets if w.winfo_exists()])
        _debug_log(
            f"table_sync_end note_id={self.note_id} marker={marker_name} alive_after={alive_count_after}"
        )

        self._on_text_change()

    def _show_inline_toast(self, message: str, duration_ms: int = 1300) -> None:
        if self._toast_window and self._toast_window.winfo_exists():
            self._toast_window.destroy()

        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#4a4337")

        label = tk.Label(
            toast,
            text=message,
            bg="#4a4337",
            fg="#fff7e6",
            padx=10,
            pady=6,
            font=("Segoe UI", 9, "bold"),
        )
        label.pack()

        self.update_idletasks()
        toast.update_idletasks()
        x = self.winfo_rootx() + max(8, (self.winfo_width() - toast.winfo_reqwidth()) // 2)
        y = self.winfo_rooty() + 54
        toast.geometry(f"+{x}+{y}")

        self._toast_window = toast
        toast.after(duration_ms, lambda: toast.destroy() if toast.winfo_exists() else None)

    def _style_icon_buttons(self, color: str) -> None:
        base_color = _mix_color(color, "#fffdf8", 0.15)
        hover_color = _mix_color(color, "#ffffff", 0.32)
        for child in self.header.winfo_children():
            if isinstance(child, tk.Button):
                child.configure(
                    bg=base_color,
                    fg="#5d5549",
                    activebackground=hover_color,
                    activeforeground="#433c32",
                    relief="flat",
                    bd=0,
                    padx=2,
                    pady=2,
                    highlightthickness=0,
                )
                child.bind("<Enter>", lambda _event, button=child: button.configure(bg=hover_color), add="+")
                child.bind("<Leave>", lambda _event, button=child: button.configure(bg=base_color), add="+")

    def apply_theme(self, color: str) -> None:
        self.configure(bg=color)
        self.header.configure(bg=color)
        self.title_label.configure(bg=color)
        self.body.configure(bg=color)
        self.text.configure(bg=color)
        if hasattr(self, "resize_grip") and self.resize_grip.winfo_exists():
            self.resize_grip.configure(bg=color)
        self._style_icon_buttons(color)

    def apply_text_style(self) -> None:
        note = self.app.notes.get(self.note_id, {})
        font_size = int(note.get("font_size", 11) or 11)
        opacity = float(note.get("opacity", 1.0) or 1.0)
        self.text.configure(font=("Segoe Print", max(8, min(24, font_size))))
        try:
            self.attributes("-alpha", max(0.45, min(1.0, opacity)))
        except tk.TclError:
            pass

    def _prompt_rename_note(self, _event=None) -> None:
        current = self.app.notes.get(self.note_id, {}).get("title", self.title())
        new_title = simpledialog.askstring("이름 변경", "노트 이름", initialvalue=current, parent=self)
        if new_title is None:
            return
        new_title = new_title.strip()
        if not new_title:
            return
        self.app.rename_note(self.note_id, new_title)

    def _show_note_context_menu(self, event=None) -> None:
        if event is None:
            return
        try:
            self.note_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.note_context_menu.grab_release()

    def update_title_display(self, title: str) -> None:
        self.title(title)
        self.title_var.set(title)

    def _toggle_collapse(self) -> None:
        self._is_collapsed = not self._is_collapsed
        self._apply_collapsed_state()

    def _apply_collapsed_header_mode(self) -> None:
        self._collapsed_header_pack = []
        for widget in self.header.winfo_children():
            if widget is self.fold_btn:
                continue
            manager = widget.winfo_manager()
            if manager != "pack":
                continue
            pack_info = widget.pack_info()
            pack_info.pop("in", None)
            self._collapsed_header_pack.append((widget, pack_info))
            widget.pack_forget()

    def _restore_header_mode(self) -> None:
        if not self._collapsed_header_pack:
            return
        for widget, pack_info in self._collapsed_header_pack:
            try:
                widget.pack(**pack_info)
            except tk.TclError:
                continue
        self._collapsed_header_pack = []

    def _apply_collapsed_state(self) -> None:
        if self._is_collapsed:
            current_h = max(self.winfo_height(), MIN_NOTE_HEIGHT)
            self.app.update_note(self.note_id, expanded_height=current_h)
            self._apply_collapsed_header_mode()
            if self.body.winfo_manager():
                self.body.pack_forget()
            self.fold_btn.config(text="▣")
            if hasattr(self.fold_btn, "_tooltip"):
                self.fold_btn._tooltip.set_text("펴기")
            self.minsize(MIN_NOTE_WIDTH, 34)
            self.update_idletasks()
            self.geometry(f"{self.winfo_width()}x34+{self.winfo_x()}+{self.winfo_y()}")
        else:
            target_h = int(self.app.notes.get(self.note_id, {}).get("expanded_height", 260))
            self._restore_header_mode()
            if not self.body.winfo_manager():
                self.body.pack(fill="both", expand=True)
            self.fold_btn.config(text="—")
            if hasattr(self.fold_btn, "_tooltip"):
                self.fold_btn._tooltip.set_text("접기")
            self.minsize(MIN_NOTE_WIDTH, MIN_NOTE_HEIGHT)
            self.update_idletasks()
            self.geometry(f"{self.winfo_width()}x{max(target_h, MIN_NOTE_HEIGHT)}+{self.winfo_x()}+{self.winfo_y()}")

        self.app.update_note(self.note_id, collapsed=self._is_collapsed)

    def _hide(self) -> None:
        self.app._sync_note_from_window(self.note_id)
        self.app.hide_note_window(self.note_id)

    def _on_window_close(self) -> None:
        self.app.close_note_window(self.note_id)

    def _delete(self) -> None:
        self.app.delete_note(self.note_id)

    def destroy(self) -> None:
        if self._table_dialog and self._table_dialog.winfo_exists():
            self._table_dialog.destroy()
        if self._drawing_dialog and self._drawing_dialog.winfo_exists():
            self._drawing_dialog.destroy()
        if self._toast_window and self._toast_window.winfo_exists():
            self._toast_window.destroy()
        self._clear_embedded_objects()
        super().destroy()

    def _on_configure(self, _event=None) -> None:
        if self._geometry_job is not None:
            self.after_cancel(self._geometry_job)
        self._geometry_job = self.after(200, self._save_geometry)

    def _on_focus_in(self, _event=None) -> None:
        self.app._last_active_note_id = self.note_id
        self.app._keep_panels_on_top()

    def _save_geometry(self) -> None:
        self._geometry_job = None
        self.update_idletasks()
        self.app.update_note(
            self.note_id,
            x=self.winfo_x(),
            y=self.winfo_y(),
            width=self.winfo_width(),
            height=self.winfo_height(),
        )

        if not self._is_collapsed:
            self.app.update_note(self.note_id, expanded_height=self.winfo_height())


class NotesManagerDialog(tk.Toplevel):
    def __init__(self, app: StickyNotesApp) -> None:
        super().__init__(app.root)
        self.app = app
        self.note_ids = []

        self.title("노트 목록")
        self.geometry("320x420")
        self.minsize(280, 320)
        self.attributes("-topmost", True)
        _apply_window_icon(self)

        top = tk.Frame(self, padx=10, pady=10)
        top.pack(fill="x")

        tk.Button(top, text="New", command=self.app.create_note, width=9).pack(side="left")
        tk.Button(top, text="Open All", command=self.app.show_all_notes, width=9).pack(side="left", padx=6)
        tk.Button(top, text="Global", command=self.app.open_global_settings, width=9).pack(side="left", padx=6)
        tk.Button(top, text="Exit", command=self.app.hide_manager_dialog, width=9).pack(side="right")

        layout_row = tk.Frame(self, padx=10, pady=0)
        layout_row.pack(fill="x", pady=(0, 8))
        self._create_layout_button(layout_row, "⇆", "가로배치", lambda: self.app.arrange_notes("horizontal")).pack(side="left")
        self._create_layout_button(layout_row, "⇅", "세로배치", lambda: self.app.arrange_notes("vertical")).pack(side="left", padx=6)
        self._create_layout_button(layout_row, "▦", "바둑판배열", lambda: self.app.arrange_notes("grid")).pack(side="left")
        self._create_layout_button(layout_row, "◫", "열려있는 모든 노트", self.app.show_all_notes).pack(side="left", padx=6)
        self._create_layout_button(layout_row, "—", "일괄닫기", self.app.close_all_notes).pack(side="right")

        list_header = tk.Frame(self, padx=10, pady=0)
        list_header.pack(fill="x", pady=(0, 4))
        tk.Label(list_header, text="노트 목록", anchor="w").pack(side="left")
        self.rename_icon_btn = tk.Button(
            list_header,
            text="✎",
            width=3,
            command=self._begin_inline_rename,
            font=("Segoe UI Symbol", 10, "bold"),
            cursor="hand2",
            relief="flat",
            bd=0,
            bg="#f6f0eb",
            activebackground="#fff7f1",
            activeforeground="#4d4638",
            fg="#5d5549",
            highlightthickness=0,
            padx=2,
            pady=2,
            takefocus=0,
        )
        ToolTip(self.rename_icon_btn, "선택한 노트 이름변경")
        self.rename_icon_btn.pack(side="right")
        self.rename_icon_btn.pack_forget()

        filter_row = tk.Frame(self, padx=10, pady=0)
        filter_row.pack(fill="x", pady=(0, 6))
        tk.Label(filter_row, text="검색", width=4, anchor="w").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_args: self.refresh())
        self.filter_entry = tk.Entry(filter_row, textvariable=self.filter_var)
        self.filter_entry.pack(side="left", fill="x", expand=True)

        list_frame = tk.Frame(self, padx=10, pady=0)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.note_list = tk.Listbox(list_frame)
        self.note_list.configure(bg="#fffdf7", fg="#403828", selectbackground="#eacb63", selectforeground="#2f281c")
        self.note_list.pack(side="left", fill="both", expand=True)
        self.note_list.bind("<Double-Button-1>", self._open_selected_note)
        self.note_list.bind("<ButtonRelease-1>", self._on_list_click_release, add="+")
        self.note_list.bind("<Button-3>", self._on_list_right_click, add="+")
        self.note_list.bind("<<ListboxSelect>>", self._on_list_select)
        self.note_list.bind("<F2>", self._on_list_f2, add="+")

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.note_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.note_list.config(yscrollcommand=scrollbar.set)

        self._renaming_note_id = None
        self._last_selected_note_id = None
        self._last_click_index = None
        self._last_click_ts = 0.0
        self.rename_entry_var = tk.StringVar()
        self.rename_popup = None
        self.rename_entry = None
        self.rename_ok_btn = None
        self.rename_cancel_btn = None

        self.list_context_menu = tk.Menu(self, tearoff=0)
        self.list_context_menu.add_command(label="이름 변경 (F2)", command=self._begin_inline_rename)

        bottom = tk.Frame(self, padx=10, pady=0)
        bottom.pack(fill="x", pady=(0, 10))

        tk.Button(bottom, text="Open", command=self._open_selected_note, width=10).pack(side="left")
        tk.Button(bottom, text="Hide", command=self._hide_selected_note, width=10).pack(side="left", padx=6)
        tk.Button(bottom, text="Delete", command=self._delete_selected_note, width=10).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.app.hide_manager_dialog)
        self.refresh()
        self.bind("<F2>", self._on_list_f2, add="+")

    def _create_layout_button(self, parent: tk.Widget, text: str, tooltip: str, command) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            width=4,
            command=command,
            font=("Segoe UI Symbol", 10, "bold"),
            cursor="hand2",
            relief="flat",
            bd=0,
            bg="#f6f0eb",
            activebackground="#fff7f1",
            activeforeground="#4d4638",
            fg="#5d5549",
            highlightthickness=0,
            padx=4,
            pady=4,
        )
        ToolTip(button, tooltip)
        button.bind("<Enter>", lambda _event, control=button: control.configure(bg="#fff7f1"), add="+")
        button.bind("<Leave>", lambda _event, control=button: control.configure(bg="#f6f0eb"), add="+")
        return button

    def refresh(self) -> None:
        active_rename_id = self._renaming_note_id
        active_rename_text = self.rename_entry_var.get() if active_rename_id else ""

        self.app.reconcile_notes_with_windows()
        selected_note_id = self._selected_note_id()
        all_note_ids = list(self.app.notes.keys())
        query = (self.filter_var.get() or "").strip().lower()
        if query:
            self.note_ids = []
            for note_id in all_note_ids:
                note = self.app.notes[note_id]
                haystack = f"{note.get('title', '')}\n{note.get('content', '')}".lower()
                if query in haystack:
                    self.note_ids.append(note_id)
        else:
            self.note_ids = all_note_ids
        self.note_list.delete(0, tk.END)
        for note_id in self.note_ids:
            note = self.app.notes[note_id]
            status = "shown" if note.get("visible", True) else "🔒 hidden"
            preview = self.app.note_preview(note_id)
            self.note_list.insert(tk.END, f"{note['title']}  [{status}]  {preview}")

        if self.app._last_created_note_id in self.note_ids:
            idx = self.note_ids.index(self.app._last_created_note_id)
            self.note_list.selection_clear(0, tk.END)
            self.note_list.selection_set(idx)
            self.note_list.see(idx)
            self._on_list_select()
            self.app._last_created_note_id = None
        elif selected_note_id in self.note_ids:
            idx = self.note_ids.index(selected_note_id)
            self.note_list.selection_clear(0, tk.END)
            self.note_list.selection_set(idx)
            self.note_list.see(idx)
            self._on_list_select()
        else:
            self.note_list.selection_clear(0, tk.END)
            self._on_list_select()

        if active_rename_id and active_rename_id in self.note_ids:
            idx = self.note_ids.index(active_rename_id)
            self.rename_entry_var.set(active_rename_text)
            self._begin_inline_rename(note_id=active_rename_id, idx=idx, preserve_text=True)
        elif active_rename_id:
            self._cancel_inline_rename()

    def _selected_note_id(self):
        idxs = self.note_list.curselection()
        if idxs:
            idx = idxs[0]
            if 0 <= idx < len(self.note_ids):
                return self.note_ids[idx]

        if self._last_selected_note_id in self.note_ids:
            return self._last_selected_note_id
        return None

    def _open_selected_note(self, _event=None) -> None:
        note_id = self._selected_note_id()
        if note_id:
            self.app.open_note_window(note_id)

    def _selected_note_title(self) -> str:
        note_id = self._selected_note_id()
        if not note_id:
            return ""
        return self.app.notes.get(note_id, {}).get("title", "")

    def _selected_note_index(self):
        idxs = self.note_list.curselection()
        if not idxs:
            return None
        return idxs[0]

    def _on_list_select(self, _event=None) -> None:
        selected_note_id = None
        idxs = self.note_list.curselection()
        if idxs:
            idx = idxs[0]
            if 0 <= idx < len(self.note_ids):
                selected_note_id = self.note_ids[idx]

        if selected_note_id:
            self._last_selected_note_id = selected_note_id
            if not self.rename_icon_btn.winfo_manager():
                self.rename_icon_btn.pack(side="right")
        else:
            if self.rename_icon_btn.winfo_manager():
                self.rename_icon_btn.pack_forget()
            self._cancel_inline_rename()

    def _on_list_click_release(self, event=None) -> None:
        if event is None:
            return

        idx = self.note_list.nearest(event.y)
        if idx < 0 or idx >= len(self.note_ids):
            return

        bbox = self.note_list.bbox(idx)
        if not bbox:
            return

        x, y, width, height = bbox
        inside_item = (x <= event.x <= x + width) and (y <= event.y <= y + height)
        if not inside_item:
            return

        now = time.monotonic()
        if self._last_click_index == idx and (now - self._last_click_ts) >= 0.45:
            self._begin_inline_rename(note_id=self.note_ids[idx], idx=idx)

        self._last_click_index = idx
        self._last_click_ts = now

    def _on_list_right_click(self, event=None) -> None:
        if event is None:
            return

        idx = self.note_list.nearest(event.y)
        if 0 <= idx < len(self.note_ids):
            self.note_list.selection_clear(0, tk.END)
            self.note_list.selection_set(idx)
            self.note_list.see(idx)
            self._on_list_select()

        try:
            self.list_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.list_context_menu.grab_release()

    def _on_list_f2(self, _event=None) -> str:
        self._begin_inline_rename()
        return "break"

    def _begin_inline_rename(self, note_id=None, idx=None, preserve_text: bool = False) -> None:
        if note_id is None:
            note_id = self._selected_note_id()
        if idx is None:
            idx = self._selected_note_index()

        if note_id is None and self._last_selected_note_id in self.note_ids:
            note_id = self._last_selected_note_id
        if idx is None and note_id in self.note_ids:
            idx = self.note_ids.index(note_id)

        if not note_id or idx is None:
            return

        self.note_list.see(idx)
        self.note_list.update_idletasks()
        bbox = self.note_list.bbox(idx)
        if not bbox:
            return

        self._ensure_rename_popup()
        if not self.rename_popup or not self.rename_entry:
            return

        x, y, width, height = bbox
        self._renaming_note_id = note_id
        if not preserve_text:
            self.rename_entry_var.set(self.app.notes.get(note_id, {}).get("title", ""))

        root_x = self.note_list.winfo_rootx() + x + 1
        root_y = self.note_list.winfo_rooty() + y + 1
        popup_width = max(width - 2, 140)
        popup_height = max(height - 2, 24)
        self.rename_popup.geometry(f"{popup_width}x{popup_height}+{root_x}+{root_y}")
        self.rename_popup.deiconify()
        self.rename_popup.lift()
        self.rename_entry.focus_set()
        self.rename_entry.selection_range(0, tk.END)

    def _commit_inline_rename(self, _event=None) -> None:
        if not self._renaming_note_id:
            return

        new_title = self.rename_entry_var.get().strip()
        if not new_title:
            if self.rename_entry:
                self.rename_entry.focus_set()
            return

        target_note_id = self._renaming_note_id
        self.app.rename_note(target_note_id, new_title)
        self._cancel_inline_rename()
        self.refresh()

        if target_note_id in self.note_ids:
            idx = self.note_ids.index(target_note_id)
            self.note_list.selection_clear(0, tk.END)
            self.note_list.selection_set(idx)
            self.note_list.see(idx)
            self._on_list_select()

    def _cancel_inline_rename(self, _event=None) -> None:
        self._renaming_note_id = None
        if self.rename_popup and self.rename_popup.winfo_exists():
            self.rename_popup.withdraw()

    def _on_rename_entry_focus_out(self, _event=None) -> None:
        if not self._renaming_note_id:
            return

        self.after(40, self._apply_rename_on_focus_change)

    def _apply_rename_on_focus_change(self) -> None:
        if not self._renaming_note_id:
            return

        focused = self.focus_get()
        keep_editing_targets = (self.rename_entry, self.rename_ok_btn, self.rename_cancel_btn)
        if focused in keep_editing_targets:
            return

        if self.rename_entry_var.get().strip():
            self._commit_inline_rename()
        else:
            self._cancel_inline_rename()

    def _ensure_rename_popup(self) -> None:
        if self.rename_popup and self.rename_popup.winfo_exists():
            return

        self.rename_popup = tk.Toplevel(self)
        self.rename_popup.withdraw()
        self.rename_popup.overrideredirect(True)
        self.rename_popup.attributes("-topmost", True)

        popup_wrap = tk.Frame(self.rename_popup, bg="#fff7dd", bd=1, relief="solid")
        popup_wrap.pack(fill="both", expand=True)

        self.rename_entry = tk.Entry(popup_wrap, textvariable=self.rename_entry_var, relief="flat")
        self.rename_entry.pack(side="left", fill="x", expand=True, padx=(4, 0), pady=2)

        self.rename_ok_btn = tk.Button(
            popup_wrap,
            text="✓",
            width=2,
            command=self._commit_inline_rename,
            relief="flat",
            bg="#fff7dd",
            activebackground="#ffefbb",
            takefocus=0,
            cursor="hand2",
        )
        self.rename_ok_btn.pack(side="left", padx=(2, 1), pady=1)

        self.rename_cancel_btn = tk.Button(
            popup_wrap,
            text="✕",
            width=2,
            command=self._cancel_inline_rename,
            relief="flat",
            bg="#fff7dd",
            activebackground="#ffefbb",
            takefocus=0,
            cursor="hand2",
        )
        self.rename_cancel_btn.pack(side="left", padx=(1, 3), pady=1)

        self.rename_entry.bind("<Return>", self._commit_inline_rename)
        self.rename_entry.bind("<Escape>", self._cancel_inline_rename)
        self.rename_entry.bind("<FocusOut>", self._on_rename_entry_focus_out)

    def _hide_selected_note(self) -> None:
        note_id = self._selected_note_id()
        if note_id:
            self.app.hide_note_window(note_id)

    def _delete_selected_note(self) -> None:
        note_id = self._selected_note_id()
        if note_id:
            self.app.delete_note(note_id)

    def destroy(self) -> None:
        if self.rename_popup and self.rename_popup.winfo_exists():
            self.rename_popup.destroy()
        if self.list_context_menu:
            self.list_context_menu.destroy()
        super().destroy()

class HelpNoteWindow(tk.Toplevel):
    def __init__(self, app: StickyNotesApp) -> None:
        super().__init__(app.root)
        self.app = app

        self.title("사용안내")
        self.geometry("460x620+240+120")
        self.minsize(340, 360)
        self.configure(bg="#fff7cf")
        self.attributes("-topmost", True)
        _apply_window_icon(self)

        header = tk.Frame(self, bg="#f4d55f", padx=12, pady=9)
        header.pack(fill="x")

        tk.Label(
            header,
            text="사용안내",
            bg="#f4d55f",
            fg="#5a4c22",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x")

        body = tk.Frame(self, bg="#fff7cf", padx=10, pady=10)
        body.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(body, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.text = tk.Text(
            body,
            wrap="word",
            bg="#fff7cf",
            fg="#4f452b",
            relief="flat",
            padx=14,
            pady=14,
            font=("Segoe UI", 10),
            spacing1=3,
            spacing2=3,
            spacing3=6,
            insertbackground="#4f452b",
            highlightthickness=0,
            yscrollcommand=scrollbar.set,
        )
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text.yview)

        self.text.insert("1.0", HELP_NOTE_CONTENT)
        self._apply_link_tags()
        self.text.configure(state="disabled")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_link_tags(self) -> None:
        urls = [
            "https://play.google.com/store/apps/details?id=com.milemilesmile.work_camera_v2",
            "https://play.google.com/store/apps/details?id=com.milemilesmile.myapplication",
            "https://play.google.com/store/apps/details?id=com.axlose.meow_woof_slide",
        ]

        self.text.tag_configure("help_link", foreground="#1a5fb4", underline=True)
        self.text.tag_bind("help_link", "<Enter>", lambda _event: self.text.configure(cursor="hand2"))
        self.text.tag_bind("help_link", "<Leave>", lambda _event: self.text.configure(cursor="xterm"))
        self.text.tag_bind("help_link", "<Button-1>", self._open_link)

        for url in urls:
            start = "1.0"
            while True:
                match_start = self.text.search(url, start, stopindex="end")
                if not match_start:
                    break
                match_end = f"{match_start}+{len(url)}c"
                self.text.tag_add("help_link", match_start, match_end)
                start = match_end

    def _open_link(self, _event=None) -> None:
        for tag_name in self.text.tag_names("current"):
            ranges = self.text.tag_ranges(tag_name)
            if tag_name != "help_link" or not ranges:
                continue

        index = self.text.index("current")
        line_start = self.text.index(f"{index} linestart")
        line_end = self.text.index(f"{index} lineend")
        url = self.text.get(line_start, line_end).strip()
        if url.startswith("https://"):
            webbrowser.open(url)

    def _on_close(self) -> None:
        self.app.help_window = None
        self.destroy()

    def destroy(self) -> None:
        self.app.help_window = None
        super().destroy()


class GlobalSettingsDialog(tk.Toplevel):
    def __init__(self, app: StickyNotesApp) -> None:
        super().__init__(app.root)
        self.app = app

        self.title("Global Settings")
        self.geometry("360x260")
        self.resizable(False, False)
        self.attributes("-topmost", self.app.always_on_top)
        _apply_window_icon(self)

        wrap = tk.Frame(self, padx=12, pady=12)
        wrap.pack(fill="both", expand=True)

        tk.Label(wrap, text="전역 설정", anchor="w", font=("Segoe UI", 10, "bold")).pack(fill="x")

        self.auto_start_var = tk.BooleanVar(value=self.app.auto_start_enabled)
        tk.Checkbutton(
            wrap,
            text="윈도우 실행 시 자동 실행",
            variable=self.auto_start_var,
            anchor="w",
            command=self._on_toggle_auto_start,
        ).pack(fill="x", pady=(10, 0))

        self.autostart_force_show_var = tk.BooleanVar(value=self.app.autostart_force_show_if_all_hidden)
        tk.Checkbutton(
            wrap,
            text="자동시작 시 숨김 상태면 메모 1개 표시",
            variable=self.autostart_force_show_var,
            anchor="w",
            command=self._on_toggle_autostart_force_show,
        ).pack(fill="x", pady=(6, 0))

        self.always_on_top_var = tk.BooleanVar(value=self.app.always_on_top)
        tk.Checkbutton(
            wrap,
            text="노트를 항상 위에 표시",
            variable=self.always_on_top_var,
            anchor="w",
            command=self._on_toggle_always_on_top,
        ).pack(fill="x", pady=(6, 0))

        backup_row = tk.Frame(wrap)
        backup_row.pack(fill="x", pady=(14, 0))
        tk.Button(backup_row, text="백업 내보내기", command=self.app.export_backup_file, width=14).pack(side="left")
        tk.Button(backup_row, text="백업 불러오기", command=self.app.import_backup_file, width=14).pack(side="left", padx=8)

        tk.Button(wrap, text="Close", command=self.app.hide_global_settings).pack(anchor="e", pady=(16, 0))

        self.protocol("WM_DELETE_WINDOW", self.app.hide_global_settings)
        self.refresh()

    def refresh(self) -> None:
        self.auto_start_var.set(self.app.auto_start_enabled)
        self.autostart_force_show_var.set(self.app.autostart_force_show_if_all_hidden)
        self.always_on_top_var.set(self.app.always_on_top)

    def _on_toggle_auto_start(self) -> None:
        self.app.set_auto_start_enabled(self.auto_start_var.get())

    def _on_toggle_autostart_force_show(self) -> None:
        self.app.autostart_force_show_if_all_hidden = bool(self.autostart_force_show_var.get())
        self.app._queue_save()

    def _on_toggle_always_on_top(self) -> None:
        self.app.set_always_on_top(self.always_on_top_var.get())

    def destroy(self) -> None:
        self.app.global_settings_dialog = None
        super().destroy()


class NoteSettingsDialog(tk.Toplevel):
    def __init__(self, app: StickyNotesApp, note_id: str) -> None:
        super().__init__(app.root)
        self.app = app
        self.note_id = note_id

        self.title("Note Settings")
        self.geometry("340x260")
        self.resizable(False, False)
        self.attributes("-topmost", self.app.always_on_top)
        _apply_window_icon(self)

        wrap = tk.Frame(self, padx=12, pady=12)
        wrap.pack(fill="both", expand=True)

        self.title_label = tk.Label(wrap, anchor="w")
        self.title_label.pack(fill="x")

        tk.Label(wrap, text="Color", anchor="w", pady=6).pack(fill="x")
        palette = tk.Frame(wrap)
        palette.pack(fill="x")

        for color in DEFAULT_COLORS:
            tk.Button(
                palette,
                bg=color,
                width=3,
                relief="flat",
                command=lambda c=color: self.app.apply_note_color(self.note_id, c),
            ).pack(side="left", padx=3)

        font_row = tk.Frame(wrap)
        font_row.pack(fill="x", pady=(10, 0))
        tk.Label(font_row, text="글꼴 크기", anchor="w", width=10).pack(side="left")
        self.font_size_var = tk.IntVar(value=11)
        self.font_size_spin = tk.Spinbox(
            font_row,
            from_=8,
            to=24,
            width=6,
            textvariable=self.font_size_var,
            command=self._on_change_font_size,
        )
        self.font_size_spin.pack(side="left")
        self.font_size_spin.bind("<Return>", self._on_change_font_size)
        self.font_size_spin.bind("<FocusOut>", self._on_change_font_size)

        opacity_row = tk.Frame(wrap)
        opacity_row.pack(fill="x", pady=(10, 0))
        tk.Label(opacity_row, text="투명도", anchor="w", width=10).pack(side="left")
        self.opacity_var = tk.DoubleVar(value=100)
        self.opacity_scale = tk.Scale(
            opacity_row,
            from_=45,
            to=100,
            orient="horizontal",
            variable=self.opacity_var,
            showvalue=True,
            command=self._on_change_opacity,
        )
        self.opacity_scale.pack(side="left", fill="x", expand=True)

        tk.Button(wrap, text="Close", command=self.app.hide_settings_dialog).pack(anchor="e", pady=(12, 0))

        self.protocol("WM_DELETE_WINDOW", self.app.hide_settings_dialog)
        self.refresh()

    def refresh(self) -> None:
        note = self.app.notes.get(self.note_id)
        if not note:
            self.destroy()
            self.app.settings_dialog = None
            return
        self.title_label.config(text=f"Note: {note.get('title', '(Untitled)')}")
        self.font_size_var.set(int(note.get("font_size", 11) or 11))
        self.opacity_var.set(float(note.get("opacity", 1.0) or 1.0) * 100)

    def _on_change_font_size(self, _event=None) -> None:
        self.app.apply_note_appearance(self.note_id, font_size=self.font_size_var.get())

    def _on_change_opacity(self, _value=None) -> None:
        self.app.apply_note_appearance(self.note_id, opacity=float(self.opacity_var.get()) / 100.0)

    def destroy(self) -> None:
        self.app.settings_dialog = None
        super().destroy()


class DrawingEditorDialog(tk.Toplevel):
    def __init__(self, note_window: NoteWindow) -> None:
        super().__init__(note_window)
        self.note_window = note_window
        self.title("그림 그리기")
        self.geometry("700x520")
        self.minsize(560, 420)
        self.attributes("-topmost", self.note_window.app.always_on_top)
        _apply_window_icon(self)

        self.pen_color = "#2f2f2f"
        self.pen_width = tk.IntVar(value=3)
        self._last_x = None
        self._last_y = None

        toolbar = tk.Frame(self, padx=10, pady=8)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="색상").pack(side="left")
        for color in ("#2f2f2f", "#d64545", "#2f7ed8", "#2f9d50", "#6f42c1"):
            tk.Button(toolbar, bg=color, width=2, relief="flat", command=lambda c=color: self._set_color(c)).pack(side="left", padx=2)
        tk.Label(toolbar, text="두께", padx=8).pack(side="left")
        tk.Spinbox(toolbar, from_=1, to=20, width=4, textvariable=self.pen_width).pack(side="left")
        tk.Button(toolbar, text="지우개", command=self._use_eraser).pack(side="left", padx=(8, 0))
        tk.Button(toolbar, text="전체 지우기", command=self._clear_canvas).pack(side="left", padx=6)
        tk.Button(toolbar, text="노트에 삽입", command=self._save_and_insert).pack(side="right")

        self.canvas = tk.Canvas(self, bg="white", cursor="cross")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.protocol("WM_DELETE_WINDOW", self._close_dialog)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def _set_color(self, color: str) -> None:
        self.pen_color = color

    def _use_eraser(self) -> None:
        self.pen_color = "white"

    def _clear_canvas(self) -> None:
        self.canvas.delete("all")

    def _on_press(self, event=None) -> None:
        if event is None:
            return
        self._last_x = event.x
        self._last_y = event.y

    def _on_drag(self, event=None) -> None:
        if event is None or self._last_x is None or self._last_y is None:
            return
        width = max(1, int(self.pen_width.get() or 1))
        self.canvas.create_line(
            self._last_x,
            self._last_y,
            event.x,
            event.y,
            fill=self.pen_color,
            width=width,
            capstyle=tk.ROUND,
            smooth=True,
        )
        self._last_x = event.x
        self._last_y = event.y

    def _on_release(self, _event=None) -> None:
        self._last_x = None
        self._last_y = None

    def _save_and_insert(self) -> None:
        if not PILLOW_AVAILABLE:
            messagebox.showerror("그림 저장", "Pillow가 없어 그림 저장을 할 수 없습니다.", parent=self)
            return

        self.update_idletasks()
        x1 = self.canvas.winfo_rootx()
        y1 = self.canvas.winfo_rooty()
        x2 = x1 + self.canvas.winfo_width()
        y2 = y1 + self.canvas.winfo_height()

        try:
            capture = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            output = _resolve_media_dir() / f"drawing_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.png"
            capture.save(output, format="PNG")
            self.note_window.insert_image_reference(output)
            self._close_dialog()
        except Exception as exc:
            messagebox.showerror("그림 저장", f"그림을 저장하지 못했습니다.\n{exc}", parent=self)

    def _close_dialog(self) -> None:
        self.note_window._drawing_dialog = None
        self.destroy()


class TableEditorDialog(tk.Toplevel):
    def __init__(self, note_window: NoteWindow) -> None:
        super().__init__(note_window)
        self.note_window = note_window
        self.title("표 입력")
        self.geometry("620x470")
        self.minsize(520, 390)
        self.attributes("-topmost", self.note_window.app.always_on_top)
        _apply_window_icon(self)

        self.rows_var = tk.IntVar(value=3)
        self.cols_var = tk.IntVar(value=3)
        self.data: list[list[str]] = []
        self.merged_ranges: list[dict] = []
        self.entries: dict[tuple[int, int], tk.Entry] = {}
        self.sel_start = (0, 0)
        self.sel_end = (0, 0)
        self.selection_var = tk.StringVar(value="선택: A1")

        top = tk.Frame(self, padx=10, pady=8)
        top.pack(fill="x")
        tk.Label(top, text="행").pack(side="left")
        tk.Spinbox(top, from_=1, to=30, width=5, textvariable=self.rows_var).pack(side="left", padx=(4, 10))
        tk.Label(top, text="열").pack(side="left")
        tk.Spinbox(top, from_=1, to=20, width=5, textvariable=self.cols_var).pack(side="left", padx=(4, 10))
        tk.Button(top, text="표 생성", command=self._generate_blank_table).pack(side="left")
        tk.Label(top, textvariable=self.selection_var, fg="#2f5f9f").pack(side="right")

        ops = tk.Frame(self, padx=10, pady=0)
        ops.pack(fill="x", pady=(0, 8))
        tk.Button(ops, text="셀 추가", width=8, command=self._add_cell).pack(side="left", padx=1)
        tk.Button(ops, text="셀 삭제", width=8, command=self._delete_cell).pack(side="left", padx=1)
        tk.Button(ops, text="행 추가", width=8, command=self._add_row).pack(side="left", padx=1)
        tk.Button(ops, text="행 삭제", width=8, command=self._delete_row).pack(side="left", padx=1)
        tk.Button(ops, text="열 추가", width=8, command=self._add_col).pack(side="left", padx=1)
        tk.Button(ops, text="열 삭제", width=8, command=self._delete_col).pack(side="left", padx=1)
        tk.Button(ops, text="병합", width=8, command=self._merge_selected).pack(side="left", padx=8)
        tk.Button(ops, text="분할", width=8, command=self._split_selected).pack(side="left", padx=1)

        hint = tk.Label(
            self,
            text="셀 선택 후 병합/분할 또는 추가/삭제를 실행하세요. 범위 병합은 Shift+클릭으로 끝 셀 선택.",
            fg="#5b5447",
            anchor="w",
            padx=12,
        )
        hint.pack(fill="x")

        self.grid_canvas = tk.Canvas(self, highlightthickness=0)
        self.grid_canvas.pack(fill="both", expand=True, padx=10, pady=(4, 8))
        self.grid_frame = tk.Frame(self.grid_canvas)
        self.grid_window = self.grid_canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        y_scroll = tk.Scrollbar(self, orient="vertical", command=self.grid_canvas.yview)
        y_scroll.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
        self.grid_canvas.configure(yscrollcommand=y_scroll.set)

        self.grid_frame.bind("<Configure>", self._on_grid_configure)
        self.grid_canvas.bind("<Configure>", self._on_canvas_configure)

        bottom = tk.Frame(self, padx=10, pady=8)
        bottom.pack(fill="x")
        tk.Button(bottom, text="표 삽입", command=self._insert_table, width=10).pack(side="left")
        tk.Button(bottom, text="닫기", command=self._close_dialog, width=10).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close_dialog)
        self._generate_blank_table()

    def _col_name(self, index: int) -> str:
        name = ""
        index += 1
        while index:
            index, rem = divmod(index - 1, 26)
            name = chr(ord("A") + rem) + name
        return name

    def _cell_ref(self, row: int, col: int) -> str:
        return f"{self._col_name(col)}{row + 1}"

    def _selection_bounds(self) -> tuple[int, int, int, int]:
        r1, c1 = self.sel_start
        r2, c2 = self.sel_end
        return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)

    def _update_selection_label(self) -> None:
        r1, c1, r2, c2 = self._selection_bounds()
        if (r1, c1) == (r2, c2):
            self.selection_var.set(f"선택: {self._cell_ref(r1, c1)}")
        else:
            self.selection_var.set(f"선택: {self._cell_ref(r1, c1)}:{self._cell_ref(r2, c2)}")

    def _on_grid_configure(self, _event=None) -> None:
        self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all"))

    def _on_canvas_configure(self, event=None) -> None:
        if event is None:
            return
        self.grid_canvas.itemconfigure(self.grid_window, width=event.width)

    def _generate_blank_table(self) -> None:
        rows = max(1, min(30, int(self.rows_var.get() or 3)))
        cols = max(1, min(20, int(self.cols_var.get() or 3)))
        self.data = [["" for _ in range(cols)] for _ in range(rows)]
        self.merged_ranges = []
        self.sel_start = (0, 0)
        self.sel_end = (0, 0)
        self._render_grid()

    def _render_grid(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.entries = {}

        rows = len(self.data)
        cols = len(self.data[0]) if rows else 0

        for col in range(cols):
            label = tk.Label(self.grid_frame, text=self._col_name(col), font=("Segoe UI", 9, "bold"))
            label.grid(row=0, column=col + 1, sticky="nsew", padx=1, pady=1)

        for row in range(rows):
            row_label = tk.Label(self.grid_frame, text=str(row + 1), font=("Segoe UI", 9, "bold"))
            row_label.grid(row=row + 1, column=0, sticky="nsew", padx=1, pady=1)

            for col in range(cols):
                if self._is_hidden_by_merge(row, col):
                    continue
                merge = self._merge_at_top_left(row, col)
                rowspan = merge["rowspan"] if merge else 1
                colspan = merge["colspan"] if merge else 1

                entry = tk.Entry(self.grid_frame, width=12)
                entry.insert(0, self.data[row][col])
                entry.grid(
                    row=row + 1,
                    column=col + 1,
                    rowspan=rowspan,
                    columnspan=colspan,
                    sticky="nsew",
                    padx=1,
                    pady=1,
                    ipadx=2,
                    ipady=2,
                )
                entry.bind("<KeyRelease>", lambda _e, rr=row, cc=col: self._on_entry_change(rr, cc), add="+")
                entry.bind("<Button-1>", lambda event, rr=row, cc=col: self._on_cell_click(event, rr, cc), add="+")
                entry.bind("<FocusIn>", lambda _e, rr=row, cc=col: self._set_selection(rr, cc, extend=False), add="+")
                self.entries[(row, col)] = entry

        for col in range(cols):
            self.grid_frame.grid_columnconfigure(col + 1, weight=1)
        for row in range(rows):
            self.grid_frame.grid_rowconfigure(row + 1, weight=1)

        self._refresh_selection_highlight()
        self._update_selection_label()

    def _on_entry_change(self, row: int, col: int) -> None:
        if row < len(self.data) and col < len(self.data[row]) and (row, col) in self.entries:
            self.data[row][col] = self.entries[(row, col)].get().strip()

    def _on_cell_click(self, event, row: int, col: int) -> None:
        extend = bool(int(getattr(event, "state", 0) or 0) & 0x0001)
        self._set_selection(row, col, extend=extend)

    def _set_selection(self, row: int, col: int, extend: bool) -> None:
        row = max(0, min(row, len(self.data) - 1))
        col = max(0, min(col, len(self.data[0]) - 1))
        if extend:
            self.sel_end = (row, col)
        else:
            self.sel_start = (row, col)
            self.sel_end = (row, col)
        self._refresh_selection_highlight()
        self._update_selection_label()

    def _refresh_selection_highlight(self) -> None:
        r1, c1, r2, c2 = self._selection_bounds()
        for (row, col), entry in self.entries.items():
            if r1 <= row <= r2 and c1 <= col <= c2:
                entry.configure(bg="#fff2bf")
            else:
                entry.configure(bg="white")

    def _merge_at_top_left(self, row: int, col: int) -> dict | None:
        for merge in self.merged_ranges:
            if merge["r"] == row and merge["c"] == col:
                return merge
        return None

    def _range_covering_cell(self, row: int, col: int) -> dict | None:
        for merge in self.merged_ranges:
            if merge["r"] <= row < merge["r"] + merge["rowspan"] and merge["c"] <= col < merge["c"] + merge["colspan"]:
                return merge
        return None

    def _is_hidden_by_merge(self, row: int, col: int) -> bool:
        merge = self._range_covering_cell(row, col)
        if not merge:
            return False
        return not (merge["r"] == row and merge["c"] == col)

    def _add_col(self) -> None:
        _r1, c1, _r2, _c2 = self._selection_bounds()
        insert_col = c1 + 1
        for row in self.data:
            row.insert(insert_col, "")
        self.cols_var.set(len(self.data[0]))
        self.merged_ranges = []
        self._set_selection(0, min(insert_col, len(self.data[0]) - 1), extend=False)
        self._render_grid()

    def _delete_col(self) -> None:
        if not self.data or len(self.data[0]) <= 1:
            return
        _r1, c1, _r2, _c2 = self._selection_bounds()
        delete_col = c1
        for row in self.data:
            row.pop(delete_col)
        self.cols_var.set(len(self.data[0]))
        self.merged_ranges = []
        self._set_selection(0, max(0, min(delete_col, len(self.data[0]) - 1)), extend=False)
        self._render_grid()

    def _add_cell(self) -> None:
        if not self.data or not self.data[0]:
            return
        r1, c1, _r2, _c2 = self._selection_bounds()
        row = self.data[r1]
        insert_col = min(c1 + 1, len(row))
        row.insert(insert_col, "")
        if len(row) > self.cols_var.get():
            row.pop()
        self.merged_ranges = []
        self._set_selection(r1, min(insert_col, len(row) - 1), extend=False)
        self._render_grid()

    def _delete_cell(self) -> None:
        if not self.data or not self.data[0]:
            return
        r1, c1, _r2, _c2 = self._selection_bounds()
        row = self.data[r1]
        delete_col = min(c1, len(row) - 1)
        row.pop(delete_col)
        row.append("")
        self.merged_ranges = []
        self._set_selection(r1, min(delete_col, len(row) - 1), extend=False)
        self._render_grid()

    def _add_row(self) -> None:
        r1, _c1, _r2, _c2 = self._selection_bounds()
        insert_row = r1 + 1
        cols = len(self.data[0]) if self.data else 1
        self.data.insert(insert_row, ["" for _ in range(cols)])
        self.rows_var.set(len(self.data))
        self.merged_ranges = []
        self._set_selection(min(insert_row, len(self.data) - 1), 0, extend=False)
        self._render_grid()

    def _delete_row(self) -> None:
        if len(self.data) <= 1:
            return
        r1, _c1, _r2, _c2 = self._selection_bounds()
        delete_row = r1
        self.data.pop(delete_row)
        self.rows_var.set(len(self.data))
        self.merged_ranges = []
        self._set_selection(max(0, min(delete_row, len(self.data) - 1)), 0, extend=False)
        self._render_grid()

    def _merge_selected(self) -> None:
        r1, c1, r2, c2 = self._selection_bounds()
        if (r1, c1) == (r2, c2):
            messagebox.showinfo("셀 병합", "병합할 범위를 선택하세요. (Shift+클릭)", parent=self)
            return

        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                if self._range_covering_cell(rr, cc):
                    messagebox.showinfo("셀 병합", "이미 병합된 셀이 포함되어 있습니다. 먼저 분할하세요.", parent=self)
                    return

        texts = []
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                value = self.data[rr][cc].strip()
                if value:
                    texts.append(value)

        if texts:
            self.data[r1][c1] = " ".join(texts)
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                if (rr, cc) != (r1, c1):
                    self.data[rr][cc] = ""

        self.merged_ranges.append({"r": r1, "c": c1, "rowspan": (r2 - r1 + 1), "colspan": (c2 - c1 + 1)})
        self._set_selection(r1, c1, extend=False)
        self._render_grid()

    def _split_selected(self) -> None:
        r1, c1, _r2, _c2 = self._selection_bounds()
        merge = self._range_covering_cell(r1, c1)
        if not merge:
            messagebox.showinfo("셀 분할", "분할할 병합 셀을 선택하세요.", parent=self)
            return

        self.merged_ranges = [m for m in self.merged_ranges if m is not merge]
        self._set_selection(r1, c1, extend=False)
        self._render_grid()

    def _insert_table(self) -> None:
        rows = [[str(cell or "") for cell in row] for row in self.data]
        if not rows:
            return
        self.note_window.insert_table_rows(rows, merged_ranges=self.merged_ranges)
        self._close_dialog()

    def _close_dialog(self) -> None:
        self.note_window._table_dialog = None
        self.destroy()


def main() -> None:
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
    running = already_running(kernel32.GetLastError())
    if running:
        notify_existing_instance(kernel32, ACTIVATE_EVENT_NAME, EVENT_MODIFY_STATE)
        if mutex:
            kernel32.CloseHandle(mutex)
        return

    activation_event_handle = kernel32.CreateEventW(None, False, False, ACTIVATE_EVENT_NAME)

    try:
        root = tk.Tk()
        _apply_window_icon(root)
        launched_from_autostart = AUTOSTART_ARG in sys.argv
        app = StickyNotesApp(
            root,
            activation_event_handle=activation_event_handle,
            launched_from_autostart=launched_from_autostart,
        )
        root.mainloop()
    except Exception as exc:
        _write_crash_log(exc)
        try:
            messagebox.showerror(APP_BRAND_NAME, f"예기치 못한 오류가 발생했습니다.\n로그: {CRASH_LOG_FILE}")
        except tk.TclError:
            pass
    finally:
        if activation_event_handle:
            kernel32.CloseHandle(activation_event_handle)
        if mutex:
            kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
