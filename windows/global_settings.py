import tkinter as tk
from pathlib import Path
from typing import Any


def _apply_window_icon(window: tk.Misc, icon_path: Path) -> None:
    if not icon_path.exists():
        return
    try:
        window.iconbitmap(default=str(icon_path))
    except (tk.TclError, OSError):
        return


class GlobalSettingsDialog(tk.Toplevel):
    def __init__(self, app: Any, icon_path: Path) -> None:
        super().__init__(app.root)
        self.app = app
        self._icon_path = icon_path

        self.title("Global Settings")
        self.geometry("360x260")
        self.resizable(False, False)
        self.attributes("-topmost", self.app.always_on_top)
        _apply_window_icon(self, self._icon_path)

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
