"""HTML form containers preserve prose regardless of its length."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path
import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audited_webcrawl_body', ROOT / 'data/packages/installed/tools/web/webcrawl_body.py')
body = importlib.util.module_from_spec(spec)
spec.loader.exec_module(body)

@pytest.mark.parametrize('count', [1, 20, 399, 999, 1000, 1001])
def test_form_preserves_short_and_long_declared_body(count):
    text = '가' * count
    html = f'<body><form><main><p>{text}</p></main><input value="secret"><button>검색</button></form></body>'
    container = body.reading_container(BeautifulSoup(html, 'html.parser'))
    assert container.get_text() == text


def test_form_preserves_undeclared_prose_and_drops_only_controls():
    html = '<body><form><p>짧은 공지입니다.</p><select><option>옵션</option></select><textarea>입력값</textarea></form></body>'
    assert body.reading_container(BeautifulSoup(html, 'html.parser')).get_text() == '짧은 공지입니다.'

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
