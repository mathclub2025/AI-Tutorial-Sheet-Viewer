"""Run the API and two explicitly fake peers on loopback. Ctrl+C stops all three."""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = {
        **os.environ,
        "APP_ENV": "development",
        "BACKEND_MODE": "http",
        "API_KEY": "local-dev-secret",
        "PERSON2_BASE_URL": "http://127.0.0.1:8001",
        "AI_BASE_URL": "http://127.0.0.1:8002",
        "INTERNAL_SERVICE_TOKEN": "integration-demo-token",
        "PERSON2_SERVICE_TOKEN": "integration-demo-token",
        "AI_SERVICE_TOKEN": "integration-demo-token",
        "DOCUMENT_DISPATCH_TOKEN": "integration-demo-token",
        "AI_CALLBACK_TOKEN": "integration-demo-token",
        "CAPTURE_REQUIRED": "true",
        "RATE_LIMIT_PER_MINUTE": "120",
    }
    children = []
    try:
        for module, port in [
            ("scripts.mock_services:p2", 8001),
            ("scripts.mock_services:ai", 8002),
            ("app.main:app", 8000),
        ]:
            children.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        module,
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--no-access-log",
                    ],
                    cwd=ROOT,
                    env=env,
                )
            )
        print("LOCAL MOCK INTEGRATION ONLY: http://127.0.0.1:8000/docs", flush=True)
        print("In another terminal: python scripts/check_integration.py", flush=True)
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A service exited. Check for a port already in use.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
