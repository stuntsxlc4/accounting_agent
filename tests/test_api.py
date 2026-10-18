from fastapi.testclient import TestClient

from accounting_agent import storage
from accounting_agent.api import create_app

TOKEN = "test-token"


def pdf_bytes(text: str) -> bytes:
    return b"%PDF-1.4\n" + text.encode()


def client() -> TestClient:
    return TestClient(create_app(TOKEN, frontend_dir=None), headers={"X-App-Token": TOKEN})


def upload(c, name, content, overwrite=False):
    return c.post(
        f"/api/statements/upload?month=2026-08&overwrite={str(overwrite).lower()}",
        files=[("files", (name, content, "application/pdf"))],
    )


def test_requires_token(app_dirs):
    assert TestClient(create_app(TOKEN, frontend_dir=None)).get("/api/history").status_code == 403


def test_upload_skips_identical_and_asks_before_replacing(app_dirs, statements_folder):
    c = client()
    assert upload(c, "wyciag.pdf", pdf_bytes("a")).json()["added"] == ["wyciag.pdf"]
    assert upload(c, "wyciag.pdf", pdf_bytes("a")).json()["skipped"] == ["wyciag.pdf"]

    conflict = upload(c, "wyciag.pdf", pdf_bytes("b"))
    assert conflict.status_code == 409 and conflict.json()["conflicts"] == ["wyciag.pdf"]
    assert (statements_folder / "wyciag.pdf").read_bytes() == pdf_bytes("a")

    replaced = upload(c, "wyciag.pdf", pdf_bytes("b"), overwrite=True)
    assert replaced.json()["replaced"] == ["wyciag.pdf"]
    assert (statements_folder / "wyciag.pdf").read_bytes() == pdf_bytes("b")


def test_upload_rejects_non_pdf(app_dirs):
    response = upload(client(), "wyciag.pdf", b"to nie jest pdf")
    assert response.status_code == 400


def test_delete_moves_to_trash(app_dirs, statements_folder, monkeypatch):
    trashed = []
    monkeypatch.setattr(
        "accounting_agent.api.send2trash", lambda p: trashed.append(p) or p.unlink()
    )
    c = client()
    upload(c, "wyciag.pdf", pdf_bytes("a"))
    response = c.delete("/api/statements?month=2026-08&name=wyciag.pdf")
    assert response.json()["files"] == [] and trashed == [statements_folder / "wyciag.pdf"]


def test_delete_cannot_escape_folder(app_dirs):
    response = client().delete("/api/statements?month=2026-08&name=../../.env")
    assert response.status_code == 404


def test_history_and_last_reconcile(app_dirs):
    storage.add_history("download", "2026-08", "Faktur w KSeF: 17")
    storage.save_reconcile("2026-08", {"banks": [], "unpaid": [], "unreadable": []})
    c = client()
    assert c.get("/api/history").json()[0]["summary"] == "Faktur w KSeF: 17"
    assert c.get("/api/reconcile/last?month=2026-08").json()["record"]["month"] == "2026-08"
