"""추가 관용구 3개: AI 없는 본문, 결과·실패 보존, 상시 노출 계약."""
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from idiom_experiment_cases import decoded

CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
NEW = {'미처리만고르기', '묶어순위내기', '주소마다읽기'}
# 이 선정집에서 실측한 비-AI 원시의 닫힌 집합. 동적 fn/script/AI 술어는 인증하지 않는다.
LEAVES = {'table:dedup', 'table:join', 'table:groupby', 'table:sort',
          'table:take', 'table:each', 'sense:crawl'}
# 스크립트는 일반 인증하지 않는다. 예외는 판정관용구의 모델 없는 두 op 뿐(3ded991b):
# urls(주소 문자열 그대로 중복 제거)·finish(실패·잘림 합산). 판정 op(prepare·select)는 불허.
SCRIPT_CALL = re.compile(r'\[self:script\]\{op:"run",id:"([^"]+)",args:\{op:"([a-z_]+)"')
PURE_SCRIPT_OPS = {('판정관용구', 'urls'), ('판정관용구', 'finish')}




















def test_crawl_handler_converts_raw_paragraphs_without_model_call(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from test_report_repair_contracts_2026_09_08 import load
    from tool_context import ToolContext
    import consciousness_agent
    import oneshot_facade
    def forbidden(*args, **kwargs):
        pytest.fail('원문 수집 경로가 모델을 호출했다')
    monkeypatch.setattr(consciousness_agent, 'oneshot_ai_call', forbidden)
    monkeypatch.setattr(oneshot_facade, 'execution_oneshot', forbidden)
    handler = load('_idiom_raw_web', ROOT / 'data/packages/installed/tools/web/handler.py')
    original_loader = handler.load_module
    crawler = SimpleNamespace(crawl_website=lambda url, max_length, **kwargs:
                              {'success': True, 'title': '제목', 'text': '첫 문단\n\n둘째 문단'})
    monkeypatch.setattr(handler, 'load_module', lambda name:
                        crawler if name == 'tool_webcrawl' else original_loader(name))
    result = decoded(handler.execute({'url': 'https://fixture.test/a'}, ToolContext(str(tmp_path), 'crawl_website')))
    assert result['items'] == [{'type': 'heading', 'level': 1, 'text': '제목'},
                               {'type': 'paragraph', 'text': '첫 문단'}, {'type': 'paragraph', 'text': '둘째 문단'}]




def test_explicit_reload_invalidates_idiom_map_and_leaf_lines(monkeypatch):
    import ibl_access
    import node_registry
    monkeypatch.setattr(node_registry, 'invalidate_node_cache', lambda: None)
    monkeypatch.setattr(ibl_access, '_idioms_cache',
                        {'text': '옛 지도', 't': 9999999999, 'key': None, 'anchors': {'self:read': ['옛 이름']}})
    ibl_access.invalidate_nodes_cache()
    assert ibl_access._idioms_cache['text'] is None
    assert ibl_access._idioms_cache['anchors'] == {}


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
