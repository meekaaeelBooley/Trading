# One-time setup on a new machine (Exness, XM or any MT5 broker). Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File tools\setup.ps1
# Options:  -Symbol US100Cash  -Terminal "C:\Path\to\terminal64.exe"   -Force (overwrite an existing .mcp.json)
# It creates the Python environment, finds your MetaTrader 5 terminal, lets you pick the broker's Nasdaq symbol, writes the
# per-machine .mcp.json (never committed) and runs tools\check_broker.py. It never places an order and never touches config files.
param([string]$Symbol, [string]$Terminal, [switch]$Force)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

function Step($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }

# ---- 1. Python environment
Step "1/4 Python environment"
if (-not (Test-Path $venvPy)) {
    $py = $null
    foreach ($cand in @(@("py", "-3"), @("python"))) {
        if (Get-Command $cand[0] -ErrorAction SilentlyContinue) {
            $v = & $cand[0] @($cand[1..($cand.Length - 1)] + @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")) 2>$null
            if ($v -and [version]$v -ge [version]"3.10") { $py = $cand; break }
        }
    }
    if (-not $py) { Write-Host "Python 3.10+ not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then rerun." -ForegroundColor Red; exit 1 }
    Write-Host "Creating .venv ..."
    & $py[0] @($py[1..($py.Length - 1)] + @("-m", "venv", ".venv"))
}
Write-Host "Installing packages (first run takes a minute) ..."
& $venvPy -m pip install --quiet --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed (the MetaTrader5 package needs 64-bit Windows Python 3.10-3.13)." -ForegroundColor Red; exit 1 }
Write-Host "OK"

# ---- 2. MetaTrader 5 terminal
Step "2/4 MetaTrader 5 terminal"
$found = @()
if ($Terminal) { $found = @($Terminal) }
else {
    $found += Get-Process terminal64 -ErrorAction SilentlyContinue | ForEach-Object { $_.Path } | Where-Object { $_ }
    foreach ($pf in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs")) {
        if ($pf -and (Test-Path $pf)) {
            $found += Get-ChildItem $pf -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "MetaTrader|MT5|Exness|XM|Terminal" } |
                ForEach-Object { Join-Path $_.FullName "terminal64.exe" } | Where-Object { Test-Path $_ }
        }
    }
    $found = @($found | Select-Object -Unique)
}
$mt5Path = ""
if ($found.Count -eq 1) { $mt5Path = $found[0]; Write-Host "Found: $mt5Path" }
elseif ($found.Count -gt 1) {
    for ($i = 0; $i -lt $found.Count; $i++) { Write-Host ("  [{0}] {1}" -f ($i + 1), $found[$i]) }
    $n = Read-Host "Which terminal is logged in to your DEMO account? (number)"
    $mt5Path = $found[[int]$n - 1]
}
else {
    Write-Host "No MetaTrader 5 terminal found. Install it from your broker (Exness / XM), log in to a DEMO account, start it, and rerun this script." -ForegroundColor Yellow
    Write-Host "Continuing with auto-detection (MT5_PATH left empty)."
}

# ---- 3. Nasdaq symbol
Step "3/4 Nasdaq symbol on your broker"
$env:MT5_PATH = $mt5Path
$cands = @()
$out = & $venvPy tools\check_broker.py --list 2>$null
if ($LASTEXITCODE -eq 0 -and $out) { $cands = @($out | Where-Object { $_ }) }
if (-not $Symbol) {
    if ($cands.Count -gt 0) {
        $cands = @($cands | Sort-Object @{Expression = { if ($_ -match '^(USTEC|US100|NAS100)') { 0 } else { 1 } } }, @{Expression = { $_.Length } })
        Write-Host "Nasdaq-like symbols found on your broker (cleanest name first):"
        for ($i = 0; $i -lt $cands.Count; $i++) { Write-Host ("  [{0}] {1}" -f ($i + 1), $cands[$i]) }
        $ans = Read-Host "Pick a number, or type a symbol name (Enter = 1)"
        if (-not $ans) { $ans = "1" }
        $Symbol = if ($ans -match '^\d+$') { $cands[[int]$ans - 1] } else { $ans }
    }
    else {
        Write-Host "Could not list symbols (terminal not running/logged in?). Typical names: USTECm / USTEC (Exness), US100Cash (XM)."
        $Symbol = Read-Host "Type your broker's Nasdaq symbol (see Market Watch)"
    }
}
if (-not $Symbol) { Write-Host "No symbol given." -ForegroundColor Red; exit 1 }
Write-Host "Symbol: $Symbol"

# ---- 4. per-machine MCP config
Step "4/4 Writing .mcp.json (this machine only, not committed)"
$mcpFile = Join-Path $root ".mcp.json"
if ((Test-Path $mcpFile) -and -not $Force) {
    Write-Host ".mcp.json already exists: left untouched. Rerun with -Force to replace it (the old file is saved as .mcp.json.bak)." -ForegroundColor Yellow
}
else {
    if (Test-Path $mcpFile) { Copy-Item $mcpFile "$mcpFile.bak" -Force }
    $envBlock = [ordered]@{ TRADING_CONFIG = "config.ustec.json"; TRADING_STATE = "state-ustec"; TRADING_SYMBOL = $Symbol }
    if ($mt5Path) { $envBlock["MT5_PATH"] = $mt5Path }
    $cfg = [ordered]@{ mcpServers = [ordered]@{ ustec = [ordered]@{
                type = "stdio"; command = $venvPy; args = @((Join-Path $root "mt5_server.py")); env = $envBlock } } }
    [IO.File]::WriteAllText($mcpFile, ($cfg | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
    Write-Host "Wrote $mcpFile"
}
$local = Join-Path $root ".claude\settings.local.json"
if (-not (Test-Path $local)) {
    New-Item -ItemType Directory -Force (Split-Path $local) | Out-Null
    [IO.File]::WriteAllText($local, '{"enabledMcpjsonServers": ["ustec"]}', (New-Object Text.UTF8Encoding($false)))
}

Step "Checking your broker"
& $venvPy tools\check_broker.py
exit $LASTEXITCODE
