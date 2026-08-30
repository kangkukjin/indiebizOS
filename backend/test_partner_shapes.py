"""동반 낱말(⟨동반⟩) 회귀 — 카탈로그가 실측 조합 파트너를 말하는가 (2026-08-30).

배경: 상시 카탈로그 148줄에 조합 정보가 한 글자도 없었다 — ⟨열⟩(반환)·⟨인자⟩(입력)까지
관측으로 채우고 정작 *이웃*만 비어 있어서 낱말이 저마다 섬으로 제시됐다. 문장이 모델에 닿는
통로는 문법 프롬프트 예문 29개(등장 32/148)와 회상 top-3(조합 20.1%)뿐이라 116 낱말은 문장
안에 있는 모습을 본 적이 없다. 실측: 낱말별 '교재 조합 노출률→실행 조합률' r=0.72.

`scripts/ibl_partner_sweep.py` 가 교재·실행에서 *이어진 흔적* 을 세어 `data/ibl_partners.json`
에 적고, ibl_access 가 ⟨동반: >>a · &b⟩ 로 붙인다. 지키는 불변식:

  ① 파트너는 손으로 적지 않는다 — 관측 파일만이 원천(스크립트가 파생물임을 선언).
  ② 자기 자신으로 가는 `>>` 는 동반이 아니라 **접힐 수 있었던 자리**다 — 싣지 않는다
     (광고하면 반복을 권장하게 된다). 같은 액션의 `&` 병렬은 그 반복을 접은 모양이라 남긴다.
  ③ 범례가 '없음 = 관측 없음이지 조합 불가가 아니다' 를 말한다 — 안 적으면 빈 줄이
     '이 낱말은 조합 못 한다'는 처방으로 읽힌다(섬을 굳히는 정반대 효과).
  ④ 독립 문장(줄바꿈·`;`)은 사슬이 아니다 — `_seq_boundary` 에서 끊는다.
  ⑤ 관측 파일이 없으면 카탈로그는 옛 모양 그대로(회귀 안전).
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
    import boot_paths  # noqa: F401
_ROOT = os.path.dirname(_BACKEND)
_SCRIPTS = os.path.join(_ROOT, "scripts")


class _partners:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        import ibl_access
        self.mod = ibl_access
        self.saved = (ibl_access._partners, dict(ibl_access._PARTNER_CACHE))
        ibl_access._partners = lambda: self.data
        return ibl_access

    def __exit__(self, *exc):
        self.mod._partners = self.saved[0]
        self.mod._PARTNER_CACHE.clear()
        self.mod._PARTNER_CACHE.update(self.saved[1])


def test_action_line_prints_observed_partners():
    with _partners({"sense:realty": {"n": 40, "top": [[">>table:filter", 12], ["&같은액션", 5]]}}) as acc:
        assert acc._partner_suffix("sense:realty") == " ⟨동반: >>table:filter · &같은액션⟩"


def test_no_observation_means_no_change():
    """⑤ 관측이 없으면 빈 문자열 — 옛 카탈로그와 바이트 동일."""
    with _partners({}) as acc:
        assert acc._partner_suffix("sense:realty") == ""
        assert acc._partner_suffix("others:publish") == ""


def test_legend_says_absence_is_not_prohibition():
    """③ 범례가 '없음=관측 없음' 과 items→table 규칙을 한 번 말한다(줄마다 전개하지 않는다)."""
    import ibl_access
    assert "⟨동반" in ibl_access.CATALOG_LEGEND
    assert "관측 없음" in ibl_access.CATALOG_LEGEND
    assert "table:*" in ibl_access.CATALOG_LEGEND


def test_sweep_excludes_self_pipe_but_keeps_self_parallel():
    """② 자기→자기 `>>` 는 접힐 자리(제외), 같은 액션의 `&` 는 접은 모양(유지)."""
    sys.path.insert(0, _SCRIPTS)
    import collections
    from ibl_partner_sweep import _collect
    from ibl.ibl_parser import parse

    pairs = collections.defaultdict(collections.Counter)
    _collect(parse('[limbs:browser]{op: "click"} >> [limbs:browser]{op: "type"}'), pairs, parse)
    assert ">>limbs:browser" not in pairs["limbs:browser"]

    pairs = collections.defaultdict(collections.Counter)
    _collect(parse('[sense:stock]{op: "quote", ticker: "A"} & [sense:stock]{op: "quote", ticker: "B"}'),
             pairs, parse)
    assert pairs["sense:stock"]["&같은액션"] == 1, "같은 사건은 한 표 — 가지마다 세면 자기병렬이 부풀어 `>>` 파트너를 밀어낸다"

    pairs = collections.defaultdict(collections.Counter)
    _collect(parse('[sense:stock]{ticker: "A"} & [sense:stock]{ticker: "B"} & [sense:stock]{ticker: "C"}'),
             pairs, parse)
    assert pairs["sense:stock"]["&같은액션"] == 1


def test_sweep_does_not_chain_across_independent_statements():
    """④ 줄바꿈으로 나뉜 두 문장은 이어진 게 아니다 — 사슬을 끊지 않으면 거짓 동반이 생긴다."""
    sys.path.insert(0, _SCRIPTS)
    import collections
    from ibl_partner_sweep import _collect
    from ibl.ibl_parser import parse

    pairs = collections.defaultdict(collections.Counter)
    _collect(parse('[self:patch]{path: "a"}\n[sense:search]{query: "b"} >> [table:filter]{where: "c"}'),
             pairs, parse)
    assert ">>sense:search" not in pairs["self:patch"]
    assert pairs["sense:search"][">>table:filter"] == 1


def test_sweep_counts_sentences_inside_each_do():
    """`[table:each]{do: "…"}` 의 do 는 문자열에 담긴 진짜 문장이다 — 안 세면 고차 조합이 통째로 안 보인다."""
    sys.path.insert(0, _SCRIPTS)
    import collections
    from ibl_partner_sweep import _collect
    from ibl.ibl_parser import parse

    pairs = collections.defaultdict(collections.Counter)
    _collect(parse('[table:each]{items: [{a: 1}], do: "[sense:realty]{region: \'$it.a\'} >> [table:take]{n: 2}"}'),
             pairs, parse)
    assert pairs["sense:realty"][">>table:take"] == 1


def test_sweep_declares_derived_and_reports_observation_limits():
    """① 파생물 선언 + 깨짐≠없음(절단·파싱 실패·카탈로그 밖 이름을 신고)."""
    src = open(os.path.join(_SCRIPTS, "ibl_partner_sweep.py"), encoding="utf-8").read()
    assert "직접 수정 금지" in src and "GENERATED" in src
    assert "parse_fail" in src and "truncated" in src and "unknown_actions" in src
    assert "_known_actions" in src, "카탈로그 밖(은퇴·환각) 이름은 싣지 않는다"


def test_weekly_cadence_registered():
    """관측은 굳으면 처방이 된다 — 주간 재관측이 없으면 오늘의 습관이 화석이 된다."""
    fx = open(os.path.join(_BACKEND, "cognition", "fixture_sweeps.py"), encoding="utf-8").read()
    assert "def run_partner_sweep" in fx and "ibl_partner_sweep_state.json" in fx
    assert "run_all_sweeps" in fx and '"partner_sweep"' in fx, "주간 묶음(run_all_sweeps)에 등재"
    wp = open(os.path.join(_BACKEND, "cognition", "world_pulse_health.py"), encoding="utf-8").read()
    assert "run_all_sweeps" in wp, "유지보수 번들이 스윕 묶음을 부른다"
    own = open(os.path.join(_BACKEND, "cognition", "data_ownership.py"), encoding="utf-8").read()
    assert "data/ibl_partners.json" in own and "ibl_partner_sweep_state.json" in own


if __name__ == "__main__":                      # 러너는 하나 — pytest
    import pytest
    raise SystemExit(pytest.main([__file__] + __import__("sys").argv[1:]))
