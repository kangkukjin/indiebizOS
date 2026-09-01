"""[self:script] run args 경계 관용 회귀 (2026-08-30, ep2357).

사고: args 가 dict 리터럴만 받아 41건짜리 원장 배치가 IBL 문장 8KB 인라인 또는
Bash stdin 우회(등록 통로 밖 실행 — 실행 이력·상태·해마가 굶음)로 내몰렸다.
받은 dict 는 어차피 json.dumps 로 stdin 에 나간다 — JSON 객체 문자열은 같은 바이트.

관용: dict | JSON 객체 문자열($file:0/files_from 경유 포함). 객체 아닌
JSON(배열·스칼라)·비JSON 문자열·기타 타입은 정직 거절.

★2026-09-01 args_file 추가 — 같은 마찰이 이틀 연속 재발했다(08-30 실측 ④ → 09-01 실측 ⑥).
인라인 관용만으로는 원장 48행 upsert 가 여전히 IBL 문장에 킬로바이트를 박는 일이라,
두 날 다 셸 stdin 우회로 갔다(등록 통로 밖 실행 = 실행 이력·상태·해마가 굶는다).
payload 는 이미 이 몸 안의 파일이다 — **나르지 말고 가리킨다**. 계약은 args 와 같은
JSON 객체 하나이고, 두 통로를 함께 주면 정직 거절한다(stdin 은 하나).

실행: python3 backend/test_script_args_coercion.py  (또는 pytest)
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

_MOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "packages", "installed", "tools", "system_essentials", "script_ops.py")
spec = importlib.util.spec_from_file_location("script_ops_t", _MOD)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def test_none_and_dict_pass_through():
    assert S._coerce_args(None) == (None, None)
    assert S._coerce_args({"op": "append"}) == ({"op": "append"}, None)


def test_json_object_string_accepted():
    """ep2357 부류의 성공형 — $file:0 치환 결과(JSON 객체 문자열)가 그대로 산다."""
    args, err = S._coerce_args('{"path": "outputs/x.json", "op": "upsert", "items": [{"id": 1}]}')
    assert err is None
    assert args["op"] == "upsert" and args["items"][0]["id"] == 1


def test_korean_content_roundtrip():
    args, err = S._coerce_args('{"note": "평택·아산 편입 — 따옴표 \\" 포함"}')
    assert err is None and "평택" in args["note"]


def test_non_object_json_rejected_honestly():
    for bad, kind in [("[1, 2, 3]", "list"), ('"문자열"', "str"), ("42", "int")]:
        args, err = S._coerce_args(bad)
        assert args is None and err and "JSON 객체" in err, (bad, err)


def test_non_json_string_rejected_honestly():
    args, err = S._coerce_args("$file:0")  # 치환이 안 된 채 도달한 플레이스홀더도 여기서 잡힌다
    assert args is None and err and "파싱되지 않습니다" in err


def test_other_types_rejected():
    args, err = S._coerce_args([{"op": "x"}])
    assert args is None and err and "JSON 객체" in err


# ───────────────── args_file — 가리키기 통로 (2026-09-01) ─────────────────

def _payload(tmp_path, text):
    f = tmp_path / "payload.json"
    f.write_text(text, encoding="utf-8")
    return str(f)


def test_args_file_로_큰_payload_를_가리킨다(tmp_path):
    """실사고 재현형 — 원장 48행 upsert 가 문장 밖 파일에서 온다."""
    import json
    body = {"path": "outputs/x.json", "op": "upsert", "target": "covered", "key": "id",
            "items": [{"id": f"v{i}"} for i in range(48)]}
    args, err, src = S._resolve_run_args({"args_file": _payload(tmp_path, json.dumps(body))})
    assert err is None
    assert len(args["items"]) == 48 and args["op"] == "upsert"
    assert src, "어느 파일에서 왔는지 결과에 실릴 출처가 없다"


def test_두_통로를_함께_주면_거절(tmp_path):
    """stdin 은 하나다 — 조용히 하나를 고르면 안 고른 쪽을 준 사람이 속는다."""
    args, err, _ = S._resolve_run_args({"args_file": _payload(tmp_path, '{"a": 1}'),
                                        "args": {"b": 2}})
    assert args is None and err and "함께" in err


def test_없는_파일_비JSON_객체아님은_정직_거절(tmp_path):
    args, err, _ = S._resolve_run_args({"args_file": str(tmp_path / "없다.json")})
    assert args is None and "찾지 못했습니다" in err

    args, err, _ = S._resolve_run_args({"args_file": _payload(tmp_path, "이건 JSON 이 아니다")})
    assert args is None and "JSON 이 아닙니다" in err

    args, err, _ = S._resolve_run_args({"args_file": _payload(tmp_path, "[1, 2]")})
    assert args is None and "JSON 객체" in err


def test_args_없는_run_은_stdin_없음_그대로():
    """무회귀 — 종전 두 모양(없음·인라인)이 그대로 산다."""
    assert S._resolve_run_args({})[:2] == (None, None)
    assert S._resolve_run_args({"args": {"op": "append"}})[:2] == ({"op": "append"}, None)


if __name__ == "__main__":
    # 러너는 하나 — pytest 에 위임 (test_single_runner 규약).
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
