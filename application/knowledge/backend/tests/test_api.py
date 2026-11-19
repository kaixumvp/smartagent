def _create_kb(client, name="demo"):
    r = client.post("/v1/knowledge-bases", json={"name": name})
    assert r.status_code == 200
    return r.json()["id"]


def _upload_and_process(client, kb_id, filename, content, content_type):
    r = client.post(
        f"/v1/knowledge-bases/{kb_id}/documents",
        files={"file": (filename, content, content_type)},
    )
    assert r.status_code == 201
    doc_id = r.json()["id"]
    r = client.post("/v1/jobs/process")
    assert r.status_code == 200
    return doc_id


def test_upload_process_search_flow(client):
    kb_id = _create_kb(client)
    doc_id = _upload_and_process(
        client, kb_id, "note.md", b"# Note\n\nThe Q3 revenue was 42 million.\n", "text/markdown"
    )

    r = client.get(f"/v1/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert r.json()["parser_name"] == "markdown"

    r = client.post("/v1/search", json={"query": "revenue", "kb_ids": [kb_id]})
    assert r.status_code == 200
    body = r.json()
    assert body["chunks"], "expected at least one hit"
    assert "revenue" in body["chunks"][0]["text"].lower()
    assert body["chunks"][0]["evidence"]["document_id"] == doc_id
    assert body["chunks"][0]["start_offset"] == 0


def test_search_modes_and_internal_key(client):
    kb_id = _create_kb(client)
    _upload_and_process(client, kb_id, "n.txt", b"project XK-4021 budget is approved", "text/plain")

    for mode in ["hybrid", "vector", "keyword"]:
        r = client.post("/v1/search", json={"query": "XK-4021", "kb_ids": [kb_id], "mode": mode})
        assert r.status_code == 200
        assert r.json()["mode"] == mode
        assert r.json()["chunks"], f"expected hits in {mode} mode"

    # Internal Retrieve API is open when no INTEGRATION_KEY is configured.
    r = client.post("/internal/search", json={"query": "XK-4021", "kb_ids": [kb_id]})
    assert r.status_code == 200


def test_markdown_download(client):
    kb_id = _create_kb(client)
    doc_id = _upload_and_process(client, kb_id, "n.md", b"# Title\n\nbody", "text/markdown")
    r = client.get(f"/v1/documents/{doc_id}/markdown")
    assert r.status_code == 200
    assert "Title" in r.text


def test_delete_document_removes_from_search(client):
    kb_id = _create_kb(client)
    doc_id = _upload_and_process(client, kb_id, "n.txt", b"hello world", "text/plain")
    r = client.delete(f"/v1/documents/{doc_id}")
    assert r.status_code == 200
    assert client.get(f"/v1/documents/{doc_id}").status_code == 404
    r = client.post("/v1/search", json={"query": "hello", "kb_ids": [kb_id]})
    assert r.json()["chunks"] == []


def test_reingest_rebuilds_index(client):
    kb_id = _create_kb(client)
    doc_id = _upload_and_process(client, kb_id, "n.txt", b"first version text", "text/plain")
    r = client.post(f"/v1/documents/{doc_id}/reingest")
    assert r.status_code == 200
    assert r.json()["kind"] == "reingest"
    client.post("/v1/jobs/process")
    assert client.get(f"/v1/documents/{doc_id}").json()["status"] == "ready"
