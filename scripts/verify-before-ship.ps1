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
      3. instruction ratchet - scripts/instruction_ratchet.py: fails when a prompt-audit
                             lint rule's hit count in CLAUDE.md / AGENTS.md / skills
                             rises above the committed baseline, or a file passes its
                             size cap. Exit 3 = "not confirmed" (git unusable, an
                             unreadable file, an unclosed fence): a failure, never a pass.
      4. doc refs ratchet  - scripts/doc_refs_ratchet.py: fails when README.md, CLAUDE.md
                             or docs/**/*.md names a repo path, module or relative link
                             that does not exist, beyond the committed baseline. Exit 3 =
                             "not confirmed" (git unusable, a non-UTF-8 file, an unclosed
                             fence): a failure, never a pass.
      5. dead code ratchet - scripts/dead_code_ratchet.py: fails when a Python function,
                             class or method that nothing refers to is not in the
                             committed baseline. Exit 3 = "not confirmed" (git unusable,
                             a .py file that does not parse): a failure, never a pass.
      6. static ratchet    - scripts/static_ratchet.py: fails on a duplicated block, an
                             unused import or variable, or a likely-bug / security pattern
                             (jscpd + ruff) not in the committed baseline. Needs Node (npx)
                             and ruff in the venv. Exit 3 = "not confirmed" (no npx, ruff
                             missing, a detector that could not run): a failure, never a pass.
      7. docs ratchet      - scripts/docs_ratchet.py: fails when README.md grows past its size
                             budget, or README.md / docs/**/*.md gains an issue reference, a
                             dated heading or a changelog heading, beyond the committed
                             baseline. Exit 3 = "not confirmed" (git unusable, a non-UTF-8
                             file, an unclosed fence): a failure, never a pass.
      8. comment ratchet   - scripts/comment_ratchet.py: fails when a source file's count of
                             `#NNN` issue references in comments rises above the committed
                             baseline. Exit 3 = "not confirmed" (git unusable, a file that
                             cannot be scanned): a failure, never a pass.
      9. pytest            - the unit suite

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
Invoke-Stage "instruction ratchet" { & $py "scripts/instruction_ratchet.py" }
Invoke-Stage "doc refs ratchet" { & $py "scripts/doc_refs_ratchet.py" }
Invoke-Stage "dead code ratchet" { & $py "scripts/dead_code_ratchet.py" }
Invoke-Stage "static ratchet" { & $py "scripts/static_ratchet.py" }
Invoke-Stage "docs ratchet" { & $py "scripts/docs_ratchet.py" }
Invoke-Stage "comment ratchet" { & $py "scripts/comment_ratchet.py" }
Invoke-Stage "pytest"            { & $py -m pytest }

Write-Host ""
Write-Host "GATE-RESULT: PASS" -ForegroundColor Green
Write-Host "[PASS] all checks green - safe to ship." -ForegroundColor Green
