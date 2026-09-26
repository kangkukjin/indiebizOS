"""반사 규칙 모순 수리(2026-09-26).

자격(corpus_policy.exclusion_reason: 판본 1 = legacy_source)과 노출(hippo_tree.reference_needs_expansion: 판본 2 = 항상 숨김)이
서로의 여집합을 걸러 `_top_for_execution` 이 어떤 용례에도 코드를 내주지 않았다 — 반사(해마 ≥ 0.85) 후보 0건, 귀속
(record_recall_outcome)도 0건. 정본: docs/REFLEX_RULES_CONTRADICTION_REPAIR_2026_09_26.md
"""
import boot_paths  # noqa: F401
import pytest

from cognitive_consciousness import CognitiveConsciousnessMixin
from corpus_policy import exclusion_reason
from hippo_tree import reference_needs_expansion, sentence_count, split_sentences
from ibl_usage_db import UsageExample
from ibl_usage_rag import _top_for_execution

ONE = '#!ibl edition=2\nreturn [sense:weather]{city: "서울"}'
MANY = ('#!ibl edition=2\n$기준=5\n$목록=[{id:"007",score:7}]\n'
        '$목록 >> [table:filter]{where:($행)=>$행.score >= $기준}')
DEF = ('#!ibl edition=2\n[def:열추려보기]($목록,$열,$개수){\n'
       '  $목록 >> [table:select]{columns:$열} >> [table:take]{n:$개수}\n}')
LONG = '#!ibl edition=2\nreturn "' + 'x' * 1200 + '"'
LEGACY = '[sense:weather]{city: "서울"}'


def _ex(id_, code, score=.9):
    return UsageExample(id_, '서울 날씨', code, 'sense', 'single', 1, score, 'fixture', -1)


def test_current_single_statement_passes_both_gates():
    assert exclusion_reason({'ibl_code': ONE}) is None
    assert not reference_needs_expansion(ONE)
    assert _top_for_execution([_ex(1, ONE)]) == (.9, ONE)


@pytest.mark.parametrize('code', [MANY, LONG])
def test_current_multi_statement_or_long_is_hidden(code):
    assert exclusion_reason({'ibl_code': code}) is None
    assert reference_needs_expansion(code)
    assert _top_for_execution([_ex(2, code)]) == (.8, '')


def test_legacy_stays_historical():
    assert exclusion_reason({'ibl_code': LEGACY}) == 'legacy_source'
    assert not reference_needs_expansion(LEGACY)            # 노출 규칙은 판본을 모른다 — 자격 규칙이 거른다
    assert _top_for_execution([_ex(3, LEGACY)]) == (.8, '')


def test_sentence_count_is_edition_aware_and_split_sentences_is_untouched():
    assert (sentence_count(ONE), sentence_count(MANY), sentence_count(DEF)) == (1, 3, 1)
    assert sentence_count(LEGACY) == 1 and sentence_count('[a:b]{}; [c:d]{}') == 2
    assert split_sentences(MANY) == [MANY]                   # 증류·관용구 기계의 전제(test_ibl_v2_assets) 그대로
    broken = '#!ibl edition=9\nreturn 1'
    assert sentence_count(broken) == 0 and reference_needs_expansion(broken)


def test_reflex_fires_for_current_single_statement_and_vetoes_keep_shape():
    c = object.__new__(CognitiveConsciousnessMixin)
    assert c._decide_request_type('오늘 서울 날씨 좀', .9, ONE) == ('EXECUTE', ONE)
    # 위험 축 거부권 — 키 표기와 무관
    for code in ('[self:switch]{op: "deploy"}', '#!ibl edition=2\nreturn [self:site]{"op":"deploy","target":"prod"}',
                 "[self:build]{op:'build'}"):
        assert c._reflex_veto('올려줘', code) == "빌드·배포 등 되돌리기 어려운 작업"
    assert c._reflex_veto('보고서 만들어줘. 끝나면 보내줘', ONE)          # 요구 여럿
    assert c._reflex_veto('x', '[a:b]{} >> [c:d]{}') == "회상이 다단계 파이프라인"
    assert c._reflex_veto('오늘 서울 날씨 좀', ONE) is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
