from fastapi.testclient import TestClient

from app.core.config import Settings
from scripts.seed_reference import load_reference_rows, seed_reference


def test_reference_files_have_the_planned_sizes() -> None:
    service_codes, providers = load_reference_rows()

    assert len(service_codes) >= 60
    assert len(providers) == 40
    repeatable = {row["code"] for row in service_codes if row["repeatable"]}
    assert repeatable, "legitimate repeats need repeatable service codes"
    for row in service_codes:
        if row["repeatable"]:
            assert row["min_interval_days"] is not None and row["max_per_week"] is not None


def test_seed_is_idempotent(settings: Settings, sql) -> None:
    seed_reference(settings)
    seed_reference(settings)

    service_codes, providers = load_reference_rows()
    assert sql("select count(*) from service_codes")[0][0] == len(service_codes)
    assert sql("select count(*) from providers")[0][0] == len(providers)


def test_providers_lookup_is_paginated(settings: Settings, auth_client: TestClient) -> None:
    seed_reference(settings)

    response = auth_client.get("/api/v1/reference/providers", params={"page": 2, "page_size": 15})

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 40
    assert len(body["items"]) == 15
    assert body["items"][0]["provider_id"] == "PRV-0016"
    assert set(body["items"][0]) == {"provider_id", "name", "city"}


def test_service_codes_lookup_returns_repeat_rules(settings: Settings, auth_client: TestClient) -> None:
    seed_reference(settings)

    response = auth_client.get("/api/v1/reference/service-codes", params={"page_size": 200})

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == len(body["items"])
    physio = next(item for item in body["items"] if item["category"] == "physiotherapy")
    assert set(physio) == {
        "code",
        "description",
        "category",
        "repeatable",
        "min_interval_days",
        "max_per_week",
    }
