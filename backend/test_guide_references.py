"""정확 참조와 빌드 가드는 같은 문서를 해소해야 한다."""
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
import guide_registry as gr
import ibl_routing as routing

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from iblbuild_guide_wiring import validate_guide_wiring, markdown_references


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    guides = data / 'guides'
    guides.mkdir(parents=True)
    (guides / 'main.md').write_text('# Main\n\n## Detail\nbody\n[reference](extra.md#section)\n')
    (guides / 'extra.md').write_text('# Reference\n')
    entries = [{'id': 'main', 'name': 'Main', 'file': 'main.md',
                'description': 'main', 'aliases': ['old.md'], 'keywords': []}]
    (data / 'guide_db.json').write_text(json.dumps({'guides': entries}))
    monkeypatch.setattr(routing, '__file__', str(tmp_path / 'backend/ibl/ibl_routing.py'))
    return tmp_path, guides, entries


def test_unregistered_and_alias(catalog):
    root, guides, entries = catalog
    assert routing._search_guide('extra.md', {})['content'] == '# Reference\n'
    assert routing._search_guide('extra.md', {})['registered'] is False
    (guides / 'old.md').write_text('old stub')
    assert routing._search_guide('old.md', {})['file'] == 'main.md'
    assert 'content' not in routing._search_guide('extra.md', {'read': False})
    assert routing._search_guide('missing.md', {})['error_code'] == 'GUIDE_NOT_FOUND'
    assert not validate_guide_wiring(root)


@pytest.mark.parametrize('name', ['../extra.md', '/extra.md', 'sub/extra.md', 'sub\\extra.md', 'EXTRA.md'])
def test_no_escape_or_case_repair(catalog, name):
    assert routing._search_guide(name, {})['error_code'] == 'GUIDE_NOT_FOUND'


def test_symlink_collision_and_missing_target(catalog, tmp_path):
    root, guides, entries = catalog
    outside = tmp_path / 'private.md'
    outside.write_text('private')
    (guides / 'escape.md').symlink_to(outside)
    assert routing._search_guide('escape.md', {})['error_code'] == 'GUIDE_NOT_FOUND'
    entries.append({'id': 'extra', 'file': 'extra.md', 'aliases': ['old.md']})
    assert gr.resolve_guide_reference('old.md', entries, guides)['error_code'] == 'GUIDE_REFERENCE_AMBIGUOUS'
    (guides / 'main.md').unlink()
    assert gr.resolve_guide_reference('main.md', entries, guides)['error_code'] == 'GUIDE_TARGET_MISSING'


def test_link_guard_and_fenced_examples(catalog):
    root, guides, _ = catalog
    source = '[ok](extra.md#x)\n```md\n[example](missing.md)\n```\n[web](https://example.org/a.md)\n'
    assert markdown_references(source) == ['extra.md']
    (guides / 'main.md').write_text(source)
    assert not validate_guide_wiring(root)
    (guides / 'extra.md').unlink()
    assert any('extra.md' in issue for issue in validate_guide_wiring(root))


def test_corrupt_catalog(catalog):
    (catalog[0] / 'data/guide_db.json').write_text('{')
    assert routing._search_guide('extra.md', {})['error_code'] == 'GUIDE_CATALOG_INVALID'


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
