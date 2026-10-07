"""JSON adapter argument failures identify the caller's unsupported value."""
import boot_paths  # noqa: F401
import pytest

from ibl_v2_entry import handle_request


@pytest.mark.parametrize('callback', ['($rows)=>$rows', 'len'])
def test_nested_callable_argument_is_actionable_and_catchable(callback):
    code = ('[try]{ [{k:"a",n:1}] >> [table:groupby]'
            '{by:"k",agg:{rows:' + callback + '}} }'
            '[catch]{return {code:$error.code,details:$error.details}}')
    result = handle_request({'edition': 2, 'code': code})
    assert result['success'], result
    assert result['value']['code'] == 'ARGUMENT_CONTRACT'
    assert result['value']['details']['path'] == '$args.agg.rows'
    assert result['value']['details']['actual'] == 'Callable'


def test_native_table_callback_still_runs():
    result = handle_request({'edition': 2, 'code':
        '[{n:1},{n:2}] >> [table:filter]{where:($r)=>$r.n>1}'})
    assert result['success'] and result['value'] == [{'n': 2}], result


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
