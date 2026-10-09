"""Fixed template titles and returned metadata must describe the saved deck."""
import importlib.util
import json
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def template_module():
    spec = importlib.util.spec_from_file_location(
        "slide_template_test_module", ROOT / "data/scripts/슬라이드틀적용.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_conflicting_title_slot_cannot_diverge_from_deck_title(template_module):
    with pytest.raises(ValueError, match="title"):
        template_module.specs('<h1>{{title}}</h1>', [
            {"id": "s001", "title": "확정 제목", "fields": {"title": "다른 화면 제목"}}])


def test_exact_title_escaping_and_explicit_visual_html(template_module):
    result = template_module.specs('<h1>{{title}}</h1>{{visual_html}}', [
        {"id": "s001", "title": '<확정 & 제목>',
         "fields": {"title": '<확정 & 제목>', "visual_html": '<svg></svg>'}}])
    assert result[0][1]["custom_html"] == '<h1>&lt;확정 &amp; 제목&gt;</h1><svg></svg>'


def test_apply_reports_actual_saved_metadata_including_reuse(template_module, tmp_path, monkeypatch):
    mod = template_module
    directory = tmp_path / "fixture"
    directory.mkdir()
    (directory / 'deck.json').write_text(json.dumps({
        "lecture_id": "fixture", "slide_order": [], "slides": {}, "design_system": "vintage_book"}))
    template = tmp_path / "template.html"
    template.write_text('<h1>{{title}}</h1>')
    contents = tmp_path / "contents.json"
    contents.write_text(json.dumps([{"id": "s001", "title": "정확한 제목", "speaker_note": "원고"}]))
    monkeypatch.setattr(mod.lecture_store, 'set_roots', lambda *a: None)
    monkeypatch.setattr(mod.lecture_store, 'write_root', lambda: tmp_path)
    monkeypatch.setattr(mod.lecture_store, 'search_roots', lambda: [tmp_path])

    def render(spec, tone, target, sid):
        (target / f'{sid}.png').write_bytes(b'fixture pixels')
        (target / f'{sid}.json').write_text(json.dumps(spec))

    monkeypatch.setattr(mod.slide_ai, 'render_slide_to_files', render)
    args = {"lecture_id": "fixture", "lecture_dir": str(directory),
            "template_path": str(template), "contents_path": str(contents)}
    first = mod.apply(args)["items"][0]
    assert first['title'] == '정확한 제목' and first['speaker_note'] == '원고'
    assert first['reused'] is False
    # The saved deck can have user edits; never report the request as the actual result.
    p = directory / 'deck.json'
    deck = json.loads(p.read_text())
    deck['slides']['s001'].update(title='사용자 수정', speaker_note='보존할 사용자 노트')
    p.write_text(json.dumps(deck))
    second = mod.apply(args)['items'][0]
    assert second['reused'] is True
    assert second['title'] == '사용자 수정'
    assert second['speaker_note'] == '보존할 사용자 노트'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
