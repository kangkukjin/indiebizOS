"""최근 세 보고서의 미수리 결함 — 외부 API·모델 비용 없는 실행 회귀."""
import importlib.util
import json
from pathlib import Path
import uuid

import boot_paths  # noqa: F401
import workflow_store  # 시험 대역도 저장소 소유자에 설치한다.
import pytest

from system_tools import _execute_ibl_unified
from thread_context import actor_context


@pytest.fixture
def run(tmp_path, monkeypatch):
    import ibl_turn_vars
    monkeypatch.setattr(ibl_turn_vars, "store_path", lambda key: str(tmp_path / f"{key}.json"))
    task = f"task_test_{uuid.uuid4().hex}"

    def execute(code, **extra):
        with actor_context(agent_id="probe", task_id=task):
            raw = _execute_ibl_unified({"code": code,"edition":2,"verbose": True,**extra}, str(tmp_path), agent_id="probe")
        return json.loads(raw)

    return execute







def _package_module(filename):
    path = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/real-estate" / filename
    spec = importlib.util.spec_from_file_location("episode_audit_" + path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 2026-09-09 /api/search 실측: 색장동이 먼저, 정확한 장동은 두 번째였다.
REGIONS = [
    {"cortarNo": "5211114400", "cortarName": "전북도 전주시 완산구 색장동"},
    {"cortarNo": "5211313200", "cortarName": "전북도 전주시 덕진구 장동"},
]


@pytest.fixture
def naver(monkeypatch):
    mod = _package_module("tool_naver.py")
    monkeypatch.setattr(mod, "has_curl_cffi", lambda: True)
    return mod


@pytest.mark.parametrize("query", ["전주 장동", "전주시 장동", "전주 덕진구 장동", "장동"])
def test_naver_selects_exact_dong_regardless_of_search_rank(naver, monkeypatch, query):
    requested = []

    def api(path, params):
        if path == "/api/search":
            return {"regions": REGIONS}
        requested.append(params["cortarNo"])
        return {"articleList": []}

    monkeypatch.setattr(naver, "_api_get", api)
    out = naver.get_naver_listings({"region": query})
    assert out["success"] and out["조회지역"] == REGIONS[1]["cortarName"]
    assert requested == ["5211313200"]


@pytest.mark.parametrize("regions", [REGIONS[:1], REGIONS + [
    {"cortarNo": "other", "cortarName": "전북도 전주시 다른구 장동"},
]])
def test_naver_rejects_wrong_or_ambiguous_regions_before_fetching(naver, monkeypatch, regions):
    def api(path, params):
        assert path == "/api/search", "모호한 위치로 매물을 조회하면 안 된다"
        return {"regions": regions}

    monkeypatch.setattr(naver, "_api_get", api)
    out = naver.get_naver_listings({"region": "전주 장동"})
    assert out["success"] is False and "검색 후보:" in out["error"]
    assert "count" not in out, "잘못된 위치를 0건으로 신고하면 안 된다"


def test_naver_complex_search_still_resolves(naver, monkeypatch):
    monkeypatch.setattr(naver, "_api_get", lambda *a: {"complexes": [
        {"complexNo": "123", "complexName": "시험아파트"},
    ]})
    loc = naver._resolve_keyword("시험아파트")
    assert loc["mode"] == "complex" and loc["complexNo"] == "123"






if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
