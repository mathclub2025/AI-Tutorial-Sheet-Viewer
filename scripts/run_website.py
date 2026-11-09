"""Supervise the separate frontend/backend services without opening extra windows."""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Temporary SQLite and simulated AI/storage")
    parser.add_argument("--port", type=int, default=3100)
    args = parser.parse_args()
    if args.preview and args.port != 3100:
        parser.error("The test preview storage CORS is configured for port 3100")
    node = shutil.which("node")
    if not node or not (ROOT / "frontend/.next/BUILD_ID").exists():
        raise SystemExit("Install Node dependencies and run npm run build inside frontend first.")
    env = dict(os.environ)
    if args.preview:
        env.update(BACKEND_URL="http://127.0.0.1:8010", BACKEND_API_KEY="student-gateway-key", WEBSITE_ORIGIN="http://localhost:3100")
        commands = [([sys.executable, "scripts/run_local_preview.py"], ROOT / "backend")]
        print("LOCAL TEST PREVIEW: fake extraction, fake storage, temporary data.", flush=True)
    else:
        commands = [
            ([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"], ROOT / "backend"),
            ([sys.executable, "-m", "uvicorn", "app.data_service.main:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"], ROOT / "backend"),
            ([sys.executable, "-m", "app.data_service.worker"], ROOT / "backend"),
        ]
    commands.append(([node, str(ROOT / "frontend/node_modules/next/dist/bin/next"), "start", "-H", "127.0.0.1", "-p", str(args.port)], ROOT / "frontend"))
    processes = []
    try:
        for command, cwd in commands:
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
        print(f"Starting website at http://localhost:{args.port}. Ctrl+C stops this stack.", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        raise SystemExit("A service stopped. Check its output above; the other services will stop too.")
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

if __name__ == "__main__":
    main()
