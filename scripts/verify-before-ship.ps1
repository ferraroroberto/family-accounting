#Requires -Version 5.1
<#
.SYNOPSIS
    Pre-ship verification gate for family-accounting. One pass/fail pipeline.

.DESCRIPTION
    Runs, fail-fast:
      1. byte-compile      - every .py under app/ src/ scripts/ tests/ parses
      2. structure ratchet - scripts/structure_ratchet.py: fails when a file passes
                             1,000 lines, a function 100 lines, a directory 40 modules
                             or src/ imports app/, beyond the committed baseline, or
                             when a root folder falls outside the declared shape.
                             Exit 3 = "not confirmed" (git unusable, unparseable file,
                             unknown shape): a failure, never a pass.
      3. pytest            - the unit suite

    Anchors to the repo root, so run it from anywhere:
      powershell -File scripts/verify-before-ship.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[FAIL] .venv not found at $py" -ForegroundColor Red
    Write-Host "       Create it and run: $py -m pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

function Invoke-Stage {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ""
    Write-Host ">> $Name" -ForegroundColor Cyan
    & $Body
    # Any non-zero exit fails the gate, including the ratchet's exit 3 ("not confirmed").
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] $Name (exit $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
    Write-Host "[PASS] $Name" -ForegroundColor Green
}

Invoke-Stage "byte-compile"      { & $py -m compileall -q app src scripts tests }
Invoke-Stage "structure ratchet" { & $py "scripts/structure_ratchet.py" }
Invoke-Stage "pytest"            { & $py -m pytest }

Write-Host ""
Write-Host "GATE-RESULT: PASS" -ForegroundColor Green
Write-Host "[PASS] all checks green - safe to ship." -ForegroundColor Green
