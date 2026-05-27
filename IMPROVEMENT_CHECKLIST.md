# Sticky Notes Improvement Checklist

## 1) Stability (Priority 1)

- [x] Global crash log at AppData
- [x] Tray menu entry to open latest crash log
- [x] Autostart behavior option when visible note count is 0
- [x] Autostart fallback option: force one visible note
- [x] Startup junk cleanup expansion (pattern + signature)

## 2) UX (Priority 2)

- [x] New global settings window (autostart, startup behavior, always-on-top, backup)
- [x] Keep note settings as note-only (color, font, opacity)
- [x] Quick search/filter (title + body)

## 3) Maintenance (Priority 3)

- [x] Split modules: persistence.py
- [x] Split modules: autostart.py
- [x] Split modules: tray.py
- [x] Split modules: windows/*.py
- [x] Add minimum tests: save/restore
- [x] Add minimum tests: autostart toggle
- [x] Add minimum tests: single-instance activation

## 4) Product Gaps (Feature Backlog)

- [ ] Checklist mode (todo check)
- [ ] Date/reminder
- [ ] Backup/restore import-export
- [ ] Text formatting (bold/link preview)

## 5) Nice-to-Have Differentiators

- [ ] Global hotkeys (new note, open last note)
- [ ] Tags / pin / priority
- [ ] Note templates (meeting/todo/phone)
- [ ] Taskbar jump list (recent notes)
- [ ] Optional sync (default local-only)

## Done in this iteration

- [x] Priority 1 fully implemented
- [x] Guide text updated
- [x] Startup launcher cleanup hardened
- [x] Table input dialog added (insert as markdown table)
- [x] Table formulas added (`=A1+B1`, `=SUM(A1:B3)`)
- [x] Image insert feature added
- [x] Drawing canvas feature added
- [x] Old build artifacts cleanup
