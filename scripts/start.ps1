$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
& .\.venv\Scripts\dagforge.exe serve --reload

