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
    def pixel(image, x, y):
        return image.getpixel((round(x * image.width / 1280), round(y * image.height / 720)))[:3]
    def save(overlays):
        result = json.loads(ops.slide_image_edit({'lecture_id': 'sample', 'slide_id': 's001',
                                                 'overlay_set': overlays}))
        assert result['success'], result
    text = {'text': 'Caption', 'x': 60, 'y': 80, 'color': 'black'}
    save([photo, text])
    with Image.open(folder / 's001.png') as im:
        assert pixel(im, 150, 160) == (255, 0, 0)
        assert pixel(im, 460, 160) == (255, 255, 255)
    saved = ops.lecture_store.read_deck('sample')['slides']['s001']['text_overlays']
    assert saved[0]['src'] == photo['src']
    assert saved[1]['text'] == 'Caption'
    saved[0].update(x=40, width=10)
    save(saved)
    with Image.open(folder / 's001.png') as im:
        assert pixel(im, 150, 160) == (255, 255, 255)
        assert pixel(im, 530, 160) == (255, 0, 0)
        assert pixel(im, 650, 160) == (255, 255, 255)
    meta = ops.lecture_store.read_deck('sample')['slides']['s001']
    Image.new('RGB', (1280, 720), 'blue').save(folder / 's001.png')
    assert ops.reapply_overlays(folder, 's001', meta, folder / 's001.png')
    with Image.open(folder / 's001.png') as im:
        assert pixel(im, 530, 160) == (255, 0, 0)
    save([])
    with Image.open(folder / 's001.png') as im:
        assert pixel(im, 530, 160) == (0, 0, 255)
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


def test_photo_detail_preserved_at_native_pixels_without_cumulative_upscale(editing):
    ops, _, folder, photo = editing
    # 사진의 한 픽셀 선이 저장 뒤에도 분리돼 있어야 한다 (1280 합성에서는 뭉개졌던 입력).
    detail = Image.new('RGB', (1920, 480))
    stripe = Image.new('RGB', (1, 480), 'white')
    for x in range(0, 1920, 2):
        detail.paste(stripe, (x, 0))
    raw = BytesIO()
    detail.save(raw, format='PNG')
    photo.update(src='data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode(),
                 x=0, y=0, width=50)
    for _ in range(2):
        result = json.loads(ops.slide_image_edit({
            'lecture_id': 'sample', 'slide_id': 's001', 'overlay_set': [photo],
        }))
        assert result['success'], result
        with Image.open(folder / 's001.png') as output:
            assert output.size == (3840, 2160)
            assert output.convert('RGB').crop((0, 0, 1920, 480)).tobytes() == detail.tobytes()
        with Image.open(folder / 's001.base.png') as base:
            assert base.size == (1280, 720)
    stored = ops.lecture_store.read_deck('sample')['slides']['s001']['text_overlays'][0]
    assert stored['src'] == photo['src']


def test_large_photo_is_retained_and_output_density_is_bounded(editing):
    _, so, _, photo = editing
    raw = BytesIO()
    Image.new('RGB', (6000, 1000), 'white').save(raw, format='PNG')
    photo['src'] = 'data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode()
    assert so.image_bytes(photo['src']) == raw.getvalue()
    assert so._render_scale([photo], 1280, 720) == 3
    assert so._render_scale([photo], 7680, 4320) == 1  # 큰 배경 자체는 축소하지 않음
    assert so._render_scale([{'text': 'Caption'}], 1280, 720) == 1


def test_pdf_mixed_resolution_retains_pixels_and_page_size(editing, tmp_path):
    import re
    ops, _, folder, _ = editing
    Image.new('RGB', (3840, 2160), 'white').save(folder / 's002.png')
    ops.lecture_store.register_slide('sample', 's002', '고해상도', 'image',
                                     'slides/s002.json', 'slides/s002.png')
    export = importlib.import_module('lecture_export')
    target = tmp_path / 'mixed.pdf'
    assert export.export_pdf('sample', target)['slide_count'] == 2
    data = target.read_bytes()
    boxes = re.findall(rb'/MediaBox\s*\[([^]]+)\]', data)
    assert len(boxes) >= 2
    assert all([float(value) for value in box.split()] == [0, 0, 614.4, 345.6] for box in boxes)
    assert re.search(rb'/Width\s+3840\b', data)
    assert re.search(rb'/Height\s+2160\b', data)
