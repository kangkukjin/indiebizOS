"""[self:script] run args 경계 관용 회귀 (2026-08-30, ep2357).

사고: args 가 dict 리터럴만 받아 41건짜리 원장 배치가 IBL 문장 8KB 인라인 또는
Bash stdin 우회(등록 통로 밖 실행 — 실행 이력·상태·해마가 굶음)로 내몰렸다.
받은 dict 는 어차피 json.dumps 로 stdin 에 나간다 — JSON 객체 문자열은 같은 바이트.

관용: dict | JSON 객체 문자열($file:0/files_from 경유 포함). 객체 아닌
JSON(배열·스칼라)·비JSON 문자열·기타 타입은 정직 거절.

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


if __name__ == "__main__":
    # 러너는 하나 — pytest 에 위임 (test_single_runner 규약).
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
