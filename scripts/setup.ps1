# One-time setup on Windows PowerShell: a virtualenv, the dependencies, and both
# corpora rebuilt from arXiv (about 25 minutes, because arXiv asks for 3 seconds
# between downloads). Safe to rerun: downloads are cached.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# The py launcher avoids the Microsoft Store "python" alias that many Windows machines have.
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { $null }
if (-not $py) { throw "Python 3.11 or newer is required: https://www.python.org/downloads/" }
& $py -c "import sys; sys.exit(sys.version_info < (3, 11))"
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is required." }

if (-not (Test-Path .venv)) { & $py -m venv .venv }
$vpy = ".venv\Scripts\python.exe"
& $vpy -m pip install --quiet --upgrade pip
& $vpy -m pip install --quiet -r requirements.txt

Write-Host "Building the main corpus (138 papers)..."
& $vpy build\extract_text.py
Write-Host "Building the hard-track corpus (95 papers)..."
& $vpy build\extract_text.py --track hard

if (Get-Command ollama -ErrorAction SilentlyContinue) {
  Write-Host "Ollama found. For judged metrics, run: ollama pull qwen3.5:9b"
} else {
  Write-Host "Ollama not found. Scoring still works with --judge none; install Ollama for judged metrics."
}
Write-Host ""
Write-Host "Done. Start the console with:  $vpy app\server.py --open"
