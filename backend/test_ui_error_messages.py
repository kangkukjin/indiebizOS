"""Structured UI errors preserve their Korean fallback and raw OS parameters."""
import boot_paths
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api_pcmanager


def test_directory_errors_have_registered_codes(tmp_path, monkeypatch):
    messages = json.loads((Path(__file__).parents[1] / 'frontend/i18n/system-messages.json').read_text())
    app = FastAPI()
    app.include_router(api_pcmanager.router)
    with TestClient(app) as client:
        missing = client.get('/pcmanager/list', params={'path': str(tmp_path / '없는 경로')})
        assert missing.status_code == 404
        body = missing.json()
        assert body['detail'] == '경로를 찾을 수 없습니다'
        assert body['ui_message']['code'] == 'ui.path.missing'
        assert messages[body['ui_message']['code']]['source'] == body['detail']
        file = tmp_path / '한글 파일'
        file.write_text('content')
        not_directory = client.get('/pcmanager/list', params={'path': str(file)})
        assert not_directory.json()['ui_message']['code'] == 'ui.path.not_directory'
        parameter = '공유 폴더 <tag> $&'
        def denied(_path):
            raise OSError(parameter)
        monkeypatch.setattr(api_pcmanager.os, 'scandir', denied)
        failed = client.get('/pcmanager/list', params={'path': str(tmp_path)})
        assert failed.status_code == 502
        message = failed.json()['ui_message']
        assert message['params'] == [parameter]
        assert message['message'] == failed.json()['detail']
        assert messages[message['code']]['source'].format(parameter) == message['message']


def test_directory_data_is_never_translated(tmp_path):
    (tmp_path / '문서').write_text('hello')
    result = api_pcmanager.list_directory(str(tmp_path))
    assert result['items'][0]['name'] == '문서'
    assert result['items'][0]['path'] == str(tmp_path / '문서')
    assert isinstance(result['items'][0]['modified'], (int, float))


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + __import__("sys").argv[1:]))
