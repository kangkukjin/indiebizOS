"""강의 앱의 빈 HTML 슬라이드 생성 계약 (임시 강의만 사용)."""
import importlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    import api_lecture_workspace as api
    package = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/lecture_workspace'
    monkeypatch.syspath_prepend(str(package))
    store = importlib.import_module('lecture_store')
    slide_ai = importlib.import_module('slide_ai')
    root = tmp_path / 'lectures'
    monkeypatch.setattr(store, 'write_root', lambda: root)
    monkeypatch.setattr(store, 'search_roots', lambda: [root])
    monkeypatch.setattr(api, '_load_lecture_store', lambda: store)
    monkeypatch.setattr(api, '_load_slide_ai', lambda: slide_ai)
    monkeypatch.setattr(slide_ai, '_get_slide_ai', lambda: pytest.fail('빈 슬라이드는 AI를 호출하면 안 됨'))
    deck = store.create_lecture(title='빈 페이지 시험', design_system='native_vintage_book')
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        yield client, store, slide_ai, deck['lecture_id']


def assert_white(path):
    with Image.open(path) as image:
        assert image.size == (1280, 720)
        assert image.convert('RGB').getextrema() == ((255, 255),) * 3


def test_blank_slide_append_insert_and_overlay(workspace):
    client, store, _, lecture_id = workspace
    url = f'/lectures/{lecture_id}/slides/blank'
    first = client.post(url, json={})
    assert first.status_code == 200, first.text
    a = first.json()
    assert a['layout'] == 'custom'
    folder = store.lecture_dir(lecture_id)
    assert_white(folder / a['png_file'])
    spec = json.loads((folder / a['spec_file']).read_text())
    assert spec['layout'] == 'custom' and not spec.get('title')
    html = (folder / 'slides' / f"{a['id']}.html").read_text()
    assert spec['custom_html'] in html
    assert '빈 슬라이드' not in html  # 목록용 이름이 화면에 찍히지 않는다.
    b = client.post(url, json={'insert_at': 0}).json()
    assert b['id'] != a['id']
    assert store.read_deck(lecture_id)['slide_order'] == [b['id'], a['id']]
    ops = importlib.import_module('slide_edit_ops')
    result = json.loads(ops.slide_image_edit({
        'lecture_id': lecture_id, 'slide_id': a['id'],
        'overlay_set': [{'text': '내가 넣은 글자', 'x': 20, 'y': 30, 'color': 'black'}],
    }))
    assert result['success'], result
    # 덱의 이미지 렌더 기본값과 무관하게 HTML 재렌더 후에도 글자가 유지된다.
    rerender = client.post(f"/lectures/{lecture_id}/slides/{a['id']}/rerender")
    assert rerender.status_code == 200, rerender.text
    assert_white(folder / 'slides' / f"{a['id']}.base.png")
    clear = json.loads(ops.slide_image_edit({
        'lecture_id': lecture_id, 'slide_id': a['id'], 'overlay_set': [],
    }))
    assert clear['success']
    assert_white(folder / a['png_file'])


def test_blank_missing_lecture_returns_404(workspace):
    client, _, _, _ = workspace
    assert client.post('/lectures/missing/slides/blank', json={}).status_code == 404


def test_blank_render_failure_does_not_register(workspace, monkeypatch):
    client, store, slide_ai, lecture_id = workspace
    def fail(**kwargs):
        raise RuntimeError('render failed')
    monkeypatch.setattr(slide_ai, 'render_slide_to_files', fail)
    with pytest.raises(RuntimeError, match='render failed'):
        client.post(f'/lectures/{lecture_id}/slides/blank', json={})
    assert store.read_deck(lecture_id)['slide_order'] == []
