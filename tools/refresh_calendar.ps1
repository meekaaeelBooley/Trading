<#
 Refresh the MT5 USD economic calendar export (data\usd_events.csv) used by research and as a live fallback.
 The Python MT5 package has no calendar API, so the terminal itself runs tools\mql5\ExportUsdCalendar.mq5.
 That needs one terminal start with a startup config, so this script:
   1. refuses to run while any position or order is open (never restart the terminal mid-trade),
   2. closes the terminal gracefully, relaunches it with /config running the export script, waits for the CSV,
   3. runs `tools\usdcal.py sync`.
 Usage:  powershell -File tools\refresh_calendar.ps1 [-Force]   (-Force: skip the open-position check; never use mid-trade)
 Alternative without any restart: in MT5 Navigator > Services start `UsdCalendarService` once (it re-exports every 3 h).
#>
param([switch]$Force)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$term = "C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
$py = Join-Path $root ".venv\Scripts\python.exe"
$csv = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files\usd_calendar.csv"
$ini = Join-Path $env:TEMP "startup_usd_calendar.ini"

$scripts = Join-Path $env:APPDATA "MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\MQL5\Scripts"
if (-not (Test-Path (Join-Path $scripts "ExportUsdCalendar.ex5"))) {
    Copy-Item (Join-Path $root "tools\mql5\ExportUsdCalendar.mq5") $scripts -Force
    & "C:\Program Files\MetaTrader 5 EXNESS\MetaEditor64.exe" /compile:"$scripts\ExportUsdCalendar.mq5" | Out-Null
    Start-Sleep 3
}

if (-not $Force) {
    $chk = & $py -I -c "import MetaTrader5 as m,sys; m.initialize(path=r'$term'); print(m.positions_total()+m.orders_total()); m.shutdown()"
    if ([int]$chk -ne 0) { Write-Error "positions/orders open ($chk): not restarting the terminal"; exit 2 }
}
$before = if (Test-Path $csv) { (Get-Item $csv).LastWriteTime } else { [datetime]::MinValue }
Set-Content -Path $ini -Value "[StartUp]`nScript=ExportUsdCalendar`nSymbol=XAUUSDm`nPeriod=M5" -Encoding ASCII
$p = Get-Process terminal64 -ErrorAction SilentlyContinue
if ($p) { [void]$p.CloseMainWindow(); if (-not $p.WaitForExit(45000)) { Write-Error "terminal did not close"; exit 3 }; Start-Sleep 3 }
Start-Process -FilePath $term -ArgumentList "/config:$ini"
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep 2
    if ((Test-Path $csv) -and ((Get-Item $csv).LastWriteTime -gt $before)) { break }
}
if (-not ((Test-Path $csv) -and ((Get-Item $csv).LastWriteTime -gt $before))) { Write-Error "export did not appear within 2 min"; exit 4 }
& $py (Join-Path $root "tools\usdcal.py") sync
