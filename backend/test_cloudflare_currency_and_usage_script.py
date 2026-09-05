"""ep2833 관찰 수리 3종 (2026-09-05).

  ① 병렬 분기 실패의 error 가 빈 문자열 — Cloudflare API 봉투는 사유를 `errors[]` 에 싣는데 핸들러가
     최상위 `error` 를 안 채웠고, 사유 추출기(err_reason_of)도 errors[] 를 몰랐다. 둘 다 고친다.
  ② `[limbs:cloudflare_api]` 가 result 를 통화(items)로 방출하지 않아 `[table:each]` 가 원 행만 흘렸다.
  ③ Cloudflare 사용량(R2 저장·작업, Workers 요청 vs 무료 한도) 등록 스크립트 — 임시 파이썬 셋을 얼림.

실행: .venv/bin/python -m pytest -q backend/test_cloudflare_currency_and_usage_script.py
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: E402,F401

_REPO = Path(__file__).resolve().parent.parent
_API = _REPO / "data" / "packages" / "installed" / "tools" / "cloudflare" / "tools" / "api.py"
_SCRIPT = _REPO / "data" / "scripts" / "Cloudflare사용량.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, data, status=200, ok=True):
        self._d, self.status_code, self.ok, self.text = data, status, ok, json.dumps(data)

    def json(self):
        return self._d


def test_cloudflare_failure_carries_error_string(monkeypatch):
    api = _load("_t_cf_api", _API)
    monkeypatch.setattr(api.requests, "request",
                        lambda **kw: _Resp({"success": False, "errors": [{"code": 10000, "message": "Authentication error"}],
                                            "result": None}, 403, False))
    out = api.run({"endpoint": "/accounts/x/subscriptions"}, {"api_token": "t", "account_id": "x"})
    assert out["success"] is False
    assert "10000" in out["error"] and "Authentication error" in out["error"]


def test_cloudflare_result_is_emitted_as_items(monkeypatch):
    api = _load("_t_cf_api2", _API)
    buckets = [{"name": "a", "creation_date": "2026-01-01"}, {"name": "b", "creation_date": "2026-02-01"}]
    monkeypatch.setattr(api.requests, "request",
                        lambda **kw: _Resp({"success": True, "errors": [], "result": {"buckets": buckets}}))
    out = api.run({"endpoint": "/accounts/x/r2/buckets"}, {"api_token": "t", "account_id": "x"})
    assert out["success"] is True and out["result"] == {"buckets": buckets}
    assert out["items"] == [{"buckets": buckets}]          # dict result = 1행
    monkeypatch.setattr(api.requests, "request",
                        lambda **kw: _Resp({"success": True, "errors": [], "result": buckets}))
    out = api.run({"endpoint": "/accounts/x/workers/scripts"}, {"api_token": "t", "account_id": "x"})
    assert out["items"] == buckets                          # list result = 행들


def test_err_reason_reads_errors_list():
    from workflow_verdict import err_reason_of
    assert err_reason_of({"success": False, "errors": [{"code": 7003, "message": "no route"}]}) == "7003: no route"
    assert err_reason_of({"success": False, "error": "", "errors": ["boom"]}) == "boom"
    assert err_reason_of({"success": False, "error": "직접 사유", "errors": ["boom"]}) == "직접 사유"


def test_usage_script_aggregates_against_free_limits():
    m = _load("_t_cf_usage", _SCRIPT)
    st = m.aggregate_r2_storage([
        {"dimensions": {"date": "2026-09-04", "bucketName": "pf"}, "max": {"objectCount": 100, "payloadSize": 3e9, "metadataSize": 1e6}},
        {"dimensions": {"date": "2026-09-05", "bucketName": "pf"}, "max": {"objectCount": 120, "payloadSize": 4e9, "metadataSize": 0}},
        {"dimensions": {"date": "2026-09-05", "bucketName": "x"}, "max": {"objectCount": 1, "payloadSize": 1e9, "metadataSize": 0}},
    ])
    by = {r["bucket"]: r for r in st}
    assert by["pf"]["date"] == "2026-09-05" and by["pf"]["gb"] == 4.0 and by["pf"]["pct_of_free"] == 40.0
    assert by["(전체)"]["gb"] == 5.0 and by["(전체)"]["objects"] == 121
    ops = m.aggregate_r2_ops([{"dimensions": {"actionType": "PutObject"}, "sum": {"requests": 1000}},
                              {"dimensions": {"actionType": "GetObject"}, "sum": {"requests": 50000}}])
    assert {r["class"]: r["month_requests"] for r in ops} == {"A": 1000, "B": 50000}
    wk = m.aggregate_workers([
        {"dimensions": {"scriptName": "public-files", "date": "2026-08-28"}, "sum": {"requests": 5824, "errors": 0}},
        {"dimensions": {"scriptName": "public-files", "date": "2026-08-29"}, "sum": {"requests": 100, "errors": 1}},
        {"dimensions": {"scriptName": "diary", "date": "2026-08-28"}, "sum": {"requests": 10, "errors": 0}},
    ])
    byw = {r["script"]: r for r in wk}
    assert byw["public-files"]["max_day"] == "2026-08-28" and byw["public-files"]["pct_of_free_max_day"] == 5.82
    assert byw["(전체)"]["max_day_requests"] == 5834 and byw["(전체)"]["errors"] == 1
    msg = m.summarize(st + ops + wk)
    assert "R2 저장 5.0GB" in msg and "Class A 1,000" in msg and "Workers 최대 일요청 5,834" in msg


def test_usage_script_is_registered():
    import yaml
    reg = yaml.safe_load((_REPO / "data" / "scripts" / "registry.yaml").read_text(encoding="utf-8"))
    assert "Cloudflare사용량" in reg and reg["Cloudflare사용량"]["file"] == "Cloudflare사용량.py"


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
