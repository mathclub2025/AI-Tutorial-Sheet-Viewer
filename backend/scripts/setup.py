"""Cross-platform local setup; run with Python 3.11+ from the extracted project."""

import shutil
import subprocess
import sys
import venv
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required.")
    target = root / ".venv"
    if not target.exists():
        venv.EnvBuilder(with_pip=True).create(target)
    python = target / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "-c", "constraints.txt", "-e", ".[test]"],
        cwd=root,
        check=True,
    )
    if not (root / ".env").exists():
        shutil.copyfile(root / ".env.example", root / ".env")
    print("Setup complete. Existing .env was preserved.")
    print(f'Start: "{python}" -m uvicorn app.main:app --reload --no-access-log')
    print(f'Test:  "{python}" -m pytest')


if __name__ == "__main__":
    main()
