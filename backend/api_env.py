"""
api_env.py - 환경변수(.env) 설정 API

런처 설정 다이얼로그의 'API 키' 탭이 사용.
.env 파일을 직접 열지 않고 키를 조회(마스킹)·수정·테스트한다.

보안:
- GET은 값을 마스킹해서 반환 (비밀키는 끝 4자만). 전체 값 조회 엔드포인트는 없다 (write-only).
- 이 라우터는 is_public_remote_path 에 등록하지 않는다 — 터널로 절대 노출 금지, 로컬 전용.
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

import requests
import yaml
from fastapi import APIRouter, HTTPException

from api_config import _read_env_value, _write_env_value, ENV_PATH
from runtime_utils import get_data_path as _get_data_path

router = APIRouter()

_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# ============================================================
# 카탈로그: 알려진 키의 메타데이터
#   label       사람이 읽는 이름
#   desc        설명 + 발급 절차 한 줄
#   signup_url  가입/키 발급 페이지
#   secret      True면 마스킹 + password 입력 (기본 True)
#   restart     True면 저장 후 백엔드 재시작 필요 (부팅 시 읽는 값)
#   test        실사용 테스트 스펙 {url, headers?, method?, ok_when_absent?}
#               url/headers 안의 {v}=이 키의 값, {OTHER_VAR}=다른 환경변수 값
# ============================================================

ENV_CATALOG: Dict[str, Dict[str, list]] = {
    "cloudflare": {
        "label": "Cloudflare · 공개 서빙",
        "entries": [
            {"name": "CLOUDFLARE_API_TOKEN", "label": "Cloudflare API 토큰",
             "desc": "터널·Workers·R2 관리용. 대시보드 → 내 프로필 → API 토큰에서 발급.",
             "signup_url": "https://dash.cloudflare.com/profile/api-tokens",
             "test": {"url": "https://api.cloudflare.com/client/v4/user/tokens/verify",
                      "headers": {"Authorization": "Bearer {v}"}}},
            {"name": "CLOUDFLARE_ACCOUNT_ID", "label": "Cloudflare 계정 ID",
             "desc": "대시보드 우측(또는 Workers 개요)에 표시되는 32자 ID.",
             "signup_url": "https://dash.cloudflare.com/", "secret": False},
            {"name": "R2_ACCESS_KEY_ID", "label": "R2 액세스 키 ID",
             "desc": "R2 → API 토큰 관리에서 S3 호환 자격증명 생성.",
             "signup_url": "https://dash.cloudflare.com/"},
            {"name": "R2_SECRET_ACCESS_KEY", "label": "R2 시크릿 키",
             "desc": "R2 S3 호환 자격증명의 시크릿 (생성 시 한 번만 표시됨).",
             "signup_url": "https://dash.cloudflare.com/"},
            {"name": "SHOWCASE_ORIGIN_SECRET", "label": "공개 서빙 공유 시크릿",
             "desc": "Worker↔맥 백엔드 공유 시크릿. 가입 불필요 — 바꾸면 Worker 재배포 필요.",
             "restart": True},
            {"name": "VERCEL_TOKEN", "label": "Vercel 토큰",
             "desc": "웹 빌더 배포용. Account Settings → Tokens에서 발급.",
             "signup_url": "https://vercel.com/account/tokens"},
        ],
    },
    "ai": {
        "label": "AI 모델 (데이터 키)",
        "entries": [
            {"name": "GEMINI_API_KEY", "label": "Google Gemini API 키",
             "desc": "아이콘 생성기·경량 작업용. Google AI Studio에서 무료 발급. 폰에도 프로비저닝됨.",
             "signup_url": "https://aistudio.google.com/apikey",
             "test": {"url": "https://generativelanguage.googleapis.com/v1beta/models?key={v}"}},
        ],
    },
    "korea_public": {
        "label": "한국 공공데이터",
        "entries": [
            {"name": "DATA_GO_KR_API_KEY", "label": "공공데이터포털 인증키",
             "desc": "data.go.kr 공통 인증키 (부동산·창업·관광 등). 활용신청한 API에서만 동작.",
             "signup_url": "https://www.data.go.kr/"},
            {"name": "MOLIT_API_KEY", "label": "국토교통부 실거래가 키",
             "desc": "부동산 실거래가 조회용 (data.go.kr에서 활용신청).",
             "signup_url": "https://www.data.go.kr/data/15058017/openapi.do"},
            {"name": "KOSIS_API_KEY", "label": "통계청 KOSIS 키",
             "desc": "KOSIS 공유서비스 → 활용신청 후 발급.",
             "signup_url": "https://kosis.kr/openapi/"},
            {"name": "LAW_API_KEY", "label": "법제처 국가법령 키",
             "desc": "국가법령정보 공동활용 신청 후 이메일 ID가 곧 키.",
             "signup_url": "https://open.law.go.kr/", "secret": False},
            {"name": "NANET_API_KEY", "label": "국회도서관 LOSI 키",
             "desc": "학술논문·연구자 검색용. losi-open에서 활용신청.",
             "signup_url": "https://losi-open.nanet.go.kr/"},
            {"name": "DATA4LIBRARY_API_KEY", "label": "도서관 정보나루 키",
             "desc": "공공도서관 도서 검색·대출 데이터.",
             "signup_url": "https://www.data4library.kr/"},
            {"name": "KOPIS_API_KEY", "label": "공연예술통합전산망 키",
             "desc": "공연 정보 조회용 (KOPIS).",
             "signup_url": "https://www.kopis.or.kr/por/main/main.do"},
            {"name": "ITS_API_KEY", "label": "국가교통정보센터 키",
             "desc": "도로 소통·CCTV 정보.",
             "signup_url": "https://openapi.its.go.kr/"},
            {"name": "UTIC_API_KEY", "label": "서울교통정보 UTIC 키",
             "desc": "도시 교통 정보 (UTIC).",
             "signup_url": "https://www.utic.go.kr/"},
        ],
    },
    "portals": {
        "label": "포털 · 지도",
        "entries": [
            {"name": "KAKAO_REST_API_KEY", "label": "카카오 REST API 키",
             "desc": "지도·역지오코딩·장소검색. developers.kakao.com → 앱 만들기 → REST API 키.",
             "signup_url": "https://developers.kakao.com/",
             "test": {"url": "https://dapi.kakao.com/v2/local/search/keyword.json?query=%EC%84%9C%EC%9A%B8",
                      "headers": {"Authorization": "KakaoAK {v}"}}},
            {"name": "NAVER_CLIENT_ID", "label": "네이버 클라이언트 ID",
             "desc": "검색·쇼핑 API용. developers.naver.com → 애플리케이션 등록.",
             "signup_url": "https://developers.naver.com/apps/", "secret": False,
             "test": {"url": "https://openapi.naver.com/v1/search/blog.json?query=test",
                      "headers": {"X-Naver-Client-Id": "{v}",
                                  "X-Naver-Client-Secret": "{NAVER_CLIENT_SECRET}"}}},
            {"name": "NAVER_CLIENT_SECRET", "label": "네이버 클라이언트 시크릿",
             "desc": "네이버 클라이언트 ID와 짝 (같은 애플리케이션 페이지).",
             "signup_url": "https://developers.naver.com/apps/"},
        ],
    },
    "finance": {
        "label": "금융 · 투자",
        "entries": [
            {"name": "DART_API_KEY", "label": "금감원 DART 키",
             "desc": "기업 공시 조회. opendart 가입 후 발급.",
             "signup_url": "https://opendart.fss.or.kr/",
             "test": {"url": "https://opendart.fss.or.kr/api/list.json?crtfc_key={v}",
                      "ok_when_absent": ["\"status\":\"010\"", "\"status\":\"011\""]}},
            {"name": "FMP_API_KEY", "label": "FMP 키",
             "desc": "해외 주식 데이터 (Financial Modeling Prep).",
             "signup_url": "https://site.financialmodelingprep.com/developer/docs",
             "test": {"url": "https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={v}"}},
            {"name": "FINNHUB_API_KEY", "label": "Finnhub 키",
             "desc": "실시간 시세 (Finnhub).",
             "signup_url": "https://finnhub.io/",
             "test": {"url": "https://finnhub.io/api/v1/quote?symbol=AAPL&token={v}"}},
        ],
    },
    "world": {
        "label": "해외 · 기타 API",
        "entries": [
            {"name": "AMADEUS_API_KEY", "label": "Amadeus API 키",
             "desc": "해외 호텔·항공 (Amadeus for Developers).",
             "signup_url": "https://developers.amadeus.com/"},
            {"name": "AMADEUS_API_SECRET", "label": "Amadeus 시크릿",
             "desc": "Amadeus API 키와 짝.",
             "signup_url": "https://developers.amadeus.com/"},
            {"name": "NINJAS_API_KEY", "label": "API Ninjas 키",
             "desc": "잡다한 유틸 API 모음.",
             "signup_url": "https://api-ninjas.com/",
             "test": {"url": "https://api.api-ninjas.com/v1/hobbies",
                      "headers": {"X-Api-Key": "{v}"}}},
            {"name": "GUARDIAN_API_KEY", "label": "가디언 뉴스 키",
             "desc": "The Guardian Open Platform.",
             "signup_url": "https://open-platform.theguardian.com/access/",
             "test": {"url": "https://content.guardianapis.com/search?api-key={v}"}},
            {"name": "WINDY_API_KEY", "label": "Windy 키",
             "desc": "날씨 지도 (Windy API).",
             "signup_url": "https://api.windy.com/"},
            {"name": "GOOGLE_BOOKS_API_KEY", "label": "Google Books 키",
             "desc": "도서 검색. Google Cloud Console에서 Books API 활성화 후 발급.",
             "signup_url": "https://console.cloud.google.com/apis/library/books.googleapis.com",
             "test": {"url": "https://www.googleapis.com/books/v1/volumes?q=test&key={v}"}},
            {"name": "CONTEXT7_API_KEY", "label": "Context7 키",
             "desc": "라이브러리 문서 검색.",
             "signup_url": "https://context7.com/"},
            {"name": "KAGGLE_API_TOKEN", "label": "Kaggle 토큰",
             "desc": "데이터셋 다운로드 (kaggle.com → Account → API).",
             "signup_url": "https://www.kaggle.com/settings"},
        ],
    },
    "identity": {
        "label": "신원 · 기기 연결",
        "entries": [
            {"name": "OWNER_EMAILS", "label": "소유자 이메일",
             "desc": "시스템이 '주인'으로 인식하는 이메일 (쉼표 구분).", "secret": False},
            {"name": "OWNER_NOSTR_PUBKEYS", "label": "소유자 Nostr 공개키",
             "desc": "Nostr 신원 (쉼표 구분).", "secret": False},
            {"name": "SYSTEM_AI_GMAIL", "label": "시스템 AI Gmail 주소",
             "desc": "시스템 AI가 발신에 쓰는 Gmail 계정.", "secret": False},
            {"name": "INDIEBIZ_PHONE_URL", "label": "폰 주소",
             "desc": "폰 IndieBiz 노드 URL.", "secret": False, "restart": True},
            {"name": "INDIEBIZ_PHONE_TOKEN", "label": "폰 토큰",
             "desc": "폰 노드 인증 토큰.", "restart": True},
            {"name": "INDIEBIZ_MAC_URL", "label": "맥 주소",
             "desc": "폰에서 맥으로 위임할 때 쓰는 URL.", "secret": False, "restart": True},
            {"name": "INDIEBIZ_MAC_PASSWORD", "label": "맥 접속 비밀번호",
             "desc": "폰→맥 위임 인증.", "restart": True},
            {"name": "INDIEBIZOS_MCP_HTTP", "label": "MCP HTTP 주소",
             "desc": "Claude Code가 붙는 MCP 서버 주소.", "secret": False, "restart": True},
        ],
    },
}


# ============================================================
# 키 → 어휘(IBL 액션) 사용처 지도 — 코드에서 파생 (하드코딩 금지)
#
# 원리: 어떤 패키지 코드가 이 env 변수를 참조하는가를 스캔하고,
# 그 파일에 같이 등장하는 도구 이름(tool.json)만 골라
# ibl_nodes.yaml의 액션으로 역추적한다. 파일 단위 귀속이라
# 같은 패키지의 무관한 어휘(예: 키 없는 날씨)는 안 걸린다.
# ============================================================

_usage_cache: Optional[Dict[str, Dict[str, Any]]] = None

_SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git"}


def _iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        if not any(part in _SKIP_DIRS for part in p.parts):
            yield p


def _short_desc(text: str) -> str:
    """액션 description 첫 문장을 짧게"""
    first = (text or "").strip().splitlines()[0] if text else ""
    first = first.split(" (")[0]
    for sep in [". ", "。"]:
        if sep in first:
            first = first.split(sep)[0]
    return first[:40]


def _service_env_map() -> Dict[str, list]:
    """auth_manager 서비스명 → env 변수들 (get_api_headers("kakao") 같은 간접 참조 귀속용)"""
    try:
        from common.auth_manager import _AUTH_REGISTRY
    except Exception:
        return {}
    out = {}
    for svc, cfg in _AUTH_REGISTRY.items():
        evs = []
        if cfg.get("env_var"):
            evs.append(cfg["env_var"])
        for container in (cfg.get("headers"), cfg.get("env_vars")):
            if isinstance(container, dict):
                evs.extend(v for v in container.values() if isinstance(v, str))
        if evs:
            out[svc] = evs
    return out


def _keys_in_text(text: str, names: set, svc_map: Dict[str, list]) -> list:
    """파일 텍스트에서 직접(리터럴) + 간접(auth_manager 서비스명) 참조된 env 키"""
    hits = {n for n in names if n in text}
    if "get_api_headers" in text or "get_auth_query_params" in text or "check_api_key" in text:
        for svc, evs in svc_map.items():
            if f'"{svc}"' in text or f"'{svc}'" in text:
                hits.update(e for e in evs if e in names)
    return list(hits)


def _build_usage_map() -> Dict[str, Dict[str, Any]]:
    """key → {actions: [{code, desc}], core_modules: [str]}"""
    names = set(_catalog_index().keys()) | set(_env_file_keys())
    svc_map = _service_env_map()
    result: Dict[str, Dict[str, Any]] = {n: {"actions": [], "core_modules": []} for n in names}

    base = ENV_PATH.parent
    data_path = _get_data_path()

    # 1) ibl_nodes.yaml: tool 이름 → [(액션 코드, 짧은 설명)]
    tool_to_actions: Dict[str, list] = {}
    try:
        nodes = yaml.safe_load((data_path / "ibl_nodes.yaml").read_text(encoding="utf-8"))["nodes"]
        for node_name, node in nodes.items():
            for action_name, action in (node.get("actions") or {}).items():
                tool = action.get("tool")
                if tool:
                    tool_to_actions.setdefault(tool, []).append(
                        {"code": f"[{node_name}:{action_name}]", "desc": _short_desc(action.get("description", ""))}
                    )
    except Exception:
        pass

    # 2) 패키지 스캔: 키가 등장하는 파일 + 그 파일에 같이 있는 도구 이름 → 액션 귀속
    pkg_roots = [data_path / "packages" / "installed" / "tools",
                 data_path / "packages" / "installed" / "extensions"]
    for root in pkg_roots:
        if not root.exists():
            continue
        for pkg_dir in sorted(root.iterdir()):
            if not pkg_dir.is_dir():
                continue
            pkg_tools = []
            tj = pkg_dir / "tool.json"
            if tj.exists():
                try:
                    import json as _json
                    pkg_tools = [t["name"] for t in _json.loads(tj.read_text(encoding="utf-8")).get("tools", [])]
                except Exception:
                    pkg_tools = []
            # 함수 단위 귀속: 키를 품은 함수 → 호출자로 전파 → 도구 이름과 교집합.
            # 함수 단위로 아무 도구도 못 찾은 키만 파일 단위 폴백(그 파일에 등장하는 도구).
            fine: Dict[str, set] = {}    # key → tool names (함수 단위, 정밀)
            coarse: Dict[str, set] = {}  # key → tool names (파일 단위, 폴백)
            pkg_texts = []
            for py in _iter_py_files(pkg_dir):
                try:
                    text = py.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                pkg_texts.append(text)
            # 패키지 전체를 하나의 함수 그래프로: 파일 경계 넘는 helper 호출도 잡는다
            segments = []  # (func_name, body_text)
            for text in pkg_texts:
                parts = re.split(r"(?m)^(?:async )?def (\w+)", text)
                for i in range(1, len(parts), 2):
                    segments.append((parts[i], parts[i + 1] if i + 1 < len(parts) else ""))
            full_text = "\n".join(pkg_texts)
            for key in _keys_in_text(full_text, names, svc_map):
                hit_funcs = {fn for fn, body in segments if _keys_in_text(body, {key}, svc_map)}
                # 호출자 전파 (2단): helper가 키를 품고 도구 함수가 helper를 부르는 경우
                for _ in range(2):
                    hit_funcs |= {fn for fn, body in segments
                                  if fn not in hit_funcs and any(h + "(" in body for h in hit_funcs)}
                # _OP_DISPATCHERS 관례: 도구 company_op의 구현 함수는 _company_op
                tools = {t for t in pkg_tools if t in hit_funcs or f"_{t}" in hit_funcs}
                if tools:
                    fine.setdefault(key, set()).update(tools)
                else:
                    for text in pkg_texts:
                        if _keys_in_text(text, {key}, svc_map):
                            # 키가 있는 파일에 등장하는 도구로 좁히되, helper 파일(도구명 없음)이면 패키지 전체
                            co = {t for t in pkg_tools if t in text} or set(pkg_tools)
                            coarse.setdefault(key, set()).update(co)
            for key in set(fine) | set(coarse):
                for t in fine.get(key) or coarse.get(key, set()):
                    for act in tool_to_actions.get(t, []):
                        if act not in result[key]["actions"]:
                            result[key]["actions"].append(act)

    # 3) 백엔드 코어 스캔: 어휘가 아닌 시스템 기능(터널·공개서빙·신원 게이트 등)에서의 사용
    backend_dir = Path(__file__).parent
    for py in list(backend_dir.glob("*.py")) + list((backend_dir / "common").glob("*.py")):
        # auth_manager는 키 등기부 자체(소비자 아님), api_env는 이 설정 UI
        if py.name in ("api_env.py", "auth_manager.py"):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for key in names:
            if key in text and py.stem not in result[key]["core_modules"]:
                result[key]["core_modules"].append(py.stem)

    for v in result.values():
        v["core_modules"] = v["core_modules"][:6]
    return result


def _get_usage_map(refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    global _usage_cache
    if _usage_cache is None or refresh:
        try:
            _usage_cache = _build_usage_map()
        except Exception:
            _usage_cache = {}
    return _usage_cache


def _catalog_index() -> Dict[str, Dict[str, Any]]:
    """name → entry(+group_key) 평탄 인덱스"""
    idx = {}
    for gkey, group in ENV_CATALOG.items():
        for e in group["entries"]:
            idx[e["name"]] = {**e, "_group": gkey}
    return idx


def _env_file_keys() -> list:
    """.env 파일에 실제로 존재하는 키 목록 (순서 보존)"""
    if not ENV_PATH.exists():
        return []
    keys = []
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.append(line.split("=", 1)[0].strip())
    return keys


def _mask(value: str, secret: bool) -> str:
    if not value:
        return ""
    if not secret:
        return value
    if len(value) >= 8:
        return "••••••••" + value[-4:]
    return "••••••••"


def _entry_payload(entry: Dict[str, Any], usage: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    name = entry["name"]
    value = _read_env_value(name)
    secret = entry.get("secret", True)
    used_by = usage.get(name, {"actions": [], "core_modules": []})
    return {
        "name": name,
        "label": entry.get("label", name),
        "desc": entry.get("desc", ""),
        "signup_url": entry.get("signup_url", ""),
        "secret": secret,
        "restart_required": entry.get("restart", False),
        "testable": "test" in entry,
        "is_set": bool(value),
        "masked": _mask(value, secret),
        "used_by": used_by,
    }


@router.get("/config/env")
def get_env_config(refresh_usage: bool = False):
    """전체 키 목록 (그룹별, 값은 마스킹, 키→어휘 사용처 포함)"""
    idx = _catalog_index()
    usage = _get_usage_map(refresh=refresh_usage)
    groups = []
    for gkey, group in ENV_CATALOG.items():
        groups.append({
            "key": gkey,
            "label": group["label"],
            "entries": [_entry_payload(e, usage) for e in group["entries"]],
        })
    # 카탈로그에 없는데 .env에 있는 키 → '기타'
    extras = [k for k in _env_file_keys() if k not in idx]
    if extras:
        groups.append({
            "key": "etc",
            "label": "기타 (.env에만 있는 키)",
            "entries": [_entry_payload({"name": k, "label": k}, usage) for k in extras],
        })
    return {"groups": groups, "env_path": str(ENV_PATH)}


@router.put("/config/env")
def put_env_value(body: Dict[str, Any]):
    """키 하나 저장. .env의 해당 줄만 교체(주석·순서 보존) + os.environ 즉시 반영."""
    name = (body.get("name") or "").strip()
    value = body.get("value")
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="키 이름은 대문자·숫자·언더스코어만 가능합니다")
    if value is None or not isinstance(value, str):
        raise HTTPException(status_code=400, detail="value(문자열)가 필요합니다")
    value = value.strip()
    if "\n" in value:
        raise HTTPException(status_code=400, detail="값에 줄바꿈은 넣을 수 없습니다")

    _write_env_value(name, value)  # os.environ 갱신 포함 → 호출 시점에 읽는 핸들러는 즉시 반영

    entry = _catalog_index().get(name, {})
    return {
        "success": True,
        "name": name,
        "is_set": bool(value),
        "masked": _mask(value, entry.get("secret", True)),
        "restart_required": entry.get("restart", False),
    }


def _render_template(template: str, name: str, value: str) -> Optional[str]:
    """테스트 스펙의 {v}·{OTHER_VAR} 치환. 참조 변수가 비어 있으면 None."""
    out = template.replace("{v}", value)
    for ref in re.findall(r"\{([A-Z][A-Z0-9_]*)\}", out):
        ref_val = _read_env_value(ref) or os.environ.get(ref, "")
        if not ref_val:
            return None
        out = out.replace("{" + ref + "}", ref_val)
    return out


@router.post("/config/env/test")
def test_env_value(body: Dict[str, Any]):
    """키 실사용 테스트 — 서비스에 가벼운 요청을 보내 인증이 통과하는지 확인."""
    name = (body.get("name") or "").strip()
    entry = _catalog_index().get(name)
    value = _read_env_value(name)
    if not value:
        return {"ok": False, "message": "값이 비어 있습니다"}
    if not entry or "test" not in entry:
        return {"ok": True, "message": "값 저장됨 (이 키는 실사용 테스트 미지원)", "tested": False}

    spec = entry["test"]
    url = _render_template(spec["url"], name, value)
    if url is None:
        return {"ok": False, "message": "짝이 되는 다른 키가 비어 있어 테스트할 수 없습니다"}
    headers = {}
    for hk, hv in spec.get("headers", {}).items():
        rendered = _render_template(hv, name, value)
        if rendered is None:
            return {"ok": False, "message": f"짝 키가 비어 있어 테스트할 수 없습니다 ({hv})"}
        headers[hk] = rendered

    try:
        resp = requests.request(spec.get("method", "GET"), url, headers=headers, timeout=8)
    except Exception as e:
        return {"ok": False, "message": f"요청 실패: {e}"}

    if resp.status_code >= 400:
        return {"ok": False, "message": f"인증 실패 (HTTP {resp.status_code})", "tested": True}
    for bad in spec.get("ok_when_absent", []):
        if bad in resp.text[:2000]:
            return {"ok": False, "message": "서비스가 키를 거부했습니다", "tested": True}
    return {"ok": True, "message": f"정상 (HTTP {resp.status_code})", "tested": True}
