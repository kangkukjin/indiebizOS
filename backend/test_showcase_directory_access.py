"""공개파일: 실제 빈 폴더와 저장장치 읽기 실패를 구분한다."""
import errno
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401
import api_showcase


@pytest.fixture
def gallery(tmp_path, monkeypatch):
    monkeypatch.setattr(api_showcase, "_read_env", lambda name: "fixture-secret")
    monkeypatch.setattr(api_showcase, "_load_state", lambda: {
        "folders": [{"id": "folder", "path": str(tmp_path), "mode": "files"}],
        "baskets": [{"slug": "gallery", "folder_ids": ["folder"]}],
    })
    app = FastAPI()
    app.include_router(api_showcase.router)
    with TestClient(app) as client:
        yield client, tmp_path


def listing(client, **kwargs):
    return client.get(
        "/showcase/list/gallery", params={"path": "folder"},
        headers={"X-Showcase-Secret": "fixture-secret"}, **kwargs,
    )


def test_empty_and_populated_directory(gallery):
    client, folder = gallery
    response = listing(client)
    assert response.status_code == 200
    assert response.json()["items"] == [] and response.json()["dirs"] == []
    (folder / "photo-album").mkdir()
    (folder / "note.txt").write_text("fixture")
    response = listing(client)
    assert response.status_code == 200
    assert response.json()["dirs"] == [{"name": "photo-album", "path": "folder/photo-album"}]
    assert [item["title"] for item in response.json()["items"]] == ["note.txt"]


@pytest.mark.parametrize("error_number", [errno.EPERM, errno.EACCES, errno.EIO])
def test_unreadable_directory_is_not_reported_as_empty(gallery, monkeypatch, error_number):
    client, folder = gallery
    scan = os.scandir

    def fail(path):
        if str(path) == str(folder):
            raise OSError(error_number, "fixture failure", str(folder))
        return scan(path)

    monkeypatch.setattr(os, "scandir", fail)
    response = listing(client)
    assert response.status_code == 503
    data = response.json()
    assert "items" not in data and "dirs" not in data
    expected = "권한" if error_number != errno.EIO else "저장장치"
    assert expected in data["detail"]
    assert str(folder) not in response.text


def test_directory_failure_does_not_bypass_gallery_auth(gallery, monkeypatch):
    client, _ = gallery

    def unexpected_scan(path):
        pytest.fail("Unauthenticated requests must not inspect the disk")

    monkeypatch.setattr(os, "scandir", unexpected_scan)
    response = client.get("/showcase/list/gallery", params={"path": "folder"})
    assert response.status_code == 403


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
