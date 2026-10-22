# Headless 5-minute experiment on the demo account: USTECm and XAUUSDm, each in its own window with its own
# config, journal and state (state-exp-ustec / state-exp-xau). No LLM in the loop. Emergency stop: create
# state-exp-ustec\KILL and state-exp-xau\KILL (flattens and stops). Do NOT run alongside `/loop /session` on USTECm.
param([switch]$DryRun)
$root = Split-Path -Parent $PSScriptRoot
foreach ($i in @(@{cfg="config.exp-ustec.json"; st="state-exp-ustec"}, @{cfg="config.exp-xau.json"; st="state-exp-xau"})) {
    $extra = if ($DryRun) { "--dry-run" } else { "" }
    $cmd = "`$env:TRADING_CONFIG='$($i.cfg)'; `$env:TRADING_STATE='$($i.st)'; Set-Location '$root'; " +
           "while (`$true) { if ((Test-Path '$($i.st)\KILL') -or (Test-Path '$($i.st)\HALT')) { break }; " +
           ".venv\Scripts\python.exe tools\runner.py $extra; Start-Sleep -Seconds 200 }"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
}
