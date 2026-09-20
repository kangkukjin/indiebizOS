"""동일한 타입 바인딩 화면을 데스크탑·웹·회원 앱에 제공한다."""
from pathlib import Path


def page(csrf):
    import json
    source = (Path(__file__).resolve().parents[1] / 'static' / 'record_app.html').read_text(encoding='utf-8')
    return source.replace('__RECORD_CSRF__', json.dumps(csrf))
