"""봉투 다이어트의 부분 실패 다이제스트 가드 — E1~E4.

2026-08-28 팁 보고서 완성 프로그램 실측: `[table:each]` 부분 실패(1/4 자막 실패)의
`errors[]` 배열이 다문장 요약에서 통째로 접히면서 message 는 "errors 참조"를
가리켰다 — 참조 대상이 요약에 없어 어느 행이 왜 실패했는지 회수 불능(침묵 모순).
수리 = summarize_result 가 errors 를 다이제스트(상한 3건·건당 300자)로 나른다.
모듈 원칙("진단 정보는 다이어트 대상이 아님")의 집행이다.

수리 전 코드에서 E1·E2·E4 가 빨강이어야 한다.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

from ibl.ibl_envelope import summarize_result  # noqa: E402


def _each_envelope(n_errors=1, items=None):
    env = {
        "success": True,
        "items": items if items is not None else [{"tip": "팁", "video_id": "ok1"}],
        "error_count": n_errors,
        "errors": [{"video_id": f"bad{i}", "_error": "자막이 없습니다"} for i in range(n_errors)],
        "message": f"{n_errors}/4건 실패 — errors 참조",
    }
    return json.dumps(env, ensure_ascii=False)


def test_E1_errors_digest_carried():
    out = summarize_result(_each_envelope())
    assert out["shape"] == "items"
    assert out["error_count"] == 1
    assert isinstance(out.get("errors_digest"), list) and len(out["errors_digest"]) == 1
    assert "bad0" in out["errors_digest"][0]
    assert "자막이 없습니다" in out["errors_digest"][0]


def test_E2_digest_capped_and_reported():
    out = summarize_result(_each_envelope(n_errors=5))
    assert len(out["errors_digest"]) == 3
    assert out["errors_digest_truncated"] == 2
    assert out["error_count"] == 5


def test_E3_no_errors_no_digest():
    env = json.dumps({"success": True, "items": [{"a": 1}]}, ensure_ascii=False)
    out = summarize_result(env)
    assert "errors_digest" not in out
    assert "error_count" not in out


def test_E4_effect_shape_also_carries():
    """items 아닌 봉투(효과형)의 부분 실패도 접히지 않는다."""
    env = json.dumps({"success": True, "path": "/tmp/x",
                      "errors": [{"row": 3, "_error": "쓰기 거절"}]}, ensure_ascii=False)
    out = summarize_result(env)
    assert out.get("errors_digest") and "쓰기 거절" in out["errors_digest"][0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
