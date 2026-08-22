"""핸들러 실패 계약 회귀 테스트 — B21-1·V21-1·V21-2 (2026-08-22, 상상훈련 21회차)

B21-1: 핸들러가 실패를 `\"오류: …\"` **평문**으로 돌려주면 실행기가 정상 결과로 읽어
       봉투를 `success: true · steps 3/3` 으로 닫았다. 스케줄·트리거가 실패를 성공으로
       집계하던 자리. 수리는 두 층: ①media_producer 26자리를 error dict 계약으로
       ②판정 단일 소스(_is_error_result)에 한글 접두를 그물로.
       ★접두만으로는 원리적으로 부족하다 — 26자리 중 10자리는 접두가 아예 없었다
       (`FFmpeg 오류:`·`렌더링 중 오류 발생:`). 그래서 계약이 본체고 접두는 안전망이다.
V21-1: `[engines:render_html]` 이 파이프 통화를 안 먹어 `[table:brief] >> render_html`
       이 죽었다. `[self:write]` 와 같은 파이프 싱크 규약으로 확장.
V21-2: `[self:cctv]{op:\"stats\"}` 가 소스별 현황을 갖고도 items 를 안 내 변환자가 거절.

실행: python3 backend/test_handler_error_contract.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401 — 층 디렉토리 등재

# ★이 배터리는 backend/ 밖(data/packages)의 파일도 읽는다. 수리 격리 워크트리에서 돌리면
#   그쪽 data/ 는 세션 시작 시점 스냅샷이라 최신 패키지 편집이 안 보인다 — 라이브에서 돌릴 것.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MP = os.path.join(ROOT, "data/packages/installed/tools/media_producer/handler.py")


def _load(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_b21_1_korean_prefix_is_error():
    """B21-1 그물: 한글 오류 접두도 실패로 읽힌다(영어판과 대칭)."""
    from workflow_engine import _is_error_result
    assert _is_error_result("오류: html은 필수입니다.") is True
    assert _is_error_result("Error: nope") is True


def test_b21_1_success_text_still_ok():
    """과잉 거절 방지: 정상 결과 문자열은 그대로 성공이어야 한다."""
    from workflow_engine import _is_error_result
    assert _is_error_result("렌더링 완료: /tmp/a.png") is False
    assert _is_error_result("HTML 동영상 제작 완료: /tmp/a.mp4") is False


def test_b21_1_contract_is_dict_not_prefix():
    """B21-1 본체: media_producer 는 실패를 dict 로 낸다 — 접두 없는 실패도 잡히게."""
    from workflow_engine import _is_error_result
    mp = _load(MP, "mp_contract_probe")
    err = mp._err("렌더링 중 오류 발생: boom")   # 옛 평문이었다면 접두가 없어 안 잡히던 모양
    assert isinstance(err, dict) and err.get("success") is False, err
    assert _is_error_result(err) is True, err


def test_b21_1_no_bare_error_strings_left():
    """계약이 다시 평문으로 후퇴하지 않게 — 소스에 평문 오류 return 이 없어야 한다."""
    import re
    pat = re.compile(r'return\s+f?"[^"]*(오류|실패)')
    for rel in ("data/packages/installed/tools/media_producer/handler.py",
                "data/packages/installed/tools/media_producer/gemini_image.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        hits = [m.group(0) for m in pat.finditer(src)]
        assert not hits, "%s 에 평문 오류 return 이 남았다: %r" % (rel, hits[:3])


def test_v21_1_render_html_eats_pipe_currency():
    """V21-1: html 생략 시 직전 통화를 받는다([self:write] 와 같은 규약)."""
    mp = _load(MP, "mp_pipe_probe")
    from_msg = mp._html_from_prev(json.dumps({"message": "비트코인 7만 달러"}, ensure_ascii=False))
    assert "비트코인 7만 달러" in from_msg, from_msg
    from_items = mp._html_from_prev(json.dumps({"items": [{"이름": "카카오맵", "수": 6892}]},
                                               ensure_ascii=False))
    assert "<table" in from_items and "카카오맵" in from_items, from_items
    assert mp._html_from_prev("<h1>이미 HTML</h1>") == "<h1>이미 HTML</h1>"
    assert mp._html_from_prev(None) == ""


def test_v21_2_cctv_stats_emits_currency():
    """V21-2: stats 봉투가 items 를 낸다 + 어휘 선언도 items."""
    import yaml
    decl = yaml.safe_load(open(os.path.join(
        ROOT, "data/packages/installed/tools/cctv/ibl_actions.yaml"), encoding="utf-8"))
    _cctv = decl["nodes"]["self"]["actions"]["cctv"]
    assert _cctv["returns"] == "items", _cctv
    src = open(os.path.join(ROOT, "data/packages/installed/tools/cctv/handler.py"),
               encoding="utf-8").read()
    assert '"items": _sources' in src, "cctv_sources 가 items 를 안 낸다"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn()
            print("  ✓ %s" % fn.__name__)
        except Exception as e:
            fails += 1
            print("  ✗ %s — %s" % (fn.__name__, e))
    print("\n%d/%d 통과" % (len(fns) - fails, len(fns)))
    sys.exit(1 if fails else 0)
