@echo off
cd /d "%~dp0"
py -3 sticky_notes.py
if errorlevel 1 (
    python sticky_notes.py
)
