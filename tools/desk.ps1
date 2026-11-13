# Desk controls (user-run; Claude never touches KILL/HALT files).
#   tools\desk.ps1 stop     create KILL for both instruments: every live shift flattens and stops within seconds (also clears UNCAPPED)
#   tools\desk.ps1 resume   remove the KILL files so the next /desk can trade (HALT = weekly drawdown stop stays; delete it yourself)
#   tools\desk.ps1 uncap    remove the run time cap (UNCAPPED flag, used by /desk-max); `cap` restores the run_max_minutes cap (used by /desk)
#   tools\desk.ps1 tier <moderate|high|extreme>   playbook risk tier (root TIER flag; default moderate). Takes effect on the next tick.
#   tools\desk.ps1 status   KILL/HALT/UNCAPPED/TIER flags and per-instrument results
param([Parameter(Mandatory = $true, Position = 0)][ValidateSet("stop", "resume", "uncap", "cap", "tier", "status")][string]$Action,
      [Parameter(Position = 1)][ValidateSet("moderate", "high", "extreme")][string]$Name)
$root = Split-Path -Parent $PSScriptRoot
$flag = Join-Path $root "UNCAPPED"
$tierFile = Join-Path $root "TIER"
switch ($Action) {
    "uncap"  { Set-Content $flag "uncapped by user $(Get-Date -Format s)"; Write-Host "UNCAPPED set: runs have no time cap" }
    "cap"    { Remove-Item $flag -ErrorAction SilentlyContinue; Write-Host "UNCAPPED cleared: runs capped at run_max_minutes" }
    "stop"   { Remove-Item $flag -ErrorAction SilentlyContinue }
    "tier"   {
        if (-not $Name) { Write-Host "usage: desk.ps1 tier moderate|high|extreme"; exit 1 }
        Set-Content $tierFile $Name; Write-Host "TIER=$Name"
    }
    "status" {
        "UNCAPPED={0}" -f (Test-Path $flag)
        "TIER={0}" -f $(if (Test-Path $tierFile) { (Get-Content $tierFile -TotalCount 1).Trim() } else { "moderate (default)" })
    }
}
$dirs = "state-xau", "state-ustec"
foreach ($d in $dirs) {
    $p = Join-Path $root $d
    switch ($Action) {
        "stop"   { New-Item -ItemType Directory -Force $p | Out-Null; Set-Content (Join-Path $p "KILL") "stopped by user $(Get-Date -Format s)"; Write-Host "KILL set: $d" }
        "resume" { Remove-Item (Join-Path $p "KILL") -ErrorAction SilentlyContinue; Write-Host "KILL cleared: $d" }
        "status" { "{0}: KILL={1} HALT={2}" -f $d, (Test-Path (Join-Path $p "KILL")), (Test-Path (Join-Path $p "HALT")) }
    }
}
if ($Action -eq "status") { & (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $root "tools\summary.py") }
