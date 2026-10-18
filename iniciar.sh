#!/usr/bin/env bash
set -euo pipefail
if [ "$(uname -s)" != "Linux" ]; then
    echo "Voz Clara Linux necesita Linux con PipeWire o PulseAudio." >&2
    exit 1
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import PySide6, numpy, scipy' >/dev/null 2>&1; then
    .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python main.py
