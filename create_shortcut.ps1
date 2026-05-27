param(
    [Parameter(Mandatory = $false)]
    [string]$Target = ""
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Target)) {
    $Target = Join-Path $scriptDir "dist\StickyNotes_DaeriDoong.exe"
}

if (-not (Test-Path $Target)) {
    Write-Error "Target executable not found: $Target"
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "StickyNotes_DaeriDoong.lnk"

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $Target
$shortcut.WorkingDirectory = Split-Path -Parent $Target
$customIcon = Join-Path $scriptDir "sticky_note.ico"
if (Test-Path $customIcon) {
    $shortcut.IconLocation = "$customIcon,0"
} else {
    $shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,44"
}
$shortcut.Description = "StickyNotes_DaeriDoong"
$shortcut.Save()

Write-Host "Shortcut created: $shortcutPath"
