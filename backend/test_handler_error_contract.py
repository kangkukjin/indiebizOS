"""핸들러 실패 계약 회귀 테스트 — B21-1·V21-1·V21-2 (2026-08-22, 상상훈련 21회차)

B21-1: 핸들러가 실패를 `\"오류: …\"` **평문**으로 돌려주면 실행기가 정상 결과로 읽어
       봉투를 `success: true · steps 3/3` 으로 닫았다. 스케줄·트리거가 실패를 성공으로
       집계하던 자리. 수리는 두 층: ①media_producer 26자리를 error dict 계약으로
       ②판정 단일 소스(is_error_result)에 한글 접두를 그물로.
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
    from workflow_engine import is_error_result
    assert is_error_result("오류: html은 필수입니다.") is True
    assert is_error_result("Error: nope") is True


def test_b21_1_success_text_still_ok():
    """과잉 거절 방지: 정상 결과 문자열은 그대로 성공이어야 한다."""
    from workflow_engine import is_error_result
    assert is_error_result("렌더링 완료: /tmp/a.png") is False
    assert is_error_result("HTML 동영상 제작 완료: /tmp/a.mp4") is False


def test_b21_1_contract_is_dict_not_prefix():
    """B21-1 본체: media_producer 는 실패를 dict 로 낸다 — 접두 없는 실패도 잡히게."""
    from workflow_engine import is_error_result
    mp = _load(MP, "mp_contract_probe")
    err = mp._err("렌더링 중 오류 발생: boom")   # 옛 평문이었다면 접두가 없어 안 잡히던 모양
    assert isinstance(err, dict) and err.get("success") is False, err
    assert is_error_result(err) is True, err


def test_b21_1_no_bare_error_strings_left():
    """계약이 다시 평문으로 후퇴하지 않게 — 소스에 평문 오류 return 이 없어야 한다."""
    import re
    pat = re.compile(r'return\s+f?"[^"]*(오류|실패)')
    for rel in ("data/packages/installed/tools/media_producer/handler.py",
                "data/packages/installed/tools/media_producer/gemini_image.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        hits = [m.group(0) for m in pat.finditer(src)]
        assert not hits, "%s 에 평문 오류 return 이 남았다: %r" % (rel, hits[:3])


def test_b34_1_scalar_param_given_list_is_refused():
    """B34-1(2026-08-23 #repair): 스칼라를 선언한 param 에 목록이 오면 관문이 거절한다.

    실측(수리 전) — 결말이 액션마다 달랐고 셋 다 잘못이었다:
      [sense:stock]{op:"quote", ticker: ["AAPL","MSFT"]} → success:true, 태국 AAPL19.BK
      [sense:weather]{city: ["수원","서울"]}              → 'list' has no attribute 'lower'
      [sense:stock]{op:"search", query: [...]}            → 'list' has no attribute 'strip'
    조용한 오답이 예외보다 나쁘다 — 아무도 의심하지 않는다.
    처방은 함수 열거가 아니라 tool.json input_schema 대조 한 곳이다."""
    import ibl_routing
    out = ibl_routing._route_handler("get_weather", {"city": ["수원", "서울"]}, ".")
    assert out.get("success") is False, out
    msg = out.get("error") or ""
    assert "city" in msg and "string" in msg, msg
    assert "table:each" in msg, f"항목마다 도는 법을 안 가리킨다: {msg}"
    # 조용한 오답의 원본 사례도 같은 관문에서 막힌다
    out2 = ibl_routing._route_handler("stock_op", {"op": "quote", "ticker": ["AAPL", "MSFT"]}, ".")
    assert out2.get("success") is False and "ticker" in (out2.get("error") or ""), out2


def test_b34_1_array_params_and_scalars_still_pass():
    """★깨질 용법 0 — array 로 선언된 param($items 통짜 바인딩의 정당한 자리)과
    선언 없는 내부 키는 관문을 그대로 통과해야 한다. 가드가 넓으면 그게 새 결함이다."""
    from tool_loader import load_tool_schema
    props = ((load_tool_schema("show_location_map") or {}).get("input_schema") or {}).get("properties") or {}
    assert props.get("markers", {}).get("type") == "array", props.get("markers")

    import ibl_routing
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ibl", "ibl_routing.py"),
               encoding="utf-8").read()
    assert '("string", "number", "integer", "boolean")' in src, "스칼라 화이트리스트가 사라졌다"
    # 스칼라만 실린 흔한 호출은 스키마를 읽는 경로에 들어가지도 않는다
    out = ibl_routing._route_handler("get_weather", {"city": "수원"}, ".")
    assert "와야 하는데" not in json.dumps(out, ensure_ascii=False), out


def test_b35_1_string_param_given_number_is_normalized_not_exploded():
    """B35-1(2026-08-24 #repair): string 자리에 숫자가 오면 **파이썬 예외가 새면 안 된다**.

    수리 전 실측 — 같은 param, 같은 종류의 위반인데 결말이 갈렸다:
      [sense:weather]{city: [\"수원\",\"서울\"]} → 정직 거절(무엇을 쓰라는 안내까지)
      [sense:weather]{city: 12345}          → 'int' object has no attribute 'lower'
    옛 관문이 list/dict 만 봤기 때문이다. 숫자→문자열은 **되돌릴 수 있으므로**
    거절이 아니라 정규화가 맞다(코퍼스 33건이 이 표기 차이에 기대고 있다)."""
    import ibl_routing as R
    ok, new, why = R._coerce_declared_scalar(12345, "string")
    assert ok and new == "12345" and isinstance(new, str), (ok, new, why)
    # 코퍼스가 실제로 쓰는 표기 차이 — 되돌릴 수 있으니 전부 통과해야 한다
    for v, t, want in (("23", "integer", 23), (2, "string", "2"),
                       ("80", "integer", 80), ("true", "boolean", True),
                       (3.0, "integer", 3), ("80", "number", 80)):
        ok, new, why = R._coerce_declared_scalar(v, t)
        assert ok and new == want and type(new) is type(want), (v, t, ok, new, why)


def test_b35_2_lossy_or_ambiguous_scalar_is_refused_not_coerced():
    """B35-2(2026-08-24 #repair): 버림·모호가 생기는 변환은 **조용히 해주면 안 된다**.

    수리 전 실측:
      [table:take]{n: 3.7}  → 10행을 3행으로 말없이 깎고 success:true (경고 0)
      [self:grep]{regex: \"false\"} → 파이썬 진리값 규칙에 걸려 **참**으로 읽혀
                                     같은 질의가 70건 vs 79건으로 갈렸다
    이 저장소가 pre-commit 으로 따로 감시하는 '침묵 클램프' 와 같은 부류다."""
    import ibl_routing as R
    for v, t, mark in ((3.7, "integer", "정수"), ("yes", "boolean", "true/false"),
                       (1, "boolean", "true/false"), ("abc", "integer", "숫자"),
                       (True, "string", "참거짓"), (True, "integer", "참거짓")):
        ok, new, why = R._coerce_declared_scalar(v, t)
        assert not ok and mark in (why or ""), (v, t, ok, new, why)
    # \"false\" 는 참이 아니라 거짓으로 읽혀야 한다(파이썬 bool(\"false\") 는 True)
    ok, new, why = R._coerce_declared_scalar("false", "boolean")
    assert ok and new is False, (ok, new, why)
    # 관문을 통과한 뒤가 아니라 관문에서 막힌다 — 사유가 실려야 한다
    out = R._route_handler("data_take", {"n": 3.7, "items": [{"a": 1}, {"a": 2}]}, ".")
    assert out.get("success") is False and "n" in (out.get("error") or ""), out


def test_b35_3_container_goes_only_where_array_or_object_is_declared():
    """B35-3 3조각(2026-08-24 #repair) — 컨테이너는 **array/object 로 선언된
    자리에만** 들어간다.

    이 시험이 대체한 두 개(_..._error_is_translated / _..._stays_permissive_...)는
    정반대 계약을 못 박고 있었다: ①미선언 자리의 컨테이너는 핸들러까지 흘려보내고
    실패한 뒤 파이썬 예외를 사후에 '번역'한다(_container_type_error_hint)
    ②'선언 없으면 불검사' 기본값은 뒤집지 않는다.
    3조각 수리가 그 둘을 걷어냈다 — 정당한 컨테이너 용법은 '선언이 없어서' 사는 게
    아니라 **object/array 로 선언되어서** 산다(빌드의 param 선언 완전성 검사가
    그 선언을 강제한다). 시험도 새 계약을 본다.

    ★사후 번역 층은 소스에 잔해가 남으면 안 된다 — 다시 자라는 길을 막는다."""
    import ibl_routing as R
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ibl", "ibl_routing.py"),
               encoding="utf-8").read()
    assert "_container_type_error_hint" not in src, "사후 번역 층 잔해가 남았다"
    assert not hasattr(R, "_container_type_error_hint")

    # ① 스칼라로 선언된 자리의 컨테이너는 관문에서 거절된다 — 파이썬 예외로 새지 않는다
    #    (read_op.path 는 이번 수리 ①로 빌드가 target_key 를 properties 에 넣어 선언됐다)
    out = R._route_handler("read_op", {"path": ["/etc/hosts", "/etc/passwd"]}, ".")
    assert out.get("success") is False, out
    _e = out.get("error") or ""
    assert "path" in _e and "table:each" in _e, out

    # ② array/object 로 선언된 자리는 그대로 통과한다 — 관문이 거절을 만들지 않는다
    out = R._route_handler("data_take", {"n": 2, "items": [{"a": 1}, {"a": 2}, {"a": 3}]}, ".")
    assert "개짜리 목록이 왔습니다" not in (out.get("error") or ""), out
    # 유니온 선언(where: string|object|array)의 사전 용법도 산다
    out = R._route_handler("data_filter",
                           {"items": [{"상태": "이동"}], "where": {"상태": "이동"}}, ".")
    assert "개짜리 사전이 왔습니다" not in (out.get("error") or ""), out


def test_b35_1_parser_keeps_leading_zero_identifiers():
    """B35-1 2단계: 앞 0 이 붙은 정수 리터럴은 수량이 아니라 식별자다.

    파서가 `ticker: 005930` 을 int 5930 으로 만들면 앞 0 은 **아래층 어디서도**
    못 되살린다 — 35회차가 \"str() 변환도 불가\"라며 관문 수리를 막다른 길로 판정한
    근거가 이것이었다. 정보가 사라지는 자리에서 지킨다.
    파급 실측: 코퍼스 3,610 문장 파스 트리 대조 변화 0건."""
    from ibl_parser import parse
    p = parse('[sense:stock]{op: \"quote\", ticker: 005930}')[0]["params"]
    assert p["ticker"] == "005930" and isinstance(p["ticker"], str), p
    # ★평범한 숫자는 그대로 숫자여야 한다(좌표·개수가 문자열이 되면 그게 새 결함)
    q = parse('[limbs:screen]{op: \"click\", x: 300, y: 200}')[0]["params"]
    assert q["x"] == 300 and isinstance(q["x"], int), q
    r = parse('[table:take]{n: 0}')[0]["params"]
    assert r["n"] == 0 and isinstance(r["n"], int), r
    s = parse('[sense:weather]{lat: 0.5}')[0]["params"]
    assert s["lat"] == 0.5 and isinstance(s["lat"], float), s


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
