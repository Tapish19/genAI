$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python scripts/bootstrap.py
    if ($LASTEXITCODE -ne 0) { throw 'Project setup failed.' }
}
& '.\.venv\Scripts\python.exe' main.py models start
if ($LASTEXITCODE -ne 0) { throw 'Local model startup failed.' }
& '.\.venv\Scripts\python.exe' main.py ingest corpus
if ($LASTEXITCODE -ne 0) { throw 'Corpus ingestion failed.' }
& '.\.venv\Scripts\python.exe' main.py serve --port 8080
