"""최종 제출 판본과 근거 예산의 공통 계약."""
import boot_paths  # noqa: F401
from research_review import allocate, documents, claims, review_text, passage


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
    docs = documents(response, root)
    assert len(docs) == 1 and docs[0]['path'] == str(report)
    occurrences = claims(docs[0]['text'], path=docs[0]['path'], digest=docs[0]['hash'])
    assert len(occurrences) == 2 and occurrences[0]['offset'] != occurrences[1]['offset']
    assert occurrences[0]['hash'] == occurrences[1]['hash'] == docs[0]['hash']
    assert '주장2' in review_text(response, docs)
    report.write_text('변경된 판본')
    assert documents(response, root)[0]['hash'] != docs[0]['hash']


def test_long_single_paragraph_relevant_window_is_exact_slice():
    full = 'irrelevant background ' * 500 + 'control comparison denominator 1234 ' + 'other ' * 900
    quote, start = passage(full, 1600, 'control comparison denominator')
    assert 'denominator 1234' in quote
    assert full[start:start + len(quote)] == quote and len(quote) == 1600


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
