"""Exercise localhost MOCK peers. This deliberately submits fake document metadata."""

from uuid import uuid4

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10, trust_env=False) as client:

        def call(method, path, data=None, internal=False):
            headers = (
                {"X-Internal-Token": "integration-demo-token"}
                if internal
                else {"X-API-Key": "local-dev-secret"}
            )
            res = client.request(method, path, json=data, headers=headers)
            res.raise_for_status()
            return res.json()

        assert call("GET", "/health/ready")["upstream_reachability_checked"] is True
        assert call("GET", "/api/v1/catalog")["combinations"]
        assert call("POST", "/api/v1/ask", {"query": "differentiate"})["captured"] is True
        dispatch = {
            "document_id": "demo-document",
            "document_version": "v1",
            "source_type": "tutorial",
            "client_job_key": "demo-job-" + uuid4().hex,
        }
        first = call("POST", "/internal/v1/documents/dispatch", dispatch, True)
        second = call("POST", "/internal/v1/documents/dispatch", dispatch, True)
        assert first["job_id"] == second["job_id"]
        job = first["job_id"]
        assert (
            call("GET", f"/internal/v1/document-jobs/{job}", internal=True)["status"] == "completed"
        )
        result = {
            **dispatch,
            "event_id": str(uuid4()),
            "status": "completed",
            "questions": [
                {
                    "extraction_id": "q1",
                    "text": "Differentiate x^3",
                    "subject": "Engineering Mathematics I",
                    "source": {
                        "document_id": "demo-document",
                        "source_type": "tutorial",
                        "page_number": 1,
                    },
                    "official_solution": "3x^2",
                    "confidence": 0.95,
                    "needs_review": True,
                }
            ],
        }
        for _ in range(2):
            ack = call("POST", f"/internal/v1/document-jobs/{job}/result", result, True)
            assert ack["accepted"] and ack["indexing_status"] == "pending"
        print(
            "PASS: live peer checks, catalog, captured ask, duplicate dispatch, status and replayed result callback"
        )
        print("These are mock peers. No real database, document extraction or indexing was tested.")


if __name__ == "__main__":
    main()
