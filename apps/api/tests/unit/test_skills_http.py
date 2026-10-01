# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
from ca_api.interfaces.http.main import app
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


def test_http_list_skills() -> None:
    resp = client.get("/api/v1/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 14
    ids = [s["skill_id"] for s in data]
    assert "solver-scheduling" in ids
    assert "smart-swap-recommender" in ids


def test_http_get_skill_detail() -> None:
    resp = client.get("/api/v1/skills/solver-scheduling")
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill_id"] == "solver-scheduling"
    assert "validate_solver_payload.py" in data["scripts"]
    assert len(data["content_sha256"]) == 64


def test_http_get_skill_detail_not_found() -> None:
    resp = client.get("/api/v1/skills/non-existent-skill")
    assert resp.status_code == 404


def test_http_verify_skill_live() -> None:
    resp = client.post("/api/v1/skills/solver-scheduling/verify", headers=headers(client, "lan"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is True
    assert data["status"] == "VERIFIED"
    assert "validate_solver_payload.py" in data["script_results"]
    assert data["script_results"]["validate_solver_payload.py"]["passed"] is True
