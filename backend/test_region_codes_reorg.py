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


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__]))
