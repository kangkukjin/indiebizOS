"""강의의 사진·글자 배치 저장, 원본 복원, 재렌더와 내보내기 계약."""
import base64
import importlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def editing(tmp_path, monkeypatch):
    package = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/lecture_workspace'
    monkeypatch.syspath_prepend(str(package))
    ops = importlib.import_module('slide_edit_ops')
    so = ops.load_slide_overlay()
    so.FONT_LINK = 'data:text/css,'  # 검사는 외부 웹폰트 서버에 의존하지 않는다.
    monkeypatch.setattr(ops, 'load_slide_overlay', lambda: so)
    root = tmp_path / 'lectures'
    folder = root / 'sample' / 'slides'
    folder.mkdir(parents=True)
    monkeypatch.setattr(ops.lecture_store, 'write_root', lambda: root)
    monkeypatch.setattr(ops.lecture_store, 'search_roots', lambda: [root])
    Image.new('RGB', (1280, 720), 'white').save(folder / 's001.png')
    deck = {'lecture_id': 'sample', 'title': '사진 시험', 'slide_order': ['s001'],
            'slides': {'s001': {'id': 's001', 'layout': 'image', 'png_file': 'slides/s001.png'}}}
    ops.lecture_store.write_deck('sample', deck)
    raw = BytesIO()
    Image.new('RGBA', (200, 100), (255, 0, 0, 255)).save(raw, format='PNG')
    photo = {'kind': 'image', 'text': '', 'name': '사진.png', 'x': 10, 'y': 20, 'width': 25,
             'src': 'data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode()}
    return ops, so, folder, photo


def test_photo_save_reopen_resize_rerender_and_clear(editing):
    ops, _, folder, photo = editing
    def save(overlays):
        result = json.loads(ops.slide_image_edit({'lecture_id': 'sample', 'slide_id': 's001',
                                                 'overlay_set': overlays}))
        assert result['success'], result
    text = {'text': 'Caption', 'x': 60, 'y': 80, 'color': 'black'}
    save([photo, text])
    with Image.open(folder / 's001.png') as im:
        assert im.getpixel((150, 160))[:3] == (255, 0, 0)
        assert im.getpixel((460, 160))[:3] == (255, 255, 255)
    saved = ops.lecture_store.read_deck('sample')['slides']['s001']['text_overlays']
    assert saved[0]['src'] == photo['src']
    assert saved[1]['text'] == 'Caption'
    saved[0].update(x=40, width=10)
    save(saved)
    with Image.open(folder / 's001.png') as im:
        assert im.getpixel((150, 160))[:3] == (255, 255, 255)
        assert im.getpixel((530, 160))[:3] == (255, 0, 0)
        assert im.getpixel((650, 160))[:3] == (255, 255, 255)
    meta = ops.lecture_store.read_deck('sample')['slides']['s001']
    Image.new('RGB', (1280, 720), 'blue').save(folder / 's001.png')
    assert ops.reapply_overlays(folder, 's001', meta, folder / 's001.png')
    with Image.open(folder / 's001.png') as im:
        assert im.getpixel((530, 160))[:3] == (255, 0, 0)
    save([])
    with Image.open(folder / 's001.png') as im:
        assert im.getpixel((530, 160))[:3] == (0, 0, 255)
    assert not (folder / 's001.base.png').exists()


@pytest.mark.parametrize('patch', [
    {'src': 'file:///etc/passwd'}, {'src': 'https://example.com/photo.png'},
    {'src': 'data:image/png;base64,aW52YWxpZA=='}, {'width': 0}, {'x': float('nan')},
])
def test_invalid_photo_preserves_slide(editing, patch):
    ops, _, folder, photo = editing
    before = (folder / 's001.png').read_bytes()
    result = json.loads(ops.slide_image_edit({'lecture_id': 'sample', 'slide_id': 's001',
                                             'overlay_set': [{**photo, **patch}]}))
    assert not result['success']
    assert (folder / 's001.png').read_bytes() == before
    assert not (folder / 's001.base.png').exists()


@pytest.mark.parametrize('layout', ['image', 'hero'])
def test_editable_pptx_keeps_photo_and_text(editing, tmp_path, layout):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    ops, _, folder, photo = editing
    export = importlib.import_module('lecture_export')
    deck = ops.lecture_store.read_deck('sample')
    meta = deck['slides']['s001']
    meta.update(layout=layout, spec_file='slides/s001.json', text_overlays=[photo, {
        'text': 'Caption', 'x': 50, 'y': 60,
    }])
    (folder / 's001.json').write_text(json.dumps({'layout': 'hero', 'title': 'Title'}))
    (folder / 's001.base.png').write_bytes((folder / 's001.png').read_bytes())
    ops.lecture_store.write_deck('sample', deck)
    target = tmp_path / 'result.pptx'
    result = export.export_pptx_editable('sample', target)
    assert result['success']
    shapes = list(Presentation(target).slides[0].shapes)
    pictures = [shape for shape in shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
    photo_shape = pictures[-1]
    assert photo_shape.image.size == (200, 100)
    assert photo_shape.width == 320 * export.PX_TO_EMU
    assert photo_shape.height == 160 * export.PX_TO_EMU
    assert any(shape.has_text_frame and shape.text == 'Caption' for shape in shapes)
