from fastapi.testclient import TestClient


def test_unknown_route_uses_the_error_format(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found", "details": None}}


def test_request_validation_errors_list_every_problem(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={})

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert {tuple(d["loc"]) for d in body["details"]} == {("body", "username"), ("body", "password")}


def test_invalid_pagination_is_a_validation_error(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/reference/providers", params={"page_size": 0})

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["query", "page_size"]
