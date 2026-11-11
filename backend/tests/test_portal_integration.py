"""Portal contract regressions through the real gateway/data-service adapters."""
from test_backend_management import approve, auth, extraction, publish, search
from test_backend_management import backend as backend


def test_portal_metadata_flags_and_revision_conflicts(backend):
    headers = auth(backend)
    doc, question, _, _ = extraction(backend, headers)
    path = "/api/v1/admin/questions/" + question["id"]
    response = backend.client.patch(path, headers=headers, json={
        "expected_revision": question["revision"], "topics": ["Calculus", "Derivatives", "calculus"], "difficulty": "medium",
    })
    assert response.status_code == 200, response.text
    updated = response.json()
    assert set(updated["topics"]) == {"Calculus", "Derivatives"}
    assert updated["difficulty"] == "medium"
    assert backend.client.patch(path, headers=headers, json={"expected_revision": question["revision"], "text": "stale edit"}).status_code == 409
    flagged = backend.client.post(path + "/review", headers=headers, json={
        "expected_revision": updated["revision"], "status": "pending_review", "flagged": True, "note": "Check solution",
    })
    assert flagged.status_code == 200, flagged.text
    assert backend.client.get(path, headers=headers).json()["flag_note"] == "Check solution"
    counts = backend.client.get("/api/v1/admin/documents/" + doc, headers=headers).json()
    assert counts["question_count"] == 1 and counts["flagged_count"] == 1
    approved = approve(backend, headers, flagged.json())
    assert approved["flag_note"] is None
    assert publish(backend, headers, doc).status_code == 200
    found = search(backend).json()["items"][0]["question"]
    assert found["difficulty"] == "medium" and len(found["topics"]) == 2


def test_classification_unpublishes_and_requires_review(backend):
    headers = auth(backend)
    doc, question, _, _ = extraction(backend, headers)
    approve(backend, headers, question)
    publish(backend, headers, doc)
    path = "/api/v1/admin/documents/" + doc + "/classification"
    response = backend.client.patch(path, headers=headers, json={"expected_source_type": "tutorial", "source_type": "pyq"})
    assert response.status_code == 200, response.text
    assert response.json()["visibility"] == "private"
    assert search(backend).json()["items"] == []
    changed = backend.client.get("/api/v1/admin/questions/" + question["id"], headers=headers).json()
    assert changed["status"] == "pending_review" and changed["solution_status"] == "pending_review"
    assert changed["source_type"] == "pyq"
    assert backend.client.patch(path, headers=headers, json={"expected_source_type": "tutorial", "source_type": "pyq"}).status_code == 409


def test_login_limits_do_not_pool_unrelated_accounts(backend):
    for _ in range(10):
        assert backend.client.post("/api/v1/auth/login", json={"email": "missing@example.edu", "password": "wrong"}).status_code == 401
    assert backend.client.post("/api/v1/auth/login", json={"email": "missing@example.edu", "password": "wrong"}).status_code == 429
    assert auth(backend)
