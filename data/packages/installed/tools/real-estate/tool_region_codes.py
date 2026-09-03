"""
부동산 API 지역 코드 조회 모듈
법정동 코드 앞 5자리 (시군구 코드)
"""
import json
import os
import sys
from datetime import datetime, timezone

# common 유틸리티 (카카오 키) 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))


def get_tool_definition():
    return {
        "name": "get_region_codes",
        "description": "부동산 API에서 사용하는 주요 지역 코드 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "도시명 (예: 서울, 경기, 부산). 생략시 전체 목록 반환",
                    "default": ""
                }
            },
            "required": []
        }
    }

# 씨앗 표 (법정동 코드 앞 5자리) — **정본이 아니다.**
# 정본은 옆의 생성물 region_codes.json 이고 이 표는 그것이 없거나 깨졌을 때의 폴백이다.
# 손으로 고치는 표는 반드시 다시 낡는다 — 행정구역 재편은 두 층에서 계속 일어나고,
# 폐지 코드는 molit 실거래 API 에서 오류가 아니라 **조용히 0건**이라 호출자가 '거래가 없다'로 오독한다:
#   · 시도 재편 — 강원 42→51 · 전북 45→52 · 전남광주 46/29→12(재번호)
#   · 시군구 재편 — 부천 41190→41192/41194/41196(2024 구 부활) · 화성 41590→4159x ·
#     인천 28110/28140/28260→28125/28155/28275/28290 · 군위 47720→27720(대구 편입)
# 그래서 갱신은 손이 아니라 경로가 한다: refresh_region_catalog() ([sense:realty]{op:"codes", refresh:true}).
#
# ★아래 표는 **기계가 찍은 스냅샷**이다(2026-09-03, refresh_region_catalog 출력). 손으로
#   고치지 말 것 — 한 지역만 끼워 넣으면 나머지가 조용히 낡는다. 갱신 절차는 위 refresh 를
#   돌린 뒤 생성물(region_codes.json)을 이 표로 다시 찍는 것이다. 생성물은 .gitignore
#   (data/**/*.json) 밖으로 안 나가므로, **새 클론이 물려받는 것은 이 스냅샷뿐이다.**
_BUILTIN_REGION_CODES = {
    "서울": {
        "종로구": "11110",
        "중구": "11140",
        "용산구": "11170",
        "성동구": "11200",
        "광진구": "11215",
        "동대문구": "11230",
        "중랑구": "11260",
        "성북구": "11290",
        "강북구": "11305",
        "도봉구": "11320",
        "노원구": "11350",
        "은평구": "11380",
        "서대문구": "11410",
        "마포구": "11440",
        "양천구": "11470",
        "강서구": "11500",
        "구로구": "11530",
        "금천구": "11545",
        "영등포구": "11560",
        "동작구": "11590",
        "관악구": "11620",
        "서초구": "11650",
        "강남구": "11680",
        "송파구": "11710",
        "강동구": "11740",
    },
    "경기": {
        "수원시장안구": "41111",
        "수원시권선구": "41113",
        "수원시팔달구": "41115",
        "수원시영통구": "41117",
        "성남시수정구": "41131",
        "성남시중원구": "41133",
        "성남시분당구": "41135",
        "의정부시": "41150",
        "안양시만안구": "41171",
        "안양시동안구": "41173",
        "부천시원미구": "41192",
        "부천시소사구": "41194",
        "부천시오정구": "41196",
        "광명시": "41210",
        "평택시": "41220",
        "동두천시": "41250",
        "안산시상록구": "41271",
        "안산시단원구": "41273",
        "고양시덕양구": "41281",
        "고양시일산동구": "41285",
        "고양시일산서구": "41287",
        "과천시": "41290",
        "구리시": "41310",
        "남양주시": "41360",
        "오산시": "41370",
        "시흥시": "41390",
        "군포시": "41410",
        "의왕시": "41430",
        "하남시": "41450",
        "용인시처인구": "41461",
        "용인시기흥구": "41463",
        "용인시수지구": "41465",
        "파주시": "41480",
        "이천시": "41500",
        "안성시": "41550",
        "김포시": "41570",
        "화성시만세구": "41591",
        "화성시효행구": "41593",
        "화성시병점구": "41595",
        "화성시동탄구": "41597",
        "광주시": "41610",
        "양주시": "41630",
        "포천시": "41650",
        "여주시": "41670",
        "연천군": "41800",
        "가평군": "41820",
        "양평군": "41830",
    },
    "인천": {
        "제물포구": "28125",
        "영종구": "28155",
        "미추홀구": "28177",
        "연수구": "28185",
        "남동구": "28200",
        "부평구": "28237",
        "계양구": "28245",
        "서해구": "28275",
        "검단구": "28290",
        "강화군": "28710",
        "옹진군": "28720",
    },
    "부산": {
        "중구": "26110",
        "서구": "26140",
        "동구": "26170",
        "영도구": "26200",
        "부산진구": "26230",
        "동래구": "26260",
        "남구": "26290",
        "북구": "26320",
        "해운대구": "26350",
        "사하구": "26380",
        "금정구": "26410",
        "강서구": "26440",
        "연제구": "26470",
        "수영구": "26500",
        "사상구": "26530",
        "기장군": "26710",
    },
    "대구": {
        "중구": "27110",
        "동구": "27140",
        "서구": "27170",
        "남구": "27200",
        "북구": "27230",
        "수성구": "27260",
        "달서구": "27290",
        "달성군": "27710",
        "군위군": "27720",
    },
    "광주": {
        "동구": "12210",
        "서구": "12240",
        "남구": "12270",
        "북구": "12300",
        "광산구": "12330",
    },
    "대전": {
        "동구": "30110",
        "중구": "30140",
        "서구": "30170",
        "유성구": "30200",
        "대덕구": "30230",
    },
    "울산": {
        "중구": "31110",
        "남구": "31140",
        "동구": "31170",
        "북구": "31200",
        "울주군": "31710",
    },
    "세종": {
        "세종시": "36110",
    },
    "강원": {
        "춘천시": "51110",
        "원주시": "51130",
        "강릉시": "51150",
        "동해시": "51170",
        "태백시": "51190",
        "속초시": "51210",
        "삼척시": "51230",
        "홍천군": "51720",
        "횡성군": "51730",
        "영월군": "51750",
        "평창군": "51760",
        "정선군": "51770",
        "철원군": "51780",
        "화천군": "51790",
        "양구군": "51800",
        "인제군": "51810",
        "고성군": "51820",
        "양양군": "51830",
    },
    "충북": {
        "청주시상당구": "43111",
        "청주시서원구": "43112",
        "청주시흥덕구": "43113",
        "청주시청원구": "43114",
        "충주시": "43130",
        "제천시": "43150",
        "보은군": "43720",
        "옥천군": "43730",
        "영동군": "43740",
        "증평군": "43745",
        "진천군": "43750",
        "괴산군": "43760",
        "음성군": "43770",
        "단양군": "43800",
    },
    "충남": {
        "천안시동남구": "44131",
        "천안시서북구": "44133",
        "공주시": "44150",
        "보령시": "44180",
        "아산시": "44200",
        "서산시": "44210",
        "논산시": "44230",
        "계룡시": "44250",
        "당진시": "44270",
        "금산군": "44710",
        "부여군": "44760",
        "서천군": "44770",
        "청양군": "44790",
        "홍성군": "44800",
        "예산군": "44810",
        "태안군": "44825",
    },
    "전북": {
        "전주시완산구": "52111",
        "전주시덕진구": "52113",
        "군산시": "52130",
        "익산시": "52140",
        "정읍시": "52180",
        "남원시": "52190",
        "김제시": "52210",
        "완주군": "52710",
        "진안군": "52720",
        "무주군": "52730",
        "장수군": "52740",
        "임실군": "52750",
        "순창군": "52770",
        "고창군": "52790",
        "부안군": "52800",
    },
    "전남": {
        "목포시": "12110",
        "여수시": "12130",
        "순천시": "12150",
        "나주시": "12170",
        "광양시": "12190",
        "담양군": "12710",
        "곡성군": "12720",
        "구례군": "12730",
        "고흥군": "12740",
        "보성군": "12750",
        "화순군": "12760",
        "장흥군": "12770",
        "강진군": "12780",
        "해남군": "12790",
        "영암군": "12800",
        "무안군": "12810",
        "함평군": "12820",
        "영광군": "12830",
        "장성군": "12840",
        "완도군": "12850",
        "진도군": "12860",
        "신안군": "12870",
    },
    "경북": {
        "포항시남구": "47111",
        "포항시북구": "47113",
        "경주시": "47130",
        "김천시": "47150",
        "안동시": "47170",
        "구미시": "47190",
        "영주시": "47210",
        "영천시": "47230",
        "상주시": "47250",
        "문경시": "47280",
        "경산시": "47290",
        "의성군": "47730",
        "청송군": "47750",
        "영양군": "47760",
        "영덕군": "47770",
        "청도군": "47820",
        "고령군": "47830",
        "성주군": "47840",
        "칠곡군": "47850",
        "예천군": "47900",
        "봉화군": "47920",
        "울진군": "47930",
        "울릉군": "47940",
    },
    "경남": {
        "창원시의창구": "48121",
        "창원시성산구": "48123",
        "창원시마산합포구": "48125",
        "창원시마산회원구": "48127",
        "창원시진해구": "48129",
        "진주시": "48170",
        "통영시": "48220",
        "사천시": "48240",
        "김해시": "48250",
        "밀양시": "48270",
        "거제시": "48310",
        "양산시": "48330",
        "의령군": "48720",
        "함안군": "48730",
        "창녕군": "48740",
        "고성군": "48820",
        "남해군": "48840",
        "하동군": "48850",
        "산청군": "48860",
        "함양군": "48870",
        "거창군": "48880",
        "합천군": "48890",
    },
    "제주": {
        "제주시": "50110",
        "서귀포시": "50130",
    },
}


# ── 현행 카탈로그: 생성물 + 갱신 경로 ────────────────────────────────────────
# molit 은 폐지 코드에 오류 대신 빈 목록을 주므로 '어느 코드가 살아있는지'를 스스로 말하지
# 않는다. 반면 네이버부동산 지역 트리(/api/regions/list, 키 불요)는 **현행 행정구역만** 담고
# cortarNo 앞 5자리가 곧 법정동 시군구 코드라, 이 트리가 카탈로그의 현행성 기준이 된다.
_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "region_codes.json")
_CATALOG_MIN_SIDO = 15      # 17 시도에서 통합(전남광주)·수집 실패 여유
_CATALOG_MIN_CODES = 200    # 전국 시군구 약 250
_CATALOG_STALE_DAYS = 180

_catalog_cache = {"mtime": None, "codes": None, "meta": None}


def _validate_catalog(codes):
    """생성물이 씨앗 표를 대체해도 되는가 — 부실한 수집이 카탈로그를 지우지 못하게 하는 관문.

    반환: 문제 설명 문자열(불합격) 또는 None(합격).
    """
    if not isinstance(codes, dict) or len(codes) < _CATALOG_MIN_SIDO:
        n = len(codes) if isinstance(codes, dict) else 0
        return f"시도 수 부족 ({n} < {_CATALOG_MIN_SIDO})"
    flat = [(s, g, c) for s, regions in codes.items() for g, c in (regions or {}).items()]
    if len(flat) < _CATALOG_MIN_CODES:
        return f"시군구 수 부족 ({len(flat)} < {_CATALOG_MIN_CODES})"
    bad = [f"{s} {g}={c!r}" for s, g, c in flat
           if not (isinstance(c, str) and len(c) == 5 and c.isdigit())]
    if bad:
        return f"5자리 숫자가 아닌 코드 {len(bad)}건: {bad[:5]}"
    dup = len(flat) - len({c for _, _, c in flat})
    if dup:
        return f"코드 중복 {dup}건"
    return None


def _load_catalog():
    """(codes, meta) — 생성물이 있으면 그것, 없거나 무효면 씨앗 표. 파일 mtime 으로 캐시.

    ★캐시를 mtime 에 걸어 두는 이유: refresh 로 파일만 새로 써도 같은 프로세스가
      즉시 새 표를 본다(패키지 tool_*.py 는 /packages/reload 밖이라 재기동이 필요하지만,
      **데이터 갱신은 재기동 없이** 반영되어야 갱신 경로가 실제로 쓰인다).
    """
    try:
        mtime = os.path.getmtime(_CATALOG_PATH)
    except OSError:
        return _BUILTIN_REGION_CODES, {
            "source": "builtin",
            "note": "생성 카탈로그 없음 — [sense:realty]{op:\"codes\", refresh:true} 로 현행화하세요",
        }

    if _catalog_cache["mtime"] != mtime:
        codes, meta = None, None
        try:
            with open(_CATALOG_PATH, encoding="utf-8") as f:
                blob = json.load(f)
            candidate = blob.get("codes") or {}
            problem = _validate_catalog(candidate)
            if problem:
                meta = {"source": "builtin", "note": f"생성 카탈로그가 관문 불합격이라 씨앗 표 사용: {problem}"}
            else:
                codes = candidate
                meta = {"source": "generated", "from": blob.get("from"),
                        "generated_at": blob.get("generated_at")}
        except Exception as e:  # 깨진 JSON 이 카탈로그를 통째로 죽이지 않는다
            meta = {"source": "builtin", "note": f"생성 카탈로그 읽기 실패라 씨앗 표 사용: {e}"}
        _catalog_cache.update(mtime=mtime, codes=codes, meta=meta)

    if _catalog_cache["codes"] is None:
        return _BUILTIN_REGION_CODES, dict(_catalog_cache["meta"])
    return _catalog_cache["codes"], dict(_catalog_cache["meta"])


def _catalog():
    return _load_catalog()[0]


def _catalog_meta():
    """응답에 실어 카탈로그가 자기 나이를 말하게 한다 — 조용한 0건의 첫 번째 단서."""
    meta = _load_catalog()[1]
    ts = meta.get("generated_at")
    if ts:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).days
            meta["age_days"] = age
            if age > _CATALOG_STALE_DAYS:
                meta["note"] = (f"카탈로그가 {age}일 지났습니다. 행정구역이 재편됐다면 폐지 코드는 "
                                f"오류 없이 0건이 됩니다 — refresh:true 로 현행화하세요")
        except Exception:
            pass
    return meta


def __getattr__(name):
    """옛 이름 REGION_CODES 는 늘 **현행 카탈로그**를 가리킨다 (PEP 562).

    모듈 밖(관문 테스트 등)에서 tool_region_codes.REGION_CODES 로 읽던 코드가
    씨앗 표에 굳지 않게 하는 다리. 모듈 안에서는 _catalog() 을 직접 쓴다.
    """
    if name == "REGION_CODES":
        return _catalog()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# 네이버 시도명 → 카탈로그 키. 코드가 아니라 **라벨**만 다루므로 재편이 나도 안 깨진다.
_SIDO_LABEL = {"충청북": "충북", "충청남": "충남", "경상북": "경북", "경상남": "경남"}
# 통합 시도 — 한 시도 안에 옛 두 시도가 들어 있어 카탈로그 키를 둘로 가른다.
# 가르는 기준은 이름의 구조다: 광역시 자치구는 '구'로 끝나고 '시'가 없고("서구"),
# 도의 시군은 '시'/'군'으로 끝난다("나주시"·"고흥군"). 코드를 손으로 적지 않는다.
_SIDO_SPLIT = {"전남광주": ("광주", "전남")}
_SIDO_SUFFIXES = ("특별자치도", "특별자치시", "특별시", "광역시", "자치도", "도", "시")


def _sido_key(name):
    k = (name or "").strip()
    for suf in _SIDO_SUFFIXES:
        if k.endswith(suf) and len(k) > len(suf):
            k = k[: -len(suf)]
            break
    return _SIDO_LABEL.get(k, k)


def refresh_region_catalog(save=True):
    """네이버부동산 지역 트리를 걸어 시군구 카탈로그를 현행화한다 (키 불요).

    이것이 이 모듈의 **갱신 경로**다 — 재편 지역을 손으로 끼워 넣는 대신 현행 트리를
    다시 받아 표 전체를 갈아끼운다. 관문(_validate_catalog)을 통과하지 못하면
    아무것도 쓰지 않는다(수집 실패가 카탈로그를 지우는 사고 방지).
    """
    from common.pkg_utils import load_sibling
    naver = load_sibling(__file__, "tool_naver")

    def kids(cortar_no):
        return naver._api_get("/api/regions/list", {"cortarNo": cortar_no}).get("regionList") or []

    try:
        sido_list = kids("0000000000")
    except Exception as e:
        return {"success": False, "error": f"지역 트리를 받지 못했습니다(카탈로그 변경 없음): {e}"}

    codes = {}
    for sido in sido_list:
        key = _sido_key(sido.get("cortarName"))
        split = _SIDO_SPLIT.get(key)
        try:
            children = kids(sido.get("cortarNo") or "")
        except Exception as e:
            return {"success": False, "error": f"'{key}' 하위를 받지 못했습니다(카탈로그 변경 없음): {e}"}
        for child in children:
            name = (child.get("cortarName") or "").replace(" ", "")
            code = (child.get("cortarNo") or "")[:5]
            if not name or len(code) != 5 or not code.isdigit():
                continue
            bucket = key
            if split:
                metro, province = split
                bucket = metro if (name.endswith("구") and "시" not in name) else province
            codes.setdefault(bucket, {})[name] = code

    problem = _validate_catalog(codes)
    if problem:
        return {"success": False, "error": f"수집 결과가 관문 불합격이라 카탈로그를 바꾸지 않았습니다: {problem}"}

    before = {c: f"{s} {g}" for s, regions in _catalog().items() for g, c in regions.items()}
    after = {c: f"{s} {g}" for s, regions in codes.items() for g, c in regions.items()}
    removed = sorted(f"{n}({c})" for c, n in before.items() if c not in after)
    added = sorted(f"{n}({c})" for c, n in after.items() if c not in before)

    blob = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "from": "naver land regions/list (cortarNo 앞 5자리 = 법정동 시군구 코드)",
        "codes": codes,
    }
    if save:
        tmp = _CATALOG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(blob, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, _CATALOG_PATH)  # 원자적 교체 — 반쯤 쓰인 파일을 읽는 일이 없다

    return {
        "success": True,
        "generated_at": blob["generated_at"],
        "시도": len(codes),
        "시군구": len(after),
        "사라진_코드": removed,   # 행정구역 폐지 — 그동안 조용히 0건이던 것들
        "새_코드": added,
        "saved": bool(save),
    }


def resolve_region_code(name: str):
    """지역 이름 → 법정동 5자리 시군구 코드 (내부 자동 해소용).

    "강남구"/"서울 강남구"/"청주흥덕구"/"흥덕구" 같은 시군구 이름을 코드로 바꾼다.
    실거래가 API가 시군구 단위라, 읍·면·동(예: 오송)은 직접 못 찾으므로 후보/안내를 돌려준다.

    Returns:
        {"code": "11680", "matched": "서울 강남구"}                 — 유일 매칭
        {"candidates": [{"name","code"}...], "error": "..."}       — 모호 (여러 매칭)
        {"error": "..."}                                            — 못 찾음
    """
    if not name or not str(name).strip():
        return {"success": False, "error": "지역명이 비었습니다."}
    raw = str(name).strip()
    norm = (raw.replace("특별시", "").replace("광역시", "")
               .replace("특별자치시", "").replace("특별자치도", "")
               .replace(" ", ""))

    flat = [(sido, gu, code) for sido, regions in _catalog().items()
            for gu, code in regions.items()]

    matched = {}  # code -> "시도 시군구"
    for sido, gu, code in flat:
        full = sido + gu  # 예: "서울강남구", "충북청주시흥덕구"
        # norm in full: "강남"·"분당"·"흥덕구" 같은 부분/접미 매칭 허용.
        # (gu in norm은 금지 — "남구"가 "강남구"의 부분문자열이라 강남구가 모든 남구에 오매칭됨)
        if norm == gu or norm == full or norm in full:
            matched[code] = f"{sido} {gu}"

    if len(matched) == 1:
        code = next(iter(matched))
        return {"code": code, "matched": matched[code]}
    if len(matched) > 1:
        return {
            "success": False,
            "candidates": [{"name": n, "code": c} for c, n in matched.items()][:12],
            "error": f"'{raw}'가 여러 시군구와 일치합니다. region_code로 지정하거나 시/도를 함께 적으세요 (예: '서울 중구').",
        }

    # 로컬 시군구 테이블에 없음 → 카카오 지오코딩으로 읍·면·동을 상위 시군구로 자동 해소
    via = _resolve_via_kakao(raw)
    if via:
        return via

    return {
        "success": False,
        "error": (f"'{raw}'에 해당하는 시군구를 찾지 못했습니다. 실거래가는 시군구 단위입니다 "
                  f"(예: 강남구, 청주시흥덕구). 시군구 이름으로 다시 시도하세요. "
                  f"district_codes로 목록을 확인할 수 있습니다.")
    }


def _resolve_via_kakao(name: str):
    """카카오 주소검색으로 임의 지명 → 시군구 코드. 법정동코드(b_code) 앞 5자리가 시군구 코드.

    읍·면·동(예 '오송')처럼 로컬 시군구 테이블에 없는 하위 지명을 상위 시군구로 자동 변환한다.
    카카오 키 없거나 결과 없으면 None.
    """
    try:
        from common.auth_manager import get_api_key
        key = get_api_key('KAKAO_REST_API_KEY')
        if not key:
            return None
        import urllib.request
        import urllib.parse
        import json as _json
        url = "https://dapi.kakao.com/v2/local/search/address.json?" + urllib.parse.urlencode(
            {"query": name, "size": 5})
        req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {key}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read().decode("utf-8"))
        for doc in data.get("documents", []):
            addr = doc.get("address") or {}
            b = (addr.get("b_code") or "")
            if len(b) >= 5 and b[:5].isdigit():
                sido = (addr.get("region_1depth_name") or "").strip()
                sgg = (addr.get("region_2depth_name") or "").strip()
                emd = (addr.get("region_3depth_name") or "").strip()
                return {
                    "code": b[:5],
                    "matched": f"{sido} {sgg}".strip(),
                    "via": emd or name,  # 어떤 읍·면·동을 상위 시군구로 올렸는지
                }
    except Exception:
        return None
    return None


def get_region_codes(city: str = "", refresh: bool = False):
    """
    지역 코드 조회

    Args:
        city: 도시명 (빈 문자열이면 전체 반환)
        refresh: True 면 먼저 카탈로그를 현행화한다 (네이버 지역 트리, 키 불요)

    Returns:
        dict: 지역 코드 목록 + catalog(출처·생성시각·나이)
    """
    refreshed = refresh_region_catalog() if refresh else None
    codes = _catalog()
    meta = _catalog_meta()

    if city:
        city_normalized = city.replace("특별시", "").replace("광역시", "").replace("시", "").replace("도", "").strip()

        for key in codes:
            if city_normalized in key or key in city_normalized:
                # items 통화 — >> 파이프(take/filter/each)로 흐른다.
                # (dict 만 내던 시절 `[sense:realty]{op:"codes"} >> [table:take]` 가
                #  ep1116·1334 에서 같은 문장으로 두 번 단절 — 2026-08-21 수리)
                out = {
                    "success": True,
                    "city": key,
                    "items": [{"지역": name, "코드": code} for name, code in codes[key].items()],
                    "count": len(codes[key]),
                    "catalog": meta,
                }
                if refreshed:
                    out["refreshed"] = refreshed
                return out

        return {
            "success": False,
            "error": f"'{city}'에 해당하는 지역을 찾을 수 없습니다. 지원 도시: {', '.join(codes.keys())}",
            "catalog": meta,
        }

    # 전체 목록 — 시/도 단위 items (구/군까지 펼치려면 city 지정)
    items = [{"시도": city_name, "구군수": len(regions)} for city_name, regions in codes.items()]
    out = {
        "success": True,
        "total_cities": len(codes),
        "items": items,
        "catalog": meta,
        "usage": "특정 도시의 전체 코드를 보려면 city 파라미터에 도시명을 입력하세요. (예: 서울, 경기, 부산)"
    }
    if refreshed:
        out["refreshed"] = refreshed
    return out
