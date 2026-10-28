"""Optional display metadata must not change an already completed dispatch."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest

from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/experiments/long_sentence_imagination/round_104/report_fixed.ibl'


@pytest.mark.parametrize('metadata,expected', [
    ({}, 'L2'), ({'label': None}, 'L2'), ({'label': ''}, 'L2'),
    ({'label': '동네 도서관'}, '동네 도서관'),
])
def test_optional_label_fallback_keeps_dispatch_receipt_and_cost(metadata, expected):
    args = {
        'lib': {'id': 'L2', **metadata},
        'lines': [{'item': 'K', 'cost': 282}],
        'cost': 282, 'ready': True,
        'receipt': {'receipt': 'already-written', 'path': 'dispatch.jsonl'},
    }
    code = SOURCE.read_text() + '\nreturn [fn:LS102Report]{lib:$lib,lines:$lines,cost:$cost,ready:$ready,receipt:$receipt}'
    result = Runtime(compile_program(code, {}, inputs=args), inputs=args).run()
    assert result['success'], result
    assert result['value'] == {
        'library': 'L2', 'label': expected, 'lines': args['lines'],
        'total_cost': 282, 'ready': True, 'receipt': args['receipt'],
    }


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
