"""쓰기 관문 원장 배터리 (2026-08-21 신설 — 몸 원장 기둥 ③)

    T1. 기본 기록 — 한 줄 JSONL, 필드 완전
    T2. 행위자 전파 — thread_context 의 agent/task/origin 이 실린다
    T3. 자기지시 차단 — 원장 자신의 쓰기는 기록하지 않는다
    T4. 로테이션 — 상한 초과 시 .1 로 1세대
    T5. 절대 무해 — 기록 실패가 예외를 내지 않는다(본 쓰기 보호)
    T6. safe_store 관문 통합 — safe_save_json 이 원장 한 줄을 남긴다
    T7. [self:body]{op:"writes"} — 기간·스코프 필터, 부분성 정직 광고, 빈 원장 정직

실행: python3 backend/test_write_ledger.py
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

import thread_context as tc  # noqa: E402
import write_ledger as wl  # noqa: E402

_BODY_OPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data",
                         "packages", "installed", "tools", "system_essentials", "body_ops.py")


def _read_lines(p):
    try:
        return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return []


def test_t1_basic(tmp):
    wl.log_write(tmp["root"] / "data" / "foo.json", event="write", gate="safe_store", size=7)
    rows = _read_lines(tmp["ledger"])
    assert len(rows) == 1
    r = rows[0]
    assert r["path"] == "data/foo.json" and r["gate"] == "safe_store" and r["size"] == 7
    assert r["ts"][:4].isdigit() and "agent" in r and "task" in r


def test_t2_actor(tmp):
    tc.set_current_agent_id("agent_x")
    tc.set_current_task_id("task_123")
    try:
        wl.log_write(tmp["root"] / "data" / "bar.json", gate="self_write")
    finally:
        tc.set_current_agent_id(None)
        tc.set_current_task_id(None)
    r = _read_lines(tmp["ledger"])[-1]
    assert r["agent"] == "agent_x" and r["task"] == "task_123", f"행위자 유실: {r}"


def test_t3_self_skip(tmp):
    before = len(_read_lines(tmp["ledger"]))
    wl.log_write(tmp["ledger"], gate="safe_store")
    wl.log_write(str(tmp["ledger"]) + ".1", gate="safe_store")
    assert len(_read_lines(tmp["ledger"])) == before, "원장 자신의 쓰기가 기록됨(자기지시 루프)"


def test_t4_rotation(tmp):
    saved = wl._ROTATE_BYTES
    wl._ROTATE_BYTES = 100
    try:
        wl.log_write(tmp["root"] / "data" / "r1.json")
        wl.log_write(tmp["root"] / "data" / "r2.json")  # 상한 초과 → 로테이션 후 기록
    finally:
        wl._ROTATE_BYTES = saved
    assert os.path.exists(str(tmp["ledger"]) + ".1"), "로테이션 미발생"
    cur = _read_lines(tmp["ledger"])
    assert len(cur) == 1 and cur[0]["path"] == "data/r2.json"


def test_t5_never_raise(tmp):
    saved = wl._LEDGER_PATH
    wl._LEDGER_PATH = tmp["root"] / "no_dir_here" / "x" / "ledger.jsonl" / "impossible"
    try:
        wl.log_write(tmp["root"] / "data" / "z.json")  # 예외가 새면 테스트 실패
    finally:
        wl._LEDGER_PATH = saved


def test_t6_safe_store_gate(tmp):
    import safe_store
    target = tmp["root"] / "data" / "gate_probe.json"
    safe_store.safe_save_json(target, {"k": 1})
    rows = [r for r in _read_lines(tmp["ledger"]) if r["path"] == "data/gate_probe.json"]
    assert rows and rows[-1]["gate"] == "safe_store", "safe_store 관문이 원장에 안 남음"
    assert json.loads(target.read_text())["k"] == 1  # 본 쓰기 무손상


def test_t7_body_writes_op(tmp):
    # 앞 테스트(T4 로테이션)의 잔재 제거 — op_writes 는 .1 세대도 읽는다
    for p in (tmp["ledger"], Path(str(tmp["ledger"]) + ".1")):
        try:
            Path(p).unlink()
        except OSError:
            pass
    spec = importlib.util.spec_from_file_location("body_ops_wl_test", _BODY_OPS)
    bo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bo)
    bo._repo_root = lambda: str(tmp["root"])
    now = datetime.now()
    lines = [
        {"ts": now.isoformat(timespec="seconds"), "path": "data/a.json",
         "event": "write", "gate": "safe_store", "agent": "sys", "task": "t1", "origin": ""},
        {"ts": now.isoformat(timespec="seconds"), "path": "outputs/b.md",
         "event": "write", "gate": "self_write", "agent": "", "task": "", "origin": "user"},
        {"ts": (now - timedelta(days=30)).isoformat(timespec="seconds"), "path": "data/old.json",
         "event": "write", "gate": "safe_store", "agent": "", "task": "", "origin": ""},
    ]
    tmp["ledger"].write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n",
                             encoding="utf-8")
    out = bo.op_writes({"days": 7})
    files = {r["파일"] for r in out["items"]}
    assert files == {"data/a.json", "outputs/b.md"}, f"기간 필터 오류: {files}"
    assert "전수 아님" in out["text"], "부분성 정직 광고 누락"
    row = next(r for r in out["items"] if r["파일"] == "data/a.json")
    assert row["행위자"] == "sys" and row["작업"] == "t1"
    out = bo.op_writes({"days": 7, "path": "outputs"})
    assert {r["파일"] for r in out["items"]} == {"outputs/b.md"}, "스코프 필터 오류"
    tmp["ledger"].unlink()
    out = bo.op_writes({})
    assert out["total"] == 0 and "비어" in out["text"], "빈 원장 정직 메시지 누락"


def test_t8_heartbeat_compress(tmp):
    """심장박동 압축 — 행위자 없는 폴링 쓰기는 창(6h)당 1건(hb 표식), 행위자 실리면 전부."""
    hb_path = tmp["root"] / "data" / "device_registry.json"
    try:
        tmp["ledger"].unlink()
    except OSError:
        pass
    wl._hb_last.clear()
    wl.log_write(hb_path, gate="device_registry")   # 첫 심장박동 → 기록(hb)
    wl.log_write(hb_path, gate="device_registry")   # 창 안 → 억제
    wl.log_write(hb_path, gate="device_registry")   # 창 안 → 억제
    rows = _read_lines(tmp["ledger"])
    assert len(rows) == 1 and rows[0].get("hb") is True, f"압축 실패: {rows}"
    # 행위자가 실린 쓰기(진짜 사건)는 창 안이어도 전부 기록 — hb 아님
    tc.set_current_agent_id("registrar")
    try:
        wl.log_write(hb_path, gate="device_registry")
    finally:
        tc.set_current_agent_id(None)
    rows = _read_lines(tmp["ledger"])
    assert len(rows) == 2 and not rows[-1].get("hb"), f"행위자 쓰기가 억제됨: {rows}"
    # 창 만료 → 다시 1건 기록
    wl._hb_last["data/device_registry.json"] -= wl._HB_WINDOW_S + 1
    wl.log_write(hb_path, gate="device_registry")
    assert len(_read_lines(tmp["ledger"])) == 3, "창 만료 후 미기록"
    # 비심장박동 파일은 무영향
    wl.log_write(tmp["root"] / "data" / "normal.json", gate="safe_store")
    wl.log_write(tmp["root"] / "data" / "normal.json", gate="safe_store")
    normal = [r for r in _read_lines(tmp["ledger"]) if r["path"] == "data/normal.json"]
    assert len(normal) == 2, "비심장박동 파일이 압축됨"
    wl._hb_last.clear()


def _make_tmp():
    root = Path(tempfile.mkdtemp(prefix="write_ledger_"))
    (root / "data").mkdir()
    (root / ".git").mkdir()  # body_ops _guard_root 용
    return {"root": root, "ledger": root / "data" / "write_ledger.jsonl"}


def main():
    tmp = _make_tmp()
    saved_root, saved_ledger = wl._ROOT, wl._LEDGER_PATH
    wl._ROOT, wl._LEDGER_PATH = tmp["root"], tmp["ledger"]
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    try:
        for name, fn in tests:
            try:
                fn(tmp)
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:
                failed += 1
                print(f"FAIL {name}: 예외 {e}")
    finally:
        wl._ROOT, wl._LEDGER_PATH = saved_root, saved_ledger
        shutil.rmtree(tmp["root"], ignore_errors=True)
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)


# pytest 수집 호환
try:
    import pytest

    @pytest.fixture(scope="module", name="tmp")
    def _tmp_fixture():
        t = _make_tmp()
        saved_root, saved_ledger = wl._ROOT, wl._LEDGER_PATH
        wl._ROOT, wl._LEDGER_PATH = t["root"], t["ledger"]
        yield t
        wl._ROOT, wl._LEDGER_PATH = saved_root, saved_ledger
        shutil.rmtree(t["root"], ignore_errors=True)
except ImportError:
    pass


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
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
