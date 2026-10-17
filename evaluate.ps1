$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv\Scripts\python.exe' main.py models start
if ($LASTEXITCODE -ne 0) { throw 'Local model startup failed.' }
& '.\.venv\Scripts\python.exe' main.py verify
if ($LASTEXITCODE -ne 0) { throw 'Verification failed.' }
& '.\.venv\Scripts\python.exe' main.py evaluate all
if ($LASTEXITCODE -ne 0) { throw 'Evaluation failed.' }
& '.\.venv\Scripts\python.exe' main.py archive
if ($LASTEXITCODE -ne 0) { throw 'Submission packaging failed.' }
