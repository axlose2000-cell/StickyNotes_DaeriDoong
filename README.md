# StickyNotes_DaeriDoong

Windows desktop sticky notes app built with Python tkinter. Public release by DaeriDoong.

## Latest build

- EXE: dist/StickyNotes_DaeriDoong.exe
- Desktop shortcut script: create_shortcut.bat

## Key features

- Multi-window sticky notes with auto-save
- Restore title/text/size/position/color/collapsed state
- Single-instance activation (second launch focuses running app)
- System tray icon with open/new/quit and latest crash-log access
- Windows autostart toggle in app settings
- Autostart startup behavior option when all notes were hidden
- Global settings window: autostart, startup behavior, always-on-top, backup
- Note settings window: color, font size, opacity (note-only settings)
- Quick search/filter in note manager (title + body)
- Smoother Korean IME typing with reduced input jitter
- Keeps Korean input mode during typing unless user intentionally switches
- Table input dialog in notes
- Table cell operations: add/delete/merge/split before insertion
- Image insert button (copy image into app media folder and insert reference)
- Drawing canvas button (sketch and insert as PNG)
- Inserted images/tables are rendered visually inside notes (not plain markdown text)
- Right-bottom resize grip for easier window resizing
- Top menu bar with file actions (save/new/backup/import/close/exit)
- Inserted tables remain editable inside notes and persist after edits
- Table editor supports range selection (Shift+click) for merge and split operations
- Merged table layout now persists after insertion and after editing inside notes

## Run

1. Install Python 3 if needed
2. Run create_shortcut.bat or start dist/StickyNotes_DaeriDoong.exe directly

## Analysis & tests

- Static analyze: no current diagnostics
- Minimum tests: `py -3 -m unittest discover -s tests -p "test_*.py" -v`

## Code structure

- Core app: sticky_notes.py
- Persistence: persistence.py
- Autostart: autostart.py
- Tray image: tray.py
- Single-instance helpers: instance_control.py
- Window modules: windows/global_settings.py, windows/note_settings.py

## Data location

- %APPDATA%/Sticky Notes/notes_data.json
- Crash log: %APPDATA%/Sticky Notes/last_crash.log

## Improvement checklist

- See IMPROVEMENT_CHECKLIST.md for ordered progress and backlog.
