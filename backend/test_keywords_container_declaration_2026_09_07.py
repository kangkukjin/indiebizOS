"""선언이 산문보다 좁으면 문서대로 쓴 문장이 죽는다 — 2026-09-07 (ep2518·ep2834 실측).

`[self:memory]{op:"save", keywords: ["a","b","c"], …}` 가 실행 관문에서 거절됐다:
    memory_op: `keywords` 에는 string 이 와야 하는데 5개짜리 목록이 왔습니다.
    목록의 항목마다 실행하려면 [table:each]{…}
그런데 저장소는 **이미 배열을 받게 고쳐져 있었다**(`normalize_keywords`, 2026-09-05
`fbc12119`, ep2831). 그 수리는 저장소·산문·시험까지 갔는데 **타입 선언만** 두었고,
같은 날 90분 뒤 ep2834 가 같은 자리에서 두 번 더 죽었다. 낱말이 스스로
"쉼표 구분 문자열 또는 배열" 이라고 적어 놓은 채 관문이 배열을 거절한 것이다 —
산문은 모델이 읽고 타입은 관문이 읽는데 둘이 어긋났다.

비용은 틀린 답이 아니라 **재타이핑**이다: 거절될 때마다 모델이 긴 content(강릉 보고서
기억은 ~700자)를 통째로 다시 쳐서 keywords 표기만 바꿔 보냈다.

부류 스윕에서 같은 모양이 하나 더 나왔다 — `publish_newspaper.keywords`
(설명 "JSON 리스트도 허용", 구현 `_parse_keywords` 는 리스트를 먼저 받는데 타입은 string).

실행: .venv/bin/python -m pytest -q backend/test_keywords_container_declaration_2026_09_07.py
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PKG = _ROOT / "data" / "packages" / "installed" / "tools"
sys.path.insert(0, str(_ROOT / "backend"))
import boot_paths  # noqa: E402,F401


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _props(pkg, tool):
    tj = json.loads((_PKG / pkg / "tool.json").read_text(encoding="utf-8"))
    for t in tj["tools"]:
        if t["name"] == tool:
            return ((t.get("input_schema") or {}).get("properties")) or {}
    raise AssertionError(f"{pkg}/{tool} 없음")


# ── ① 실행 관문 — 실제로 막고 있던 층 ────────────────────────────────────
def test_gate_accepts_keyword_list():
    """★op 는 일부러 빈 값이다 — 관문은 핸들러 실행 **전**이라 컨테이너 통과는 그대로
    보이면서, save 가 실물 저장소에 쓰는 일은 없다(이 시험을 처음 쓸 때 실제로 한 줄
    썼다 — '시험이 영속 경로에 쓴다' 부류를 시험 자신이 되풀이했다)."""
    sys.path.insert(0, str(_ROOT / "backend" / "ibl"))
    import ibl_routing as R
    out = R._route_handler(
        "memory_op", {"op": "", "keywords": ["a", "b", "c"], "content": "x"}, str(_ROOT))
    err = out if isinstance(out, str) else (out.get("error") or "")
    assert "개짜리 목록이 왔습니다" not in err, out
    assert "알 수 없는 op" in err, out          # 관문을 지나 핸들러의 op 분기까지 갔다는 증거


# ── ② 선언(단일 소스) ────────────────────────────────────────────────────
def test_keyword_slots_declared_string_or_array():
    for pkg, tool in (("memory", "memory_op"), ("web", "publish_newspaper")):
        assert _props(pkg, tool)["keywords"].get("type") == ["string", "array"], (pkg, tool)


def test_store_still_normalizes_both_notations():
    """선언을 넓혀도 저장 정규형은 그대로 쉼표 문자열이다(09-05 계약)."""
    md = _load("_t_kwdecl_memory_db", os.path.join(_PKG, "memory", "memory_db.py"))
    assert md.normalize_keywords(["a", " b ", ""]) == "a, b"
    assert md.normalize_keywords("a, b") == "a, b"
    np = _load("_t_kwdecl_newspaper", os.path.join(_PKG, "web", "tool_newspaper.py"))
    assert np._parse_keywords(["a", "b"]) == ["a", "b"]
    assert np._parse_keywords("a, b") == ["a", "b"]


# ── ③ 부류 관문 — 사람이 고른 자리 대신 빌드가 잡는다 ────────────────────
def test_no_declaration_contradicts_its_own_prose():
    """산문이 컨테이너를 허용한다고 말하는데 타입은 스칼라인 자리 = 0."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    from iblbuild_params_check import validate_param_type_vs_prose
    assert validate_param_type_vs_prose(_ROOT) == []


def test_contradiction_pattern_precision():
    """관문의 어법 판정 — 대안으로 명시한 것만 잡고 경로·이름·enum 산문은 놔둔다."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    from iblbuild_params_check import _CONTAINER_PROSE as P
    for yes in ("쉼표 구분 문자열 또는 배열 — 배열은 쉼표로 합쳐 저장",
                "섹션 키워드 목록 (쉼표/개행 구분, JSON 리스트도 허용)",
                "문자열 또는 리스트"):
        assert P.search(yes), yes
    for no in ("플레이리스트 이름 (playlist·playlist_create)",
               "아이템 첨부 경로(JSON 배열 문자열)",
               "append/upsert 후 배열 상한(오래된 앞을 버림)",
               "배열·값 자리(점 경로, 예 queue 또는 covered)",
               "중첩 목록 경로(점 표기)",
               "volumes=볼륨 목록(기본), scan=스캔/인덱싱"):
        assert not P.search(no), no


def test_impl_container_read_vs_scalar_declaration_is_audited():
    """구현이 컨테이너 기본값을 쓰는데 선언이 스칼라면 감사가 잡는다(옛 판은 미선언만 봤다)."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import iblbuild_params_check as C
    src = (_ROOT / "scripts" / "iblbuild_params_check.py").read_text(encoding="utf-8")
    assert "pkg_scalar_only" in src and "스칼라로 선언됨" in src
    assert C._SCALAR_TYPES == {"string", "integer", "number", "boolean"}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
