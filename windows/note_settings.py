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


class NoteSettingsDialog(tk.Toplevel):
    def __init__(self, app: Any, note_id: str, icon_path: Path, palette_colors: list[str]) -> None:
        super().__init__(app.root)
        self.app = app
        self.note_id = note_id
        self._icon_path = icon_path
        self._palette_colors = palette_colors

        self.title("Note Settings")
        self.geometry("340x260")
        self.resizable(False, False)
        self.attributes("-topmost", self.app.always_on_top)
        _apply_window_icon(self, self._icon_path)

        wrap = tk.Frame(self, padx=12, pady=12)
        wrap.pack(fill="both", expand=True)

        self.title_label = tk.Label(wrap, anchor="w")
        self.title_label.pack(fill="x")

        tk.Label(wrap, text="Color", anchor="w", pady=6).pack(fill="x")
        palette = tk.Frame(wrap)
        palette.pack(fill="x")

        for color in self._palette_colors:
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
