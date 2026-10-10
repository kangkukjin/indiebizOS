"""공통 채팅 첨부 업로드와 원문 보존의 운반 계약."""
import boot_paths  # noqa: F401
import pytest


@pytest.mark.parametrize('name', ['보고서.docx', '메모.pages', '설정.json', 'code.py', '표.csv'])
def test_chat_attachment_types_upload_without_changing_bytes(tmp_path, monkeypatch, name):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_launcher_web
    monkeypatch.setattr(api_launcher_web, '_UPLOAD_DIR', str(tmp_path))
    app = FastAPI(); app.include_router(api_launcher_web.router)
    raw = b'original bytes for transport'
    with TestClient(app) as client:
        result = client.post('/launcher/upload', params={'name':name}, content=raw)
    assert result.status_code == 200
    from pathlib import Path
    assert Path(result.json()['path']).read_bytes() == raw


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
