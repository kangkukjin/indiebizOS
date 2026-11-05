"""최종 제출 판본과 근거 예산의 공통 계약."""
import boot_paths  # noqa: F401
from research_review import allocate, submission_paths, claims, review_text, passage


def test_short_evidence_redistributes_without_order_dependence():
    lengths = {'short': 10, **{str(n): 3000 for n in range(10)}}
    quotas = allocate(lengths)
    assert sum(quotas.values()) == 16000 and quotas['short'] == 10
    assert min(v for k, v in quotas.items() if k != 'short') >= 1599
    assert quotas == allocate(dict(reversed(list(lengths.items()))))
    assert allocate({'empty': 0}) == {'empty': 0}
    assert passage('확보된 원문', 0, '원문') == ('', 0)


def test_explicit_submission_only_and_duplicate_claim_locations(tmp_path):
    root = tmp_path / 'project'; root.mkdir()
    outputs = root / 'outputs'; outputs.mkdir()
    outside = tmp_path / 'secret.md'; outside.write_text('외부')
    (outputs / 'linked.md').symlink_to(outside)
    report = outputs / 'report.md'
    report.write_text('주장1 [자료:version:p1]\n주장2 [자료:version:p1]')
    response = f'[보고서](outputs/report.md) [외부]({outside}) [링크](outputs/linked.md)'
    assert submission_paths(response, root) == {str(report)}
    body = report.read_text()
    occurrences = claims(body, path=str(report), digest='revision')
    assert len(occurrences) == 2 and occurrences[0]['offset'] != occurrences[1]['offset']
    assert occurrences[0]['hash'] == occurrences[1]['hash'] == 'revision'
    assert '주장2' in review_text(response, [{'path': str(report), 'hash': 'revision', 'text': body}])


def test_long_single_paragraph_relevant_window_is_exact_slice():
    full = 'irrelevant background ' * 500 + 'control comparison denominator 1234 ' + 'other ' * 900
    quote, start = passage(full, 1600, 'control comparison denominator')
    assert 'denominator 1234' in quote
    assert full[start:start + len(quote)] == quote and len(quote) == 1600


def test_disjoint_explicit_definition_and_limit_keep_exact_coordinates():
    from research_review import passages
    definition = '모형의 성분 값이며 전체 경제 관측치가 아니다.'
    limitation = '해당 값은 다른 기간이나 집단에 적용할 수 없다.'
    full = definition + ' 배경' * 4000 + limitation
    ranges = passages(full, 1200, [], [definition, limitation])
    assert len(ranges) == 2 and sum(end - start for start, end in ranges) <= 1200
    assert any(definition in full[start:end] for start, end in ranges)
    assert any(limitation in full[start:end] for start, end in ranges)
    assert ranges == passages(full, 1200, [], [definition, definition, limitation])


def test_ai_usage_selection_cannot_create_a_nonexistent_source():
    import pytest
    from research_review import citation_uses
    occurrences = claims('예시 [자료:판본:위치]. 실제 근거 [자료:v:p1]. 잘못된 근거 [자료:v:p9]')
    uses, invalid = citation_uses('CITATION_USES: [{"index":0,"use":"example"},'
        '{"index":1,"use":"source"},{"index":2,"use":"source"}]', occurrences,
        [{'citation': '[자료:v:p1]'}])
    assert [r['citation'] for r in invalid] == ['[자료:v:p9]']
    assert uses[0]['use'] == 'example'
    for bad in ('', 'CITATION_USES: []', 'CITATION_USES: [{"index":true,"use":"source"}]'):
        with pytest.raises(ValueError):
            citation_uses(bad, occurrences, [])


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
