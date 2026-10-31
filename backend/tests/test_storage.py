import uuid

import httpx

from app.config import Settings
from app.storage import Storage


def test_uploaded_object_lands_under_prefix_and_is_downloadable(
    live_settings: Settings,
) -> None:
    storage = Storage.from_settings(live_settings)
    name = f"tests/{uuid.uuid4()}.txt"

    key = storage.upload(name, b"hello spaces", content_type="text/plain")
    try:
        assert key == f"{live_settings.spaces_prefix}{name}"
        response = httpx.get(storage.presigned_download_url(name, expires_in=60))
        assert response.status_code == 200
        assert response.content == b"hello spaces"
    finally:
        storage.delete(name)


def test_deleted_object_is_no_longer_downloadable(live_settings: Settings) -> None:
    storage = Storage.from_settings(live_settings)
    name = f"tests/{uuid.uuid4()}.txt"
    storage.upload(name, b"short-lived", content_type="text/plain")

    storage.delete(name)

    response = httpx.get(storage.presigned_download_url(name, expires_in=60))
    assert response.status_code == 404
