"""Explicit text must bypass extension-based JSON parsing of unfinished drafts."""
import boot_paths  # noqa: F401
from pathlib import Path
import pytest
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))

def read(registry,path,fmt=None):
    inputs={'path':str(path)}
    code='return [self:read]{path:$path'+(',format:$format}' if fmt else '}')
    if fmt:inputs['format']=fmt
    plan=compile_program(code,registry,inputs)
    assert not plan.issues
    return Runtime(plan,inputs).run()

@pytest.mark.parametrize('extension',['json','JSON','txt'])
@pytest.mark.parametrize('body',['{"draft":\n// TODO fix\n','{"x":1}\n'])
def test_explicit_text_preserves_body_without_structured_data(tmp_path,registry,extension,body):
    path=tmp_path/f'draft.{extension}';path.write_text(body)
    result=read(registry,path,'text')
    assert result['success'],result.get('diagnostic')
    assert result['value']['text']==body
    assert 'x' not in result['value']['data']

@pytest.mark.parametrize('extension,fmt',[('json',None),('JSON',None),('txt','json')])
def test_automatic_and_explicit_json_still_parse(tmp_path,registry,extension,fmt):
    path=tmp_path/f'data.{extension}';path.write_text('{"x":0}')
    result=read(registry,path,fmt)
    assert result['success'] and result['value']['data']=={'x':0}
    path.write_text('{"x":')
    failed=read(registry,path,fmt)
    assert not failed['success'] and 'JSON 원문 오류' in failed['diagnostic']['message']

if __name__=='__main__':
    import sys
    raise SystemExit(pytest.main([__file__,*sys.argv[1:]]))
