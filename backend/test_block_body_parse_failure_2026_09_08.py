"""블록 본문 실패를 빈 분기의 성공으로 숨기지 않는다(실제 보고서 재현)."""
import pytest

import boot_paths  # noqa: F401
from ibl_parser import IBLSyntaxError, parse


@pytest.mark.parametrize("code", [
    '[if: 1 == 1]{[table:take]{n:1} >> 이것은문장이아니다}',
    '[if: 1 == 2]{[table:take]{n:1}} [else]{[table:take] >> 잘못된문장}',
    '[case: self:time]{default: [if: 1 == 1]{[table:take] >> 잘못된문장}}',
    '[if: 1 == 1]{[if: 2 == 2]{[table:take] >> 잘못된문장}}',
])
def test_invalid_nonempty_branch_is_a_syntax_error(code):
    with pytest.raises(IBLSyntaxError, match="블록 본문 해석 실패"):
        parse(code)


def test_report_guard_cannot_discard_unparsed_outer_variable_pipeline():
    # 현 파서의 블록 외부 변수 파이프 지원 공백이다. 이 시험은 그 기능이
    # 구현됐다고 주장하지 않으며, 본문을 버린 성공만 금지한다.
    code = ('$자료 = [table:take]{items:[{id:1}],n:1}; '
            '[if: count($자료.items) == 1]{'
            '$델타 = $자료 >> [table:take]{n:1}; '
            '$델타 >> [self:write]{path:"outputs/never_written.json",format:"json"}}')
    with pytest.raises(IBLSyntaxError, match="블록 본문 해석 실패"):
        parse(code)


def test_explicit_empty_branch_remains_empty():
    step = parse('[if: 1 == 1]{}')[0]
    assert step["branches"][0]["action"] is None


def test_valid_branch_keeps_its_write_action():
    step = parse('[if: 1 == 1]{[self:write]{path:"outputs/a.txt",content:"ok"}}')[0]
    assert step["branches"][0]["action"]["action"] == "write"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
