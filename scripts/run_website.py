"""Supervise the separate frontend/backend services without opening extra windows."""
import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def stream_output(label, stream):
    for line in iter(stream.readline, ""):
        print(f"[{label}] {line.rstrip()}", flush=True)
    stream.close()


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
        commands = [("preview backend", [sys.executable, "scripts/run_local_preview.py"], ROOT / "backend")]
        print("LOCAL TEST PREVIEW: fake extraction, fake storage, temporary data.", flush=True)
    else:
        commands = [
            ("api", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"], ROOT / "backend"),
            ("data service", [sys.executable, "-m", "uvicorn", "app.data_service.main:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"], ROOT / "backend"),
            ("worker", [sys.executable, "-m", "app.data_service.worker"], ROOT / "backend"),
        ]
    commands.append(("website", [node, str(ROOT / "frontend/node_modules/next/dist/bin/next"), "start", "-H", "127.0.0.1", "-p", str(args.port)], ROOT / "frontend"))
    processes = []
    try:
        for label, command, cwd in commands:
            try:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except OSError as exc:
                print(
                    f"[{label}] failed to start in {cwd}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                raise SystemExit(1) from exc
            processes.append((label, process))
            threading.Thread(
                target=stream_output,
                args=(label, process.stdout),
                daemon=True,
            ).start()
        print(f"Starting website at http://localhost:{args.port}. Ctrl+C stops this stack.", flush=True)
        while all(process.poll() is None for _, process in processes):
            time.sleep(1)
        for label, process in processes:
            return_code = process.poll()
            if return_code is not None:
                if return_code == 0:
                    print(f"[{label}] stopped unexpectedly (exit code 0).", flush=True)
                else:
                    print(f"[{label}] stopped with exit code {return_code}.", file=sys.stderr, flush=True)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("Stopping website stack...", flush=True)
    finally:
        for _, process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for label, process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(f"[{label}] did not stop gracefully; terminating it.", file=sys.stderr, flush=True)
                process.kill()

if __name__ == "__main__":
    main()
