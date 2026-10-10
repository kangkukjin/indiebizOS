"""Engine errors retain actionable distinctions at the conversion boundary."""
import boot_paths  # noqa: F401
import pytest
import document_formats
from document_pages import ImportFailure
from document_workspace import DocumentWorkspace


@pytest.mark.parametrize('engine_code,expected', [
    (-5, 'password_required'), (-10, 'input_too_large'),
    (-2, 'conversion_timeout'), (-3, 'conversion_failed'),
])
def test_conversion_error_codes(tmp_path, monkeypatch, engine_code, expected):
    app = DocumentWorkspace(tmp_path / 'state')
    cfg = {'url': 'http://127.0.0.1:8093', 'callback_origin': 'http://127.0.0.1:8765',
           'secret': 'synthetic-test-secret'}
    monkeypatch.setattr(document_formats, 'settings', lambda: cfg)
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {'error': engine_code}
    monkeypatch.setattr(document_formats.httpx, 'post', lambda *a, **k: Response())
    with pytest.raises(ImportFailure) as error:
        document_formats.convert_bytes(app, 'synthetic', b'input', 'pages', 'docx', 'test')
    assert error.value.code == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
