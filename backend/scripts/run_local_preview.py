"""LOCAL TEST PREVIEW ONLY. SQLite plus fake storage/AI, never production.

Exercises real API/data-service/worker code through the test adapters. Nothing is
sent to B2 or a model. Uploaded bytes and the database are discarded on shutdown.
"""
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_backend_management import approve, auth, backend, extraction, publish


def main():
    with tempfile.TemporaryDirectory(prefix="mathclub-preview-") as temporary:
        fixture = backend.__wrapped__(Path(temporary))
        state = next(fixture)
        headers = auth(state)
        document, question, _, _ = extraction(state, headers)
        approve(state, headers, question)
        publish(state, headers, document)
        state.worker.run_once()
        state.s3.generate_presigned_url = lambda operation, *, Params, ExpiresIn, HttpMethod=None: "http://localhost:8010/fixture-storage/" + Params["Key"]

        def finish_jobs():
            # Deterministic fake extraction, explicitly for portal verification.
            while state.worker.run_once():
                pass
            for job in list(state.peer.jobs.values()):
                if job["status"] == "completed":
                    continue
                job.update(status="completed", progress=100, extracted_count=1)
                payload = {k: job[k] for k in ("document_id", "document_version", "source_type", "client_job_key")}
                payload.update(event_id="preview-" + job["job_id"], status="completed", questions=[{
                    "extraction_id": "preview-q1", "text": "LOCAL TEST EXTRACT: Differentiate x squared",
                    "subject": "Mathematics", "module": "Module 1", "topic": "Differentiation", "official_solution": "2x",
                    "source": {"document_id": job["document_id"], "source_type": job["source_type"], "page_number": 1},
                }])
                response = state.client.post("/internal/v1/document-jobs/" + job["job_id"] + "/result", headers={"X-Internal-Token": "callback-token"}, json=payload)
                if response.status_code != 200:
                    raise RuntimeError("Preview callback failed: " + str(response.status_code))

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def cors(self):
                self.send_header("Access-Control-Allow-Origin", "http://localhost:3100")
                self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def do_OPTIONS(self):
                self.send_response(204)
                self.cors()
                self.end_headers()

            def do_PUT(self):
                if not self.path.startswith("/fixture-storage/"):
                    self.send_error(404)
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 15 * 1024 * 1024:
                    self.send_error(413)
                    return
                key = unquote(urlsplit(self.path).path.removeprefix("/fixture-storage/"))
                state.s3.objects[key] = (self.rfile.read(size), self.headers.get("Content-Type", ""))
                self.send_response(200)
                self.cors()
                self.end_headers()

            def proxy(self):
                if self.path.startswith("/fixture-storage/"):
                    key = unquote(urlsplit(self.path).path.removeprefix("/fixture-storage/"))
                    value = state.s3.objects.get(key)
                    if not value:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", value[1])
                    self.end_headers()
                    self.wfile.write(value[0])
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if size > 65536:
                    self.send_error(413)
                    return
                body = self.rfile.read(size) if size else None
                finish_jobs()
                response = state.client.request(self.command, self.path, content=body, headers={k: v for k, v in self.headers.items() if k.lower() in {"authorization", "x-api-key", "content-type"}})
                self.send_response(response.status_code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response.content)

            do_GET = proxy
            do_POST = proxy
            do_PATCH = proxy

        server = HTTPServer(("127.0.0.1", 8010), Handler)
        print("LOCAL TEST PREVIEW at http://localhost:8010 — fake AI and storage; temporary data", flush=True)
        print("Staff: admin@example.edu / local-test-password; student API key: student-gateway-key", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            fixture.close()


if __name__ == "__main__":
    main()
