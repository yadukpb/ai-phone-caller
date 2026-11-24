"""Dependency-free structural smoke check for the project."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "app/main.py",
    "app/config.py",
    "app/schemas.py",
    "app/store.py",
    "app/telephony.py",
    "worker.py",
    "tts_server.py",
]

for relative in REQUIRED:
    path = ROOT / relative
    assert path.is_file(), f"missing {relative}"
    ast.parse(path.read_text(), filename=str(path))

print(f"ok: parsed {len(REQUIRED)} source files")
