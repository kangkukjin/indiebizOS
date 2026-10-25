"""Current each value contract; the retired implicit currency conversion is refused.

Collection with source metadata is explicit in the migrated judgment idioms and is
covered by test_ibl_edition1_retirement. These checks exercise the native loop.
"""
import importlib.util
import json
import os
import sys
import pytest
import boot_paths  # noqa: F401
from test_ibl_v2_core import adapter, run, value
from ibl_v2_ir import Fault, UNIT
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKGS = os.path.join(_ROOT, 'data/packages/installed/tools')


@pytest.mark.parametrize('rows', [[],[1],[1,2]])
@pytest.mark.parametrize('parallel', [1,3])
def test_map_preserves_one_result_per_input(rows, parallel):
    source='$rows >> [table:each]{parallel:'+str(parallel)+'}{return {value:$it}}'
    assert value(source, inputs={'rows':rows}) == [{'value':r} for r in rows]


def test_flat_map_is_explicit_and_map_does_not_flatten():
    assert value('[1,2] >> [table:each]{return [$it,$it+1]}') == [[1,2],[2,3]]
    assert value('[1,2] >> [table:each]{mode:"flat_map"}{return [$it,$it+1]}') == [1,2,2,3]


def test_unit_is_not_replaced_with_the_source_row():
    assert value('[1,2] >> [table:each]{}') == [UNIT,UNIT]
    assert value('[1,2] >> [table:each]{mode:"effect"}{return $it}') == UNIT


@pytest.mark.parametrize('parallel',[1,3])
@pytest.mark.parametrize('rows',[[1,0,2],[0,0],[]])
def test_collect_retains_error_positions_without_claiming_success(rows,parallel):
    source='$rows >> [table:each]{parallel:'+str(parallel)+',on_error:"collect"}{return 4/$it}'
    results=value(source, inputs={'rows':rows})
    assert [r.ok for r in results] == [bool(n) for n in rows]
    assert [r.value for r in results if r.ok] == [4/n for n in rows if n]
    assert all(r.error for r in results if not r.ok)


def test_stop_prevents_later_sequential_effects():
    calls=[]
    def work(rt,args):
        calls.append(args['n'])
        if args['n']==0: raise Fault('FAILED','failure')
        return args['n']
    registry={'test:work':adapter(work,{'n':'Number'},result='Number',effects=['write_external'])}
    out=run('[1,0,2] >> [table:each]{[test:work]{n:$it}}',registry=registry)
    assert not out['success'] and calls==[1,0]


def test_source_metadata_is_explicit_and_does_not_overwrite_child_value():
    source='[{city:"parent"}] >> [table:each]{$child={city:"child"};return {city:$child.city,source_city:$it.city}}'
    assert value(source)==[{'city':'child','source_city':'parent'}]


@pytest.mark.parametrize('option',['do:"return 1"','keep:["city"]','collect:true','limit:1','as:"row"'])
def test_retired_loop_options_are_not_silently_accepted(option):
    from ibl_v2_entry import handle_request
    out=handle_request({'edition':2,'code':'[1] >> [table:each]{'+option+'}{return $it}'})
    assert not out.get('success',out.get('ok',False)) and not out['executed']


@pytest.fixture(scope="module")
def dops():
    p = os.path.join(_PKGS, "data-ops", "handler.py")
    if not os.path.exists(p):
        pytest.skip("data-ops 패키지 없음")
    spec = importlib.util.spec_from_file_location("_t_dops_cc", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_t_dops_cc"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Ctx:
    def __init__(self, verb):
        self.tool_name = verb
        self.project_path = _ROOT
        self.agent_id = "test"

    def output_dir(self, name=None):
        return os.path.join(_ROOT, "outputs")


def test_C9_옛_관용구_each_flatten_은_참인_처방을_말한다(dops):
    """코퍼스가 3개월간 가르친 `each >> flatten` 이 이제 여기로 온다. "목록이 없다"만
    말하면 사용자는 field 를 고치려 든다 — 참인 처방은 **flatten 을 빼는 것**이다."""
    out = dops.execute({"_prev_result": {"items": [{"date": "d1", "max_temp": 30}]}},
                       _Ctx("data_flatten"))
    r = json.loads(out) if isinstance(out, str) else out
    assert r.get("success") is False
    assert "이미 평탄" in r["error"], r
    assert "flatten 없이 바로 이으세요" in r["error"]


def test_C10_field_를_지목한_경우는_옛_문구_그대로(dops):
    """이행 안내는 기본 field(_result)로 온 경우에만 — 진짜 중첩 목록을 펴려다 필드명을
    틀린 사람에게 'flatten 을 빼라'고 하면 그게 새 오진이다."""
    out = dops.execute({"field": "tags", "_prev_result": {"items": [{"tags": "문자열"}]}},
                       _Ctx("data_flatten"))
    r = json.loads(out) if isinstance(out, str) else out
    assert r.get("success") is False
    assert "이미 평탄" not in r["error"] and "목록을 가진 행이 없습니다" in r["error"]




if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
