# Headless, no-LLM trading loop that starts a fresh run after each one ends.
# Stops when state\KILL or state\HALT exists. Ctrl+C to stop (open positions keep broker-side SL/TP, unmanaged).
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
while ($true) {
    if ((Test-Path "state\KILL") -or (Test-Path "state\HALT")) { Write-Host "KILL/HALT present: stopping"; break }
    & .venv\Scripts\python.exe tools\runner.py @args
    Start-Sleep -Seconds 200   # > 180s just_ended guard in engine/run.py
}
