"""[table:ai] 색인 병합 계약 (2026-09-06, ep2882 실측: 출력의 76% 가 입력 echo).

모델은 행마다 `{_i, 새로 만들거나 바꾼 필드}` 만 돌려주고 코드가 원 행에 병합한다. 값 보존·순서=반환 순서·
뺀 _i=제거(rows_dropped 신고)·_i 없는 행=신규. 계약을 어긴 반환(_i 전무)은 옛 계약(전체 행)으로 정직 폴백
+ `_merge:"full"`.

실행: .venv/bin/python -m pytest -q backend/test_table_ai_index_merge_2026_09_06.py
"""
import importlib.util
import json
import os
from pathlib import Path

import oneshot_facade as _fac

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load("_t_aiops_index_merge", os.path.join(_PKG, "ai-ops", "handler.py"))


class _Ctx:
    tool_name = "ai_transform"


ITEMS = [{"title": "t0", "url": "u0"}, {"title": "t1", "url": "u1"}, {"title": "t2", "url": "u2"}]


def _run(reply, **params):
    calls = []

    def fake(prompt, system_prompt=None, images=None, role="execution"):
        calls.append((prompt, system_prompt))
        return json.dumps(reply, ensure_ascii=False)
    old = _fac.execution_oneshot
    _fac.execution_oneshot = fake
    try:
        out = json.loads(M.execute({"instruction": "라벨", "_prev_result": json.dumps({"items": ITEMS}), **params}, _Ctx()))
    finally:
        _fac.execution_oneshot = old
    return out, calls


def test_index_merge_keeps_input_fields_and_applies_changes():
    out, calls = _run([{"_i": 0, "label": "NEW", "delta": "d0"}, {"_i": 2, "label": "OLD", "title": "바뀜"}],
                      fields=["label", "title", "url", "delta"])
    assert out["success"] and out["_merge"] == "index"
    assert out["items"][0] == {"label": "NEW", "title": "t0", "url": "u0", "delta": "d0", "_ai": True}
    assert out["items"][1]["title"] == "바뀜" and out["items"][1]["url"] == "u2"   # 값 수정 통로 + 보존
    assert out["rows_in"] == 3 and out["rows_out"] == 2 and out["rows_dropped"] == 1
    assert not any("_i" in r for r in out["items"])
    prompt, system = calls[0]
    assert '"_i": 0' in prompt and "색인 _i" in system and "다시 쓰지 말 것" in system


def test_new_row_without_index_and_out_of_range_index():
    out, _ = _run([{"_i": 1, "label": "A"}, {"label": "신규", "title": "n"}, {"_i": 9, "label": "?"}])
    assert out["_merge"] == "index" and out["rows_out"] == 3
    assert out["items"][0]["title"] == "t1" and out["items"][1]["title"] == "n"
    assert "9" in out.get("note", "")


def test_full_rows_fallback_when_model_ignores_contract():
    out, _ = _run([{"title": "x", "url": "y", "label": "L"}])
    assert out["_merge"] == "full" and out["rows_out"] == 1 and out["rows_dropped"] == 2
    assert out["items"][0]["title"] == "x"


def test_zero_rows_skip_call_unchanged():
    old = _fac.execution_oneshot
    _fac.execution_oneshot = lambda *a, **k: (_ for _ in ()).throw(AssertionError("호출 금지"))
    try:
        out = json.loads(M.execute({"instruction": "x", "_prev_result": json.dumps({"items": []})}, _Ctx()))
    finally:
        _fac.execution_oneshot = old
    assert out["success"] and out["rows_in"] == 0


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
