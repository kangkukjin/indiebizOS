"""변이 축 회귀 — 카탈로그 ⟨열⟩ 이 param 으로 갈리는 반환 모양을 말하는가 (2026-08-22, F20-1 판정).

배경: ⟨열⟩ 색인 키는 `node:action[#op]` 인데, 반환 열이 **op 이 아니라 param 으로**
갈리는 액션이 있다 — `[sense:realty]` 의 source=molit/naver/zigbang(molit=아파트명·
법정동·전용면적 / naver=title·name·price). 그 상태의 카탈로그는 *한 변이의 열을
전부인 양* 말하고, 뒷문장(`>> [table:compute]`)이 없는 필드를 골라 죽는다.

판정: 열 이름 정규화는 **기각**했다(열 이름=세계의 명사=관측 데이터. 몸이 이름을
붙이면 외부 API 가 바뀔 때 몸이 조용히 거짓말한다 — 헌법 '명사의 자리'. 게다가 앱
view 템플릿 `{명칭}`·`{법정동}` 과 코퍼스까지 파괴된다). 대신 **색인 키를 변이 축까지**
넓혀 변이별로 실측한다. 여기서 지키는 불변식 셋:

  ① 변이는 `shape_variants:` 선언에서만 나온다(손으로 적은 열 목록 금지 — 미봉책이
     되는 건 병기가 아니라 *손으로 적는 것*이다).
  ② 변이 fixture 는 **건강검진 우주(`fixtures`)를 넓히지 않는다** — 넓히면 외부 API 를
     매일 더 두드리고 통화·returns 스윕의 분모도 바뀐다.
  ③ 카탈로그는 변이가 있으면 반드시 그것을 인쇄한다(침묵하면 ①의 의미가 없다).
"""
import json
import os
import sys

_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
    import boot_paths  # noqa: F401 — 층 디렉토리 등재
_ROOT = os.path.dirname(_BACKEND)
_SCRIPTS = os.path.join(_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


def _nodes():
    import yaml
    return yaml.safe_load(open(os.path.join(_ROOT, "data", "ibl_nodes.yaml"), encoding="utf-8"))


# ───────── ① 선언 → 파생 ─────────

def test_declared_variants_derive_to_their_own_section():
    """`shape_variants:` 선언이 `node:action@param=값` 키로 파생된다."""
    from iblbuild_derive import derive_fixtures
    out = derive_fixtures(_nodes())
    declared = {}
    for n, nd in (_nodes().get("nodes") or {}).items():
        for a, ad in ((nd or {}).get("actions") or {}).items():
            for label, code in ((ad or {}).get("shape_variants") or {}).items():
                declared[f"{n}:{a}@{label}"] = code
    assert out["shape_variants"] == declared, "선언과 파생이 갈렸다"


def test_derived_file_on_disk_matches_declarations():
    """디스크의 ibl_fixtures.json 이 최신 선언과 일치(빌드 미실행 = 카탈로그가 옛 열을 말한다)."""
    from iblbuild_derive import derive_fixtures
    on_disk = json.load(open(os.path.join(_ROOT, "data", "ibl_fixtures.json"), encoding="utf-8"))
    assert on_disk.get("shape_variants") == derive_fixtures(_nodes())["shape_variants"]


# ───────── ② 측정 우주 불변 ─────────

def test_variants_do_not_widen_the_health_universe():
    """변이는 `fixtures`(건강검진·통화·returns 스윕의 우주)에 새지 않는다."""
    fx = json.load(open(os.path.join(_ROOT, "data", "ibl_fixtures.json"), encoding="utf-8"))
    leaked = [k for k in fx["fixtures"] if "@" in k]
    assert leaked == [], f"변이가 건강검진 우주로 샜다: {leaked}"
    assert fx.get("shape_variants"), "변이 섹션이 비었다(선언이 사라졌거나 파생이 끊겼다)"


def test_shape_sweep_reads_both_sections():
    """관측 스윕만이 두 섹션을 함께 읽는다 — 유일한 소비자."""
    src = open(os.path.join(_SCRIPTS, "ibl_shape_sweep.py"), encoding="utf-8").read()
    assert 'fx.get("shape_variants")' in src


# ───────── ③ 카탈로그 인쇄 ─────────

class _shapes:
    """관측 파일(런타임 데이터, 미추적) 대신 합성 관측으로 인쇄만 검사한다 — CI 안전."""

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        import ibl_access
        self.mod = ibl_access
        self.saved = ibl_access._return_shapes
        ibl_access._return_shapes = lambda: self.data
        return ibl_access

    def __exit__(self, *exc):
        self.mod._return_shapes = self.saved


def test_catalog_prints_variant_columns():
    with _shapes({
        "sense:realty": {"keys": ["아파트명", "법정동", "전용면적"]},
        "sense:realty@source=naver": {"keys": ["title", "name", "price"]},
        "sense:realty@source=zigbang": {"keys": ["title", "distance_m"]},
        "sense:realty#codes": {"keys": ["지역", "코드"]},
    }) as acc:
        line = acc._shape_suffix("sense:realty", None, {"default": "query"})
        assert "아파트명" in line, line
        assert "source=naver: title·name·price" in line, line
        assert "source=zigbang: title·distance_m" in line, line
        # op 줄은 자기 열만 — 변이를 op 마다 반복하면 카탈로그가 부푼다.
        op_line = acc._shape_suffix("sense:realty", "codes", {"default": "query"})
        assert op_line.strip() == "⟨열: 지역·코드⟩", op_line


def test_no_variants_means_no_change():
    """변이가 없는 액션의 줄은 옛 모양 그대로(회귀 — 카탈로그 전체가 흔들리면 안 된다)."""
    with _shapes({"sense:stock": {"keys": ["종목", "현재가"]}}) as acc:
        assert acc._shape_suffix("sense:stock", None, None) == " ⟨열: 종목·현재가⟩"


def test_legend_explains_the_pipe():
    """표기를 인쇄만 하고 범례에 안 적으면 읽는 쪽이 '|' 를 열 이름으로 읽는다."""
    import ibl_access
    assert "|" in ibl_access.CATALOG_LEGEND and "기본값의 열" in ibl_access.CATALOG_LEGEND


# ───────── 선언 가드 ─────────

def test_validator_rejects_malformed_declarations():
    from iblbuild_validators import _check_shape_variants
    base = {"returns": "items", "side_effect": False}

    ok = dict(base, shape_variants={"source=naver": '[sense:realty]{source: "naver"}'})
    assert _check_shape_variants("sense:realty", ok) == []

    bad_label = dict(base, shape_variants={"naver": '[sense:realty]{source: "naver"}'})
    assert any("라벨" in m for m in _check_shape_variants("sense:realty", bad_label))

    wrong_action = dict(base, shape_variants={"source=naver": '[sense:stock]{source: "naver"}'})
    assert any("자기 액션" in m for m in _check_shape_variants("sense:realty", wrong_action))

    no_param = dict(base, shape_variants={"source=naver": '[sense:realty]{region: "강남구"}'})
    assert any("파라미터가 없음" in m for m in _check_shape_variants("sense:realty", no_param))

    side_effect = dict(base, side_effect=True,
                       shape_variants={"source=naver": '[sense:realty]{source: "naver"}'})
    assert any("부작용" in m for m in _check_shape_variants("sense:realty", side_effect))

    effect_ret = dict(base, returns="effect",
                      shape_variants={"source=naver": '[sense:realty]{source: "naver"}'})
    assert any("통화" in m for m in _check_shape_variants("sense:realty", effect_ret))


def test_live_registry_declarations_are_clean():
    """라이브 어휘 전수 — 선언된 변이가 전부 검사를 통과한다."""
    from iblbuild_validators import _check_shape_variants
    problems = []
    for n, nd in (_nodes().get("nodes") or {}).items():
        for a, ad in ((nd or {}).get("actions") or {}).items():
            problems += _check_shape_variants(f"{n}:{a}", ad)
    assert problems == [], problems


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
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
