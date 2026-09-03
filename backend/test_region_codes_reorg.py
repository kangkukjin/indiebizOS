"""지역 코드 카탈로그 재편 관문 — 옛 시도코드(42/45/46/29)가 되살아나지 않는다.

강원특별자치도(42→51)·전북특별자치도(45→52)·전남광주통합특별시(46/29→12, 2026-07-01)
출범으로 법정동 시도 코드가 바뀌었는데 `tool_region_codes.REGION_CODES` 는 옛 코드를 내줬다.
옛 코드는 molit 실거래 API 에서 오류가 아니라 **조용히 0건**이라 호출자가 "그 지역엔 거래가
없다"로 오독했다(부동산 발굴 보고서 실측 2026-08-12~25, real_estate.md §9).

아래 값은 2026-09-02 에 molit 아파트 매매 엔드포인트(DEAL_YMD=202607)와 네이버부동산
cortarNo 앞 5자리로 60개 코드를 전수 대조한 것이다. 전남광주는 접두어 교체가 아니라
**재번호**(광양 46230→12190, 고흥 46770→12740, 군은 12710 부터 연번, 광주 5구는 12210/12240/
12270/12300/12330)라 "46→12 로 바꾸면 된다"는 리팩터가 표를 다시 깨뜨릴 수 있어 표로 못박는다.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "data" / "packages" / "installed" / "tools" / "real-estate" / "tool_region_codes.py"

OLD_SIDO_PREFIXES = {"42", "45", "46", "29"}  # 강원(구)·전북(구)·전남(구)·광주(구)

# 현장 실측으로 확인된 대표 코드 (housing report 방법론 메모, 2026-08-12 ~ 08-25)
FIELD_VERIFIED = {
    ("강원", "원주시"): "51130",
    ("강원", "동해시"): "51170",
    ("전북", "전주시완산구"): "52111",
    ("전남", "나주시"): "12170",
    ("광주", "서구"): "12240",
}

# 2026-09-02 molit(아파트 매매 202607, 전부 1건 이상)·네이버 cortarNo 전수 대조 — 전남광주 27개
JEONNAM_GWANGJU_12 = {
    "광주": {"동구": "12210", "서구": "12240", "남구": "12270", "북구": "12300", "광산구": "12330"},
    "전남": {
        "목포시": "12110", "여수시": "12130", "순천시": "12150", "나주시": "12170", "광양시": "12190",
        "담양군": "12710", "곡성군": "12720", "구례군": "12730", "고흥군": "12740", "보성군": "12750",
        "화순군": "12760", "장흥군": "12770", "강진군": "12780", "해남군": "12790", "영암군": "12800",
        "무안군": "12810", "함평군": "12820", "영광군": "12830", "장성군": "12840", "완도군": "12850",
        "진도군": "12860", "신안군": "12870",
    },
}


def _load():
    spec = importlib.util.spec_from_file_location("tool_region_codes_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _all_codes(codes):
    return [(sido, gu, code) for sido, regions in codes.items() for gu, code in regions.items()]


def test_현장_검증_코드가_표에_있다():
    codes = _load().REGION_CODES
    for (sido, gu), expected in FIELD_VERIFIED.items():
        assert codes[sido][gu] == expected, f"{sido} {gu}: {codes[sido][gu]} != {expected}"


def test_옛_시도코드가_남아있지_않다():
    """42xxx/45xxx/46xxx/29xxx 하나라도 남으면 그 지역은 molit 에서 조용히 0건이 된다."""
    stale = [(s, g, c) for s, g, c in _all_codes(_load().REGION_CODES) if c[:2] in OLD_SIDO_PREFIXES]
    assert stale == [], f"옛 시도코드 잔존: {stale}"


def test_모든_코드는_5자리_숫자이고_중복이_없다():
    rows = _all_codes(_load().REGION_CODES)
    assert all(len(c) == 5 and c.isdigit() for _, _, c in rows)
    codes = [c for _, _, c in rows]
    assert len(codes) == len(set(codes)), "시군구 코드 중복"


def test_강원_전북은_접두어만_바뀌고_접미어는_그대로():
    codes = _load().REGION_CODES
    assert all(c.startswith("51") for c in codes["강원"].values())
    assert all(c.startswith("52") for c in codes["전북"].values())
    # 대표 접미어 — 춘천 110·전주 덕진 113 (재편 전 42110·45113 의 꼬리)
    assert codes["강원"]["춘천시"] == "51110"
    assert codes["전북"]["전주시덕진구"] == "52113"


def test_전남광주는_재번호_표와_정확히_일치():
    """접두어 교체 리팩터(46→12)가 광양·고흥·군·광주 구를 다시 깨뜨리지 못하게 표 전체를 고정."""
    codes = _load().REGION_CODES
    for sido, expected in JEONNAM_GWANGJU_12.items():
        assert codes[sido] == expected, f"{sido} 표 불일치"


def test_공개_경로가_새_코드를_낸다():
    """`[sense:realty]{op:"codes", city:"강원"}` 와 이름 자동 해소가 새 코드를 돌려준다(네트워크 불요)."""
    mod = _load()
    items = mod.get_region_codes("강원")["items"]
    assert items and all(row["코드"].startswith("51") for row in items)
    assert mod.resolve_region_code("원주시")["code"] == "51130"
    assert mod.resolve_region_code("광주 서구")["code"] == "12240"
    assert mod.resolve_region_code("나주")["code"] == "12170"


# ── 한 층 아래: 시군구 재편 (2026-09-03 수리) ─────────────────────────────
# 위 관문은 *시도* 접두어만 봤다. 그래서 한 층 아래의 재편 — 구 부활·분구·편입 — 은
# 그대로 통과했고, 부천 41190 이 카탈로그에 남아 molit 에서 조용히 0건을 냈다
# (사용자 실측 2026-09-03). 접두어 규칙으로는 영영 못 잡는 부류다.
#
# 뿌리 수리: 카탈로그를 손 표가 아니라 네이버부동산 지역 트리(현행 행정구역만 담고
# cortarNo 앞 5자리 = 법정동 시군구 코드)에서 **생성**한다 —
# tool_region_codes.refresh_region_catalog(). 아래는 그 결과가 되돌아가지 않게 하는 못이다.
ABOLISHED_SGG = {
    "41190": "경기 부천시 — 2024 원미·소사·오정구 부활",
    "41590": "경기 화성시 — 만세·효행·병점·동탄구 설치",
    "28110": "인천 중구 — 제물포·영종구로 개편",
    "28140": "인천 동구 — 제물포구로 통합",
    "28260": "인천 서구 — 서해·검단구로 분구",
    "47720": "경북 군위군 — 대구 편입(27720)",
}

CURRENT_SGG = {
    "41192": ("경기", "부천시원미구"),
    "41194": ("경기", "부천시소사구"),
    "41196": ("경기", "부천시오정구"),
    "41591": ("경기", "화성시만세구"),
    "41593": ("경기", "화성시효행구"),
    "41595": ("경기", "화성시병점구"),
    "41597": ("경기", "화성시동탄구"),
    "28125": ("인천", "제물포구"),
    "28155": ("인천", "영종구"),
    "28275": ("인천", "서해구"),
    "28290": ("인천", "검단구"),
    "27720": ("대구", "군위군"),
}


def test_폐지된_시군구코드가_카탈로그에_없다():
    live = {c for _, _, c in _all_codes(_load().REGION_CODES)}
    stale = {c: why for c, why in ABOLISHED_SGG.items() if c in live}
    assert stale == {}, f"폐지 코드 잔존(molit 에서 조용히 0건이 된다): {stale}"


def test_재편된_현행_시군구코드가_카탈로그에_있다():
    codes = _load().REGION_CODES
    for code, (sido, gu) in CURRENT_SGG.items():
        assert codes.get(sido, {}).get(gu) == code, f"{sido} {gu}({code}) 누락/불일치"


def test_씨앗표도_현행이다():
    """생성물(region_codes.json)은 .gitignore(data/**/*.json) 밖으로 안 나간다 —
    새 클론이 물려받는 것은 .py 안의 씨앗 스냅샷뿐이라, 씨앗이 낡으면 버그가 되살아난다."""
    seed = _load()._BUILTIN_REGION_CODES
    flat = {c for regions in seed.values() for c in regions.values()}
    assert not (flat & set(ABOLISHED_SGG)), f"씨앗 표에 폐지 코드: {sorted(flat & set(ABOLISHED_SGG))}"
    missing = [c for c in CURRENT_SGG if c not in flat]
    assert missing == [], f"씨앗 표에 현행 코드 누락: {missing}"


def test_관문이_부실한_수집을_거부한다():
    """수집이 반쯤 실패해도 카탈로그를 지우지 못한다(_validate_catalog)."""
    mod = _load()
    assert mod._validate_catalog({}) is not None
    assert mod._validate_catalog({"서울": {"종로구": "11110"}}) is not None       # 너무 작음
    assert mod._validate_catalog({"서울": {"종로구": 11110}}) is not None         # 5자리 문자열 아님
    assert mod._validate_catalog(mod._BUILTIN_REGION_CODES) is None


def test_생성물이_깨져도_씨앗표로_되돌아간다(tmp_path):
    mod = _load()
    broken = tmp_path / "region_codes.json"
    broken.write_text("{깨진 json", encoding="utf-8")
    mod._CATALOG_PATH = str(broken)
    mod._catalog_cache.update(mtime=None, codes=None, meta=None)
    codes, meta = mod._load_catalog()
    assert codes is mod._BUILTIN_REGION_CODES
    assert meta["source"] == "builtin" and "note" in meta


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__]))
