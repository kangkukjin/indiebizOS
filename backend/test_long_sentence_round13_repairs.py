"""Ambiguous source JSON is a located read failure, not a tool output violation."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
import pytest
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))

@pytest.mark.parametrize('content', [
    '{"x":1,"x":2}',
    '{"rows":[{"x":1,"x":2}]}',
    '{"x":1,"\\u0078":2}',
])
def test_source_duplicate_is_located_read_failure(tmp_path,registry,content):
    path=tmp_path/'source.json';path.write_text(content)
    inputs={'path':str(path)}
    plan=compile_program('[self:read]{path:$path}',registry,inputs)
    result=Runtime(plan,inputs).run()
    assert not result['success']
    error=result['diagnostic']
    assert str(path) in error['message']
    assert '중복 키' in error['message']
    assert error['details'].get('error_type')=='read'
    assert error['details'].get('error_code')!='NON_JSON_RESULT'

@pytest.mark.parametrize('value',[{'rows':[{'x':1},{'x':2}]},[0,False,None],{'nested':{'x':1},'x':2}])
def test_distinct_objects_and_zero_keep_their_values(tmp_path,registry,value):
    path=tmp_path/'source.json';path.write_text(json.dumps(value))
    inputs={'path':str(path)}
    plan=compile_program('return [self:read]{path:$path}',registry,inputs)
    result=Runtime(plan,inputs).run()
    assert result['success']
    data=result['value']['data']
    assert (data['items'] if isinstance(value,list) else data)==value

if __name__=='__main__':
    import sys
    raise SystemExit(pytest.main([__file__,*sys.argv[1:]]))
