"""프로그램급 IBL 회귀 배터리 2 (2026-08-22 — 설계 M3·M4·M5).

  M3 오류 처리
    T1. [try]{실패} [catch]{$error.summary 치환} → catch 결과 + _caught 메타
    T2. try 성공 → catch 안 돎, finally 는 돎(결과 불변)
    T3. try·catch 모두 실패 → 두 오류 동봉(덮어쓰기 금지)
    T4. [on_error: skip] — 실패 step 건너뛰고 직전 통화로 계속 + skipped_steps 신고
    T5. [on_error: null] — 빈 items 로 계속
    T6. A ?? (B >> C) 괄호 파이프 가지
  M4 반복
    R1. [repeat: 3, collect: true] — $i 치환·회차 items 이어붙임
    R2. until 이 몸통 할당 $st 를 읽는다(3회차에 done)
    R3. until 미충족 max 도달 → halted:"max"(성공·통화 냄)
    R4. while 바깥 $변수 · 몸통 실패 → success False
    R5. [table:each]{collect: true}
  M5 누적·스필·재개
    D1. [table:reduce] 합·문자열·없는 열·허용 밖 구문
    S1. 자동 스필 — 임계 초과 통화가 참조로 흐르고 $items 바인딩·data-ops _get_items 가 투명하게 읽는다
    S2. 실패 봉투 resume → 그 step 부터 재개(앞 단 재실행 0)
    S3. 스필 GC(24h)

실행: .venv/bin/python3 -m pytest backend/test_ibl_program_grade_m3m5.py
"""
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401

import ibl_engine
import ibl_executors as ex
import ibl_control_blocks as cb
import workflow_engine
from common import spill as spill_mod

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ROWS = {"success": True, "items": [{"title": "a", "n": 1}, {"title": "b", "n": 2}, {"title": "c", "n": 3}]}


def _fake_factory(calls, state, orig=None):
    def _fake(tool_input, project_path, agent_id=None, **kw):
        if tool_input.get("_var_emit") and orig is not None:
            # `$x >> …` 파이프 머리는 엔진의 변수 방출 규약 그대로(가짜 도구가 아니다)
            return orig(tool_input, project_path, agent_id, **kw)
        for key, fn in (("_condition", ex._execute_condition), ("_case", ex._execute_case),
                        ("_try", cb._execute_try), ("_repeat", cb._execute_repeat)):
            if tool_input.get(key):
                return fn(tool_input, project_path, agent_id)
        calls.append(tool_input)
        act = tool_input.get("action")
        p = tool_input.get("params", {}) or {}
        if act == "rows":
            return json.dumps(ROWS)
        if act == "bad":
            return json.dumps({"success": False, "error": "고장: " + str(p.get("why", "x"))}, ensure_ascii=False)
        if act == "boom":
            raise RuntimeError("예외 발생")
        if act == "status":
            state["calls"] = state.get("calls", 0) + 1
            return json.dumps({"success": True, "status": "done" if state["calls"] >= 3 else "running", "n": state["calls"]})
        if act == "each":
            return ex._execute_table_each(dict(p), project_path, agent_id=agent_id)
        if act == "reduce":
            return cb._execute_table_reduce(dict(p), project_path, agent_id=agent_id)
        if act == "big":
            return json.dumps({"items": [{"i": i, "pad": "x" * 100} for i in range(50)]})
        if act == "take":
            prev = p.get("_prev_result")
            obj, err = spill_mod.resolve_ref_str(prev)
            if err:
                return json.dumps({"success": False, "error": err})
            if isinstance(obj, str):
                obj = json.loads(obj) if obj.strip()[:1] in "{[" else {}
            items = obj.get("items") if isinstance(obj, dict) else []
            return json.dumps({"items": items[: int(p.get("n", 1))]})
        return {"success": True, "did": act, "params": {k: v for k, v in p.items() if not k.startswith("_")},
                "prev": p.get("_prev_result")}
    return _fake




def _final(out):
    f = out.get("final_result")
    return json.loads(f) if isinstance(f, str) and f.strip()[:1] in "{[" else f


@pytest.fixture
def tmp_spill(tmp_path, monkeypatch):
    monkeypatch.setattr(spill_mod, "_root", lambda: str(tmp_path / "spill"))
    return tmp_path / "spill"


# ═══ M3 ═══


















# ═══ M4 ═══










# ═══ M5 ═══




def test_s1b_mixed_spill_envelope_preserves_sibling_metadata(tmp_spill):
    """items 참조와 본문 메타를 함께 낸 생산자는 주입 이음매에서 메타를 잃지 않는다."""
    payload = {"items": [{"text": "첫 세그먼트"}, {"text": "둘째 세그먼트"}]}
    env = spill_mod.spill_write(json.dumps(payload, ensure_ascii=False), tag="mixed")
    mixed = {
        **env,
        "saved_to_file": True,
        "file_path": "/tmp/transcript.txt",
        "preview": "자막 앞부분",
        "message": "자막이 길어서 파일로 저장했습니다",
    }

    resolved, err = spill_mod.resolve_ref(mixed)
    assert err is None
    assert resolved["items"] == payload["items"]
    assert resolved["file_path"] == mixed["file_path"]
    assert resolved["preview"] == mixed["preview"]
    assert "ref" not in resolved and "_spilled" not in resolved

    from ibl_v2_compat import plain_arguments
    seen = plain_arguments({'payload':resolved})['payload']
    assert seen['items'] == payload['items']
    assert seen['saved_to_file'] is True and seen['file_path'] == mixed['file_path']


def test_s3_spill_gc(tmp_spill):
    env = spill_mod.spill_write("x" * 10, tag="old")
    old = env["ref"]["path"]
    os.utime(old, (time.time() - 25 * 3600, time.time() - 25 * 3600))
    fresh = spill_mod.spill_write("y", tag="new")["ref"]["path"]
    assert not os.path.exists(old) and os.path.exists(fresh)
    body, err = spill_mod.read_ref(env["ref"])
    assert body is None and "24h" in err


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
