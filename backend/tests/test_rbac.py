"""Roles are enforced by the API. Each test proves the wrong person is refused, not only that the
right person is allowed."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import DEMO_PASSWORD, DEMO_USERNAME
from tests.ingest_fixtures import BASE, to_csv_files
from tests.test_imports_api import api, upload  # noqa: F401 - fixture reuse

USERS = "/api/v1/users"
PASSWORD = "correct-horse-battery"


def onboard(admin: TestClient, username: str, role: str) -> dict:
    response = admin.post(
        USERS, json={"username": username, "display_name": username.title(), "role": role, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response.json()


def sign_in(app_client: TestClient, username: str, password: str = PASSWORD) -> TestClient:
    """A second browser: its own cookie jar against the same app."""
    client = TestClient(app_client.app)
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client


def first_alert(admin: TestClient) -> dict:
    batch = upload(admin, to_csv_files(BASE)).json()
    admin.post("/api/v1/runs", json={"scope": "batch", "batch_id": batch["id"]})
    alerts = admin.get("/api/v1/alerts").json()["items"]
    assert alerts, "the base fixture should raise at least one alert"
    return alerts[0]


# Onboarding


def test_environment_login_bootstraps_the_first_admin_only_once(client: TestClient) -> None:
    first = client.post("/api/v1/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD})
    assert first.json()["role"] == "admin"
    seeded = client.get(USERS).json()
    assert [(u["username"], u["role"]) for u in seeded] == [
        (DEMO_USERNAME, "admin"),
        ("reviewer", "senior_reviewer"),
        ("analyst", "analyst"),
    ]

    onboard(client, "asha", "analyst")
    # Deactivating the bootstrap admin is refused for the admin themselves, so make a second admin do it.
    onboard(client, "root2", "admin")
    other = sign_in(client, "root2")
    admin_id = client.get(USERS).json()[0]["id"]
    assert other.patch(f"{USERS}/{admin_id}", json={"is_active": False}).status_code == 200

    # With users present, the environment password no longer opens a door.
    again = TestClient(client.app).post(
        "/api/v1/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD}
    )
    assert again.status_code == 401


def test_only_admins_manage_users(auth_client: TestClient) -> None:
    onboard(auth_client, "asha", "analyst")
    onboard(auth_client, "sunil", "senior_reviewer")

    for username in ("asha", "sunil"):
        other = sign_in(auth_client, username)
        assert other.get(USERS).status_code == 403
        assert (
            other.post(
                USERS, json={"username": "x1", "display_name": "X", "role": "admin", "password": PASSWORD}
            ).status_code
            == 403
        )
        assert other.get("/api/v1/auth/me").json()["role"] in ("analyst", "senior_reviewer")


def test_usernames_are_unique_and_validated(auth_client: TestClient) -> None:
    onboard(auth_client, "asha", "analyst")
    assert (
        auth_client.post(
            USERS, json={"username": "asha", "display_name": "A", "role": "analyst", "password": PASSWORD}
        ).status_code
        == 409
    )
    assert (
        auth_client.post(
            USERS, json={"username": "Bad Name", "display_name": "A", "role": "analyst", "password": PASSWORD}
        ).status_code
        == 422
    )
    assert (
        auth_client.post(
            USERS, json={"username": "ok", "display_name": "A", "role": "analyst", "password": "short"}
        ).status_code
        == 422
    )


def test_deactivated_users_lose_access_immediately(auth_client: TestClient) -> None:
    user = onboard(auth_client, "asha", "analyst")
    asha = sign_in(auth_client, "asha")
    assert asha.get("/api/v1/auth/me").status_code == 200

    auth_client.patch(f"{USERS}/{user['id']}", json={"is_active": False})

    assert asha.get("/api/v1/auth/me").status_code == 401
    assert sign_in_fails(auth_client, "asha")


def sign_in_fails(app_client: TestClient, username: str) -> bool:
    return (
        TestClient(app_client.app)
        .post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        .status_code
        == 401
    )


def test_role_changes_apply_to_live_sessions(auth_client: TestClient) -> None:
    user = onboard(auth_client, "asha", "analyst")
    asha = sign_in(auth_client, "asha")
    assert asha.get(USERS).status_code == 403

    auth_client.patch(f"{USERS}/{user['id']}", json={"role": "admin"})

    assert asha.get(USERS).status_code == 200


def test_an_admin_cannot_remove_their_own_access(auth_client: TestClient) -> None:
    me = auth_client.get(USERS).json()[0]
    assert auth_client.patch(f"{USERS}/{me['id']}", json={"is_active": False}).status_code == 409
    assert auth_client.patch(f"{USERS}/{me['id']}", json={"role": "analyst"}).status_code == 409


# Escalation


def test_escalation_needs_a_reason_and_a_target(api: TestClient) -> None:  # noqa: F811
    alert = first_alert(api)
    url = f"/api/v1/alerts/{alert['id']}"
    assert api.patch(url, json={"status": "escalated"}).status_code == 422
    assert api.patch(url, json={"status": "escalated", "note": "Looks staged"}).status_code == 422
    assert api.patch(url, json={"status": "dismissed"}).status_code == 422
    assert api.patch(url, json={"status": "reviewed", "escalate_to": "admin"}).status_code == 422


def test_analysts_escalate_but_cannot_decide_escalations(api: TestClient) -> None:  # noqa: F811
    alert = first_alert(api)
    onboard(api, "asha", "analyst")
    onboard(api, "sunil", "senior_reviewer")
    asha = sign_in(api, "asha")
    url = f"/api/v1/alerts/{alert['id']}"

    escalated = asha.patch(
        url, json={"status": "escalated", "note": "Invoice looks altered", "escalate_to": "senior_reviewer"}
    )
    assert escalated.status_code == 200, escalated.text
    body = escalated.json()
    assert (body["status"], body["escalated_to"], body["escalated_by"]) == ("escalated", "senior_reviewer", "asha")
    assert body["escalation_reason"] == "Invoice looks altered"

    # The analyst cannot decide it, nor can another analyst.
    assert asha.patch(url, json={"status": "reviewed"}).status_code == 403
    onboard(api, "bala", "analyst")
    assert sign_in(api, "bala").patch(url, json={"status": "dismissed", "note": "no"}).status_code == 403

    sunil = sign_in(api, "sunil")
    decided = sunil.patch(url, json={"status": "reviewed", "note": "Confirmed with the hospital"})
    assert decided.status_code == 200, decided.text
    assert decided.json()["escalated_to"] is None
    assert decided.json()["reviewed_by"] == "sunil"


def test_a_reviewer_cannot_decide_their_own_escalation(api: TestClient) -> None:  # noqa: F811
    alert = first_alert(api)
    onboard(api, "sunil", "senior_reviewer")
    sunil = sign_in(api, "sunil")
    url = f"/api/v1/alerts/{alert['id']}"
    # Only upwards: a senior reviewer cannot escalate to their own level.
    same_level = {"status": "escalated", "note": "Second opinion", "escalate_to": "senior_reviewer"}
    assert sunil.patch(url, json=same_level).status_code == 403
    to_admin = {"status": "escalated", "note": "Needs admin", "escalate_to": "admin"}
    assert sunil.patch(url, json=to_admin).status_code == 200

    assert sunil.patch(url, json={"status": "dismissed", "note": "Changed my mind"}).status_code == 403
    # The admin (a different person) may.
    assert api.patch(url, json={"status": "dismissed", "note": "Provider contract allows it"}).status_code == 200


def test_escalations_go_to_the_level_chosen_and_show_in_its_queue(api: TestClient) -> None:  # noqa: F811
    alert = first_alert(api)
    onboard(api, "asha", "analyst")
    onboard(api, "sunil", "senior_reviewer")
    asha, sunil = sign_in(api, "asha"), sign_in(api, "sunil")
    url = f"/api/v1/alerts/{alert['id']}"

    assert asha.patch(url, json={"status": "escalated", "note": "Big one", "escalate_to": "admin"}).status_code == 200
    # Escalated to admin: the senior reviewer neither sees it in their queue nor decides it.
    assert sunil.get("/api/v1/alerts/escalations").json()["to_review"] == []
    assert sunil.patch(url, json={"status": "reviewed", "note": "ok"}).status_code == 403
    assert [a["id"] for a in api.get("/api/v1/alerts/escalations").json()["to_review"]] == [alert["id"]]
    assert [a["id"] for a in asha.get("/api/v1/alerts/escalations").json()["sent"]] == [alert["id"]]

    api.patch(url, json={"status": "open", "note": "Send back"})
    asha.patch(url, json={"status": "escalated", "note": "Check this", "escalate_to": "senior_reviewer"})
    assert [a["id"] for a in sunil.get("/api/v1/alerts/escalations").json()["to_review"]] == [alert["id"]]


def test_every_decision_is_audited_with_the_actor_and_role(api: TestClient, sql) -> None:  # noqa: F811
    alert = first_alert(api)
    onboard(api, "asha", "analyst")
    asha = sign_in(api, "asha")
    asha.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={"status": "escalated", "note": "Looks staged", "escalate_to": "senior_reviewer"},
    )
    api.patch(f"/api/v1/alerts/{alert['id']}", json={"status": "reviewed", "note": "Confirmed"})

    rows = sql(
        "select actor, details->>'previous', details->>'status', details->>'actor_role' from audit_log "
        "where entity = 'alert' and entity_id = :id order by id",
        id=str(alert["id"]),
    )
    assert [tuple(r) for r in rows] == [
        ("asha", "open", "escalated", "analyst"),
        (DEMO_USERNAME, "escalated", "reviewed", "admin"),
    ]
    onboarding = sql("select action, actor from audit_log where entity = 'user' order by id")
    assert [tuple(r) for r in onboarding] == [("demo_accounts_seeded", DEMO_USERNAME), ("user_created", DEMO_USERNAME)]


# Quick sign-in for demos


def test_demo_accounts_are_hidden_unless_quick_login_is_on(client: TestClient) -> None:
    client.post("/api/v1/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD})
    # No session needed, but with the switch off nothing is listed.
    assert TestClient(client.app).get("/api/v1/auth/demo-accounts").json() == []


def test_quick_login_on_a_fresh_database_lists_the_demo_accounts_before_anyone_signs_in(settings, db_url: str) -> None:
    from tests.conftest import make_settings

    quick = make_settings(database_url=db_url, demo_quick_login=True)
    with TestClient(create_app(quick)) as client:
        listed = client.get("/api/v1/auth/demo-accounts").json()
        assert [(a["username"], a["role"]) for a in listed] == [
            (DEMO_USERNAME, "admin"),
            ("reviewer", "senior_reviewer"),
            ("analyst", "analyst"),
        ]
        # Listing again does not seed twice, and each account signs in.
        assert len(client.get("/api/v1/auth/demo-accounts").json()) == 3
        assert sign_in(client, "analyst", DEMO_PASSWORD).get("/api/v1/auth/me").json()["role"] == "analyst"


def test_demo_accounts_list_live_seeded_accounts_with_the_demo_password(settings, db_url: str) -> None:
    from tests.conftest import make_settings

    quick = make_settings(database_url=db_url, demo_quick_login=True)
    with TestClient(create_app(quick)) as client:
        client.post("/api/v1/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD})
        listed = TestClient(client.app).get("/api/v1/auth/demo-accounts").json()
        assert [(a["username"], a["role"], a["password"]) for a in listed] == [
            (DEMO_USERNAME, "admin", DEMO_PASSWORD),
            ("reviewer", "senior_reviewer", DEMO_PASSWORD),
            ("analyst", "analyst", DEMO_PASSWORD),
        ]
        # Each listed account really signs in with that password.
        for account in listed:
            assert (
                sign_in(client, account["username"], account["password"]).get("/api/v1/auth/me").json()["role"]
                == account["role"]
            )

        # A deactivated demo account drops off the list.
        analyst_id = next(u["id"] for u in client.get(USERS).json() if u["username"] == "analyst")
        client.patch(f"{USERS}/{analyst_id}", json={"is_active": False})
        assert [a["username"] for a in TestClient(client.app).get("/api/v1/auth/demo-accounts").json()] == [
            DEMO_USERNAME,
            "reviewer",
        ]
