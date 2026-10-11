"""Public warehouse listing and serving must share the same visibility boundary."""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: F401
import portal_warehouse as wh


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    root = tmp_path / 'warehouse'
    for level in range(5):
        (root / str(level)).mkdir(parents=True)
    monkeypatch.setattr(wh, '_WAREHOUSE_ROOT', root)
    monkeypatch.setattr(wh, '_ensure_warehouses', lambda: None)
    monkeypatch.setattr(wh, '_check_secret', lambda secret: None)
    monkeypatch.setattr(wh, '_core', lambda: None)
    monkeypatch.setattr(wh, '_viewer_level', lambda core, request: (
        'test', int(request.headers.get('x-test-level', '0'))))
    app = FastAPI()
    app.add_api_route('/f', wh.node_file, methods=['GET'])
    with TestClient(app) as client:
        yield root, client


def put(root, relative, content='fixture'):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def names(level):
    return {entry['name'] for entry in wh._walk_accessible(level)[0]}


@pytest.mark.parametrize('relative', ['.secret', '.hidden/file.txt', 'folder/.state.json'])
def test_hidden_paths_not_listed_or_downloaded(warehouse, relative):
    root, client = warehouse
    put(root, '0/' + relative, 'private')
    assert relative not in names(0)
    assert client.get('/f', params={'path': relative, 'download': 1}).status_code == 404


@pytest.mark.parametrize('target', ['4/restricted.txt', 'outside/secret.txt'])
def test_cross_level_alias_not_listed_or_served(warehouse, target):
    root, client = warehouse
    secret = put(root, target, 'restricted')
    (root / '0/alias.txt').symlink_to(secret)
    assert 'alias.txt' not in names(0)
    assert client.get('/f', params={'path': 'alias.txt'}).status_code == 404


def test_alias_to_hidden_content_is_not_public(warehouse):
    root, client = warehouse
    hidden = put(root, '0/.hidden/private.txt')
    (root / '0/alias.txt').symlink_to(hidden)
    assert 'alias.txt' not in names(0)
    assert client.get('/f', params={'path': 'alias.txt'}).status_code == 404


def test_level_directory_cannot_alias_another_level(warehouse):
    root, client = warehouse
    put(root, '4/private.txt', 'restricted')
    (root / '0').rmdir()
    (root / '0').symlink_to(root / '4', target_is_directory=True)
    assert 'private.txt' not in names(0)
    assert client.get('/f', params={'path': 'private.txt'}).status_code == 404


def test_dangling_and_looping_aliases_are_not_public(warehouse):
    root, client = warehouse
    (root / '0/dangling').symlink_to(root / '0/missing')
    (root / '0/loop').symlink_to(root / '0/loop')
    put(root, '0/valid.txt', 'still visible')
    assert names(0) == {'valid.txt'}
    for path in ('dangling', 'loop'):
        assert client.get('/f', params={'path': path}).status_code == 404


def test_same_level_public_alias_and_unicode_download(warehouse):
    root, client = warehouse
    target = put(root, '0/자료/본문 한글.txt', '원문\n')
    (root / '0/별칭.txt').symlink_to(target)
    assert '별칭.txt' in names(0)
    response = client.get('/f', params={'path': '별칭.txt', 'download': 1})
    assert response.status_code == 200
    assert response.content == target.read_bytes()
    assert 'attachment' in response.headers['content-disposition']


def test_rejected_high_alias_preserves_lower_public_file(warehouse):
    root, client = warehouse
    put(root, '0/common.txt', 'public')
    private = put(root, '4/private.txt', 'restricted')
    (root / '2/common.txt').symlink_to(private)
    listing = {r['name']: r for r in wh._walk_accessible(2)[0]}
    assert listing['common.txt']['bytes'] == len(b'public')
    response = client.get('/f', params={'path': 'common.txt'}, headers={'x-test-level': '2'})
    assert response.status_code == 200
    assert response.content == b'public'


@pytest.mark.parametrize('level', range(5))
def test_highest_authorized_version_and_upper_level_404(warehouse, level):
    root, client = warehouse
    for lv in range(5):
        put(root, f'{lv}/common.txt', f'version-{lv}')
    put(root, '4/upper.txt', 'top')
    headers = {'x-test-level': str(level)}
    assert client.get('/f', params={'path': 'common.txt'}, headers=headers).text == f'version-{level}'
    assert client.get('/f', params={'path': 'upper.txt'}, headers=headers).status_code == (200 if level == 4 else 404)
    assert ('upper.txt' in names(level)) == (level == 4)


def test_traversal_does_not_escape_and_raw_html_is_not_rewritten(warehouse):
    root, client = warehouse
    put(root, 'secret.txt', 'outside')
    assert client.get('/f', params={'path': '../secret.txt'}).status_code in (400, 404)
    raw = '<html><a href="child.txt">원문</a></html>'
    put(root, '0/folder/index.html', raw)
    assert client.get('/f', params={'path': 'folder/index.html'}).content == raw.encode()
    assert client.get('/child.txt').status_code == 404


def test_owner_management_keeps_hidden_path_access_and_path_guard(warehouse):
    from fastapi import HTTPException
    import portal_admin

    root, _ = warehouse
    path = put(root, '0/.metadata.json', '{}')
    assert portal_admin._safe_rel(root / '0', '.metadata.json') == path
    with pytest.raises(HTTPException) as error:
        portal_admin._safe_rel(root / '0', '../outside')
    assert error.value.status_code == 400


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
