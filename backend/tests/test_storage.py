import uuid

import httpx

from app.core.config import Settings
from app.storage.spaces import Storage


def test_uploaded_object_lands_under_prefix_and_is_downloadable(
    live_settings: Settings,
) -> None:
    storage = Storage.from_settings(live_settings)
    name = f"tests/{uuid.uuid4()}.txt"

    key = storage.upload(name, b"hello spaces", content_type="text/plain")
    try:
        assert key == f"{live_settings.spaces_prefix}{name}"
        assert storage.download(name) == b"hello spaces"
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


def test_local_storage_keeps_files_under_its_directory(tmp_path) -> None:
    from app.storage.spaces import LocalStorage, Storage
    from tests.conftest import make_settings

    storage = Storage.from_settings(make_settings(local_storage_dir=str(tmp_path)))
    assert isinstance(storage, LocalStorage)
    key = storage.upload("claims/CLM-1/docs/1.pdf", b"%PDF-1.4", "application/pdf")
    assert key == storage.key("claims/CLM-1/docs/1.pdf")
    assert (tmp_path / key).read_bytes() == b"%PDF-1.4"
    assert storage.download("claims/CLM-1/docs/1.pdf") == b"%PDF-1.4"
    storage.ping()
    try:
        storage.download("../../outside")
    except ValueError:
        pass
    else:
        raise AssertionError("a name outside the directory must be refused")
