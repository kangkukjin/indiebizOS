#!/usr/bin/env python3
"""공개 노출 ↔ 인증 대조 — 세션 없이 도달 가능한 라우트가 자체 인증을 가졌는지 검사.

왜: 원격 인증 게이트(api.remote_access_guard)는 `is_public_remote_path` 가 True 인
경로를 **런처 세션 없이 통과**시킨다. 그 경로들 상당수는 "자체 시크릿 게이트 보유"라는
주석과 함께 등록돼 있는데, 그 불변식을 강제하는 장치가 없었다 — 등록만 하고 검사를
빠뜨리면 그 라우트는 **조용히 공개 인터넷에 열린다**. 게다가 시크릿
(SHOWCASE_ORIGIN_SECRET)을 5개 모듈이 공유해 실패 폭도 크다.

오라클을 코드가 아니라 **실행 중인 라우트 테이블**로 삼는다: 실제 app.routes 를 훑고
실제 `is_public_remote_path` 에 물어본다. 정규식으로 등록 목록을 재파싱하면 그 파서가
또 드리프트하기 때문이다(이 저장소가 이미 겪은 부류).

인증으로 인정하는 것(AUTH_PRIMITIVES):
  · _check_secret        — 공개 서빙 5종(showcase/portal/bulletin/report/family-news)
  · require_auth / verify_session — 원격 파인더(/nas/*)의 자체 session_token
  · limb_keys.validate   — USB 손발(/limb/*)의 limb key

★핸들러가 직접 부르지 않고 헬퍼를 거치는 경우가 많다(showcase 의 thumb/media/subtitle
은 `_resolve()` 안에서 검사). 그래서 같은 모듈 안의 호출을 깊이 3까지 따라간다 —
직접 호출만 보면 멀쩡한 라우트를 무검사로 오판한다(실측).

의도적으로 익명인 경로는 ANONYMOUS_ALLOW 에 **사유와 함께** 선언한다. 선언에 없고
인증도 없으면 커밋 차단 — 새 공개 라우트가 조용히 새는 것을 막는 게 이 가드의 전부다.
"""
import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

AUTH_PRIMITIVES = {
    "_check_secret",
    "require_auth",
    "verify_session",
    "validate",          # limb_keys.validate — 모듈 한정으로 아래에서 좁힌다
}
# `validate` 는 흔한 이름이라 이 모듈에서만 인증으로 친다.
_VALIDATE_OK_MODULES = {"api_limb"}

MAX_DEPTH = 3

# 공허한 통과 방지용 하한 — 앱이 온전히 로드되면 훨씬 크다(2026-07-25 실측: 전체 400+,
# 공개 72). 넉넉히 낮게 잡아 정상 변동에는 안 걸리되, "라우트가 거의 안 실렸다"는
# 확실히 잡는다. 라우트가 크게 줄어드는 정당한 변경이라면 이 숫자를 함께 낮출 것.
MIN_TOTAL_ROUTES = 150
MIN_PUBLIC_ROUTES = 40

# 의도적으로 인증 없이 열린 경로 — (METHOD, PATH): 사유.
# ★여기 추가하는 것은 "이 경로를 공개 인터넷에 익명으로 연다"는 선언이다.
ANONYMOUS_ALLOW = {
    ("GET",  "/ping"):                           "생존 핑 — 민감정보 없음, 다른 몸이 무인증으로 연결상태 확인",
    ("GET",  "/launcher/app"):                   "런처 셸 — 로그인 화면 자체(로그인 전에 받아야 함)",
    ("GET",  "/launcher/config"):                "런처 부트 설정 — 로그인 전에 읽히는 공개 상수",
    ("POST", "/launcher/auth/login"):            "로그인 엔드포인트 — 인증을 만드는 곳",
    ("POST", "/launcher/auth/logout"):           "로그아웃",
    ("GET",  "/launcher/manifest.webmanifest"):  "PWA 설치 매니페스트 — 설치 판단이 로그인보다 먼저",
    ("GET",  "/launcher/sw.js"):                 "PWA 서비스워커 — 정적 자산",
    ("GET",  "/launcher/apple-touch-icon.png"):  "PWA 아이콘 — 정적 자산",
    ("GET",  "/launcher/icon-192.png"):          "PWA 아이콘 — 정적 자산",
    ("GET",  "/launcher/icon-512.png"):          "PWA 아이콘 — 정적 자산",
    ("GET",  "/launcher/icon-maskable-512.png"): "PWA 아이콘 — 정적 자산",

    # 원격 파인더(/nas/*)는 자체 session_token 인증을 쓰지만, 로그인 화면 자체와
    # PWA 정적 자산은 로그인 전에 받아야 한다 — 런처 쪽과 같은 부류.
    # ★셋 다 데이터를 싣지 않음을 확인함(2026-07-25): lite·lite2 는 모듈 상수 HTML
    #   그대로 반환, app 은 config 를 enabled 판정에만 쓰고 보간이 없다.
    ("POST", "/nas/auth/login"):                 "파인더 로그인 — 인증을 만드는 곳",
    ("POST", "/nas/auth/logout"):                "파인더 로그아웃",
    ("GET",  "/nas/app"):                        "파인더 셸 — 로그인 화면 자체(config 는 enabled 판정만, 보간 없음)",
    ("GET",  "/nas/lite"):                       "구형 기기용 파인더 셸 — 모듈 상수 HTML(데이터 없음)",
    ("GET",  "/nas/lite2"):                      "초-구형 기기용 파인더 셸 — 모듈 상수 HTML(데이터 없음)",
    ("GET",  "/nas/manifest.webmanifest"):       "PWA 설치 매니페스트 — 정적 자산",
    ("GET",  "/nas/sw.js"):                      "PWA 서비스워커 — 정적 자산",
    ("GET",  "/nas/apple-touch-icon.png"):       "PWA 아이콘 — 정적 자산",
    ("GET",  "/nas/icon-192.png"):               "PWA 아이콘 — 정적 자산",
    ("GET",  "/nas/icon-512.png"):               "PWA 아이콘 — 정적 자산",
    ("GET",  "/nas/icon-maskable-512.png"):      "PWA 아이콘 — 정적 자산",
}


def _module_funcs(mod) -> dict:
    """모듈의 톱레벨 함수 이름 → 소스."""
    out = {}
    try:
        src = inspect.getsource(mod)
        tree = ast.parse(src)
    except Exception:
        return out
    lines = src.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = "\n".join(lines[node.lineno - 1: node.end_lineno])
    return out


def _called_names(src: str) -> set:
    """소스 안에서 호출되는 이름들(점 표기는 마지막 조각도 함께)."""
    names = set()
    try:
        tree = ast.parse(src.lstrip())
    except SyntaxError:
        try:
            tree = ast.parse("if 1:\n" + "\n".join("    " + l for l in src.splitlines()))
        except SyntaxError:
            return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)      # 데코레이터(@require_auth)·참조도 포함
    return names


def _auth_reachable(fn_src: str, funcs: dict, mod_name: str, depth: int = 0) -> bool:
    """이 소스에서 인증 프리미티브가 (모듈 내 호출을 따라) 닿는가."""
    names = _called_names(fn_src)
    for p in AUTH_PRIMITIVES:
        if p == "validate" and mod_name not in _VALIDATE_OK_MODULES:
            continue
        if p in names:
            return True
    if depth >= MAX_DEPTH:
        return False
    for n in names:
        sub = funcs.get(n)
        if sub and _auth_reachable(sub, funcs, mod_name, depth + 1):
            return True
    return False


def self_test() -> int:
    """_auth_reachable 의 정확도 회귀 (--self-test).

    이 가드의 급소는 **간접 호출 추적**이다. 직접 호출만 보도록 퇴화하면 showcase 의
    thumb/media/subtitle 처럼 헬퍼(`_resolve`) 안에서 검사하는 라우트가 전부 '무검사'로
    뜨고, 대량 오탐이 나면 가드가 꺼진다 — 그러면 진짜 구멍도 같이 안 보인다.
    """
    funcs = {
        "_check_secret": "def _check_secret(h):\n    raise HTTPException(403)",
        "_resolve": "def _resolve(slug, fid, rel, h):\n    _check_secret(h)\n    return 1",
        "_deep1": "def _deep1(h):\n    return _resolve(1, 2, 3, h)",
        "_innocent": "def _innocent(x):\n    return x + 1",
    }
    cases = [
        ("직접 호출",           "async def f(h):\n    _check_secret(h)", "api_showcase", True),
        ("헬퍼 1단 경유",       "async def thumb(h):\n    folder, p = _resolve(1, 2, 3, h)", "api_showcase", True),
        ("헬퍼 2단 경유",       "async def f(h):\n    return _deep1(h)", "api_showcase", True),
        ("검사 없음",           "async def f():\n    return _innocent(1)", "api_showcase", False),
        ("데코레이터 인증",     "@require_auth\nasync def f(request):\n    return 1", "api_nas", True),
        ("limb_keys.validate",  "async def f(req):\n    rec = limb_keys.validate(req.key)", "api_limb", True),
        ("validate 오인 방지",  "async def f(d):\n    return validate(d)", "api_portal", False),
    ]
    bad = 0
    for name, src, mod, expect in cases:
        got = _auth_reachable(src, funcs, mod)
        ok = got == expect
        bad += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:22} 기대={expect} 실제={got}")
    if bad:
        print(f"\n[FAIL] 자체 회귀 {bad}건 — 간접 추적이 퇴화하면 대량 오탐으로 가드가 꺼진다.")
        return 1
    print(f"[OK] 자체 회귀 {len(cases)}건 통과")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    try:
        import api
        from api_launcher_web import is_public_remote_path
    except Exception as e:
        print(f"[FAIL] 앱 임포트 실패 — 검사할 수 없습니다: {e.__class__.__name__}: {e}")
        return 1

    mod_cache: dict = {}
    unguarded, guarded, exempted = [], 0, 0

    for route in api.app.routes:
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if not path or endpoint is None:
            continue
        for method in sorted(getattr(route, "methods", None) or set()):
            if method in ("HEAD", "OPTIONS"):
                continue
            if not is_public_remote_path(method, path):
                continue

            if (method, path) in ANONYMOUS_ALLOW:
                exempted += 1
                continue

            mod = sys.modules.get(getattr(endpoint, "__module__", ""), None)
            mod_name = getattr(endpoint, "__module__", "?")
            if mod_name not in mod_cache:
                mod_cache[mod_name] = _module_funcs(mod) if mod else {}
            funcs = mod_cache[mod_name]
            try:
                src = inspect.getsource(endpoint)
            except Exception:
                src = ""
            if _auth_reachable(src, funcs, mod_name):
                guarded += 1
            else:
                unguarded.append((method, path, endpoint.__name__, mod_name))

    total_routes = sum(1 for r in api.app.routes if getattr(r, "path", None))
    inspected = guarded + exempted + len(unguarded)
    print(f"[공개 라우트] 전체 라우트 {total_routes} · 공개 {inspected} "
          f"(자체인증 {guarded} · 익명 선언 {exempted} · 무검사 {len(unguarded)})")

    # ★공허한 통과 방지 (2026-07-25). CI 첫 실행에서 이 가드가 공개 라우트를 1개만
    # 세고 초록으로 통과했다 — 로컬은 72개였다. 아무것도 검사하지 못한 가드가 초록이면
    # 거짓 안전이고, 그건 붉은 것보다 나쁘다. 라우트가 제대로 안 실렸다는 뜻이므로
    # (앱 부분 로드·라우터 등록 실패) 통과시키지 않는다.
    if total_routes < MIN_TOTAL_ROUTES or inspected < MIN_PUBLIC_ROUTES:
        print()
        print(f"[FAIL] 검사 대상이 비정상적으로 적습니다 — 앱이 온전히 로드되지 않았습니다.")
        print(f"  전체 라우트 {total_routes} (최소 기대 {MIN_TOTAL_ROUTES})"
              f" · 공개 라우트 {inspected} (최소 기대 {MIN_PUBLIC_ROUTES})")
        print("  이 상태의 '통과'는 아무것도 검사하지 않은 통과입니다.")
        print("  라우터 등록이 조용히 빠졌는지, 의존성이 모자라 일부 모듈이 안 실렸는지 확인하세요.")
        by_prefix: dict = {}
        for r in api.app.routes:
            p = getattr(r, "path", "") or ""
            if p.startswith("/"):
                by_prefix[p.split("/")[1]] = by_prefix.get(p.split("/")[1], 0) + 1
        print(f"  실린 경로 접두사: {dict(sorted(by_prefix.items()))}")
        return 1

    if unguarded:
        print()
        print("[FAIL] 세션 없이 도달 가능한데 자체 인증이 없는 라우트:")
        for method, path, name, mod_name in unguarded:
            print(f"  {method:5} {path:44} {name}()  [{mod_name}]")
        print()
        print("이 라우트들은 원격 인증 게이트를 통과하므로 공개 인터넷에 그대로 열립니다.")
        print("고치는 법:")
        print("  · 자체 게이트 추가 — _check_secret(x_showcase_secret) / @require_auth / limb_keys.validate")
        print("  · 공개될 필요가 없으면 api_launcher_web.is_public_remote_path 에서 제거(=세션 요구)")
        print("  · 정말 익명이어야 하면 scripts/check_public_routes.py 의 ANONYMOUS_ALLOW 에 사유와 함께 선언")
        return 1

    print("[OK] 공개 라우트 전부 자체 인증 보유 또는 익명 선언됨")
    return 0


if __name__ == "__main__":
    sys.exit(main())
