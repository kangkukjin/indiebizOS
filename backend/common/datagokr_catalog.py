"""datagokr_catalog.py - data.go.kr 데이터셋 카탈로그 (인증키 ↔ 활용신청 페이지)

공공데이터포털은 인증키를 계정당 하나 주지만, 권한은 **데이터셋마다 따로**
'활용신청'으로 열린다. 그래서 이 포털의 기본 실패 모양은 "키는 맞는데 403"이고,
그때 필요한 안내는 포털 첫 화면이 아니라 **그 데이터셋의 신청 페이지**다.

여기가 그 대응표의 유일한 집이다. 두 소비자가 읽는다:

  - 설정 'API 키' 탭 (surface/api_env.py) — 키마다 신청해야 할 데이터셋 목록
  - 각 도구의 401/403 메시지 (data/packages/.../tool_*.py) — 실패한 그 데이터셋 링크

옛 모양은 둘 다 손으로 적혀 있었다: 설정 탭은 데이터셋 하나(아파트 매매 상세)를
가리키는 링크 한 개였고 — 빌라를 조회하다 403 을 만난 사람에게는 쓸모가 없었다 —
도구 쪽 문구는 데이터셋 이름만 산문으로 적고 링크가 없었다. 두 자리가 같은 사실을
따로 들고 있으면 한쪽만 고쳐진다.

새 data.go.kr API 를 붙이면 여기 한 줄을 추가한다. 빠뜨리면
scripts/check_datagokr_signup.py 가 커밋을 막는다(엔드포인트는 코드에, 링크는 여기).
"""

from typing import Dict, List, Optional


def _url(dataset_id: str) -> str:
    return f"https://www.data.go.kr/data/{dataset_id}/openapi.do"


# 엔드포인트 경로(호스트 뒤 접두사) → 데이터셋.
#   env_var  이 데이터셋을 부를 때 쓰는 인증키
#   label    포털에 적힌 데이터셋 이름 (검색해서 찾을 수 있는 그대로)
#   id       data.go.kr/data/<id>/openapi.do
#   note     신청 전에 알아야 할 것 (없으면 생략)
DATASETS: List[Dict[str, str]] = [
    # ── 국토교통부 실거래가 (MOLIT_API_KEY) — 1613000, 부동산 유형마다 별개 신청 ──
    {"path": "/1613000/RTMSDataSvcAptTrade", "env_var": "MOLIT_API_KEY",
     "label": "국토교통부_아파트 매매 실거래가 자료", "id": "15126469"},
    {"path": "/1613000/RTMSDataSvcAptRent", "env_var": "MOLIT_API_KEY",
     "label": "국토교통부_아파트 전월세 실거래가 자료", "id": "15126474"},
    {"path": "/1613000/RTMSDataSvcRHTrade", "env_var": "MOLIT_API_KEY",
     "label": "국토교통부_연립다세대 매매 실거래가 자료", "id": "15126467"},
    {"path": "/1613000/RTMSDataSvcRHRent", "env_var": "MOLIT_API_KEY",
     "label": "국토교통부_연립다세대 전월세 실거래가 자료", "id": "15126473"},
    {"path": "/1613000/RTMSDataSvcSHTrade", "env_var": "MOLIT_API_KEY",
     "label": "국토교통부_단독/다가구 매매 실거래가 자료", "id": "15126465"},
    {"path": "/1613000/RTMSDataSvcSHRent", "env_var": "MOLIT_API_KEY",
     "label": "국토교통부_단독/다가구 전월세 실거래가 자료", "id": "15126472"},

    # ── 그 밖의 포털 데이터셋 (DATA_GO_KR_API_KEY) ──
    {"path": "/B553077/api/open/sdsc2", "env_var": "DATA_GO_KR_API_KEY",
     "label": "소상공인시장진흥공단_상가(상권)정보_API", "id": "15012005"},
    {"path": "/B552735/kisedKstartupService01", "env_var": "DATA_GO_KR_API_KEY",
     "label": "창업진흥원_K-Startup(사업소개,사업공고,콘텐츠 등)_조회서비스", "id": "15125364"},
    {"path": "/B553457/cultureinfo", "env_var": "DATA_GO_KR_API_KEY",
     "label": "한국문화정보원_문화정보 서비스", "id": "15138937"},
    {"path": "/B551011/KorService2", "env_var": "DATA_GO_KR_API_KEY",
     "label": "한국관광공사_국문 관광정보 서비스_GW", "id": "15101578"},
    {"path": "/1421000/mssBizService_v2", "env_var": "DATA_GO_KR_API_KEY",
     "label": "중소벤처기업부_사업공고", "id": "15113297",
     "note": "코드가 부르는 mssBizService_v2 는 폐기 추정 — 이 데이터셋이 후속(엔드포인트 갱신 필요)."},
]


def _entry_view(d: Dict[str, str]) -> Dict[str, str]:
    view = {"label": d["label"], "url": _url(d["id"])}
    if d.get("note"):
        view["note"] = d["note"]
    return view


def datasets_for(env_var: str) -> List[Dict[str, str]]:
    """이 인증키로 부르는 데이터셋들 — 각각 따로 활용신청해야 한다."""
    return [_entry_view(d) for d in DATASETS if d["env_var"] == env_var]


def lookup(url_or_path: str) -> Optional[Dict[str, str]]:
    """엔드포인트 URL(또는 경로)이 속한 데이터셋. 가장 긴 접두사가 이긴다."""
    if not url_or_path:
        return None
    path = url_or_path
    for scheme in ("https://", "http://"):
        if path.startswith(scheme):
            rest = path[len(scheme):]
            path = rest[rest.find("/"):] if "/" in rest else "/"
            break
    best = None
    for d in DATASETS:
        if path.startswith(d["path"]) and (best is None or len(d["path"]) > len(best["path"])):
            best = d
    return _entry_view(best) if best else None


def permission_error(url_or_path: str, http_code: int = 403) -> str:
    """401/403 용 표준 문구 — 그 데이터셋의 신청 링크까지 실어 보낸다.

    도구마다 손으로 적던 문장의 정본. 데이터셋 이름을 다시 타이핑하지 말 것.
    """
    ds = lookup(url_or_path)
    if not ds:
        return (f"공공데이터포털 API 권한이 없습니다({http_code}). "
                f"data.go.kr 에서 해당 데이터셋을 같은 인증키로 활용신청하세요.")
    note = f" ({ds['note']})" if ds.get("note") else ""
    return (f"'{ds['label']}' 권한이 없습니다({http_code}). "
            f"같은 인증키 그대로 활용신청만 하면 됩니다{note} → {ds['url']}")
