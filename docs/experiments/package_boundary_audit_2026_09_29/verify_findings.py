"""Offline reproductions from source AST; no handler dispatch or external actions.

Extracted functions run against synthetic DB/browser/filesystem values. Package
modules are not imported. The real compiler/decoder are read-only boundary probes.
"""
from pathlib import Path, PurePosixPath
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import ast
import asyncio
import json
import os
from datetime import datetime
from types import SimpleNamespace as NS
from common.currency import stamp_success
from ibl_v2_adapters import decode_envelope, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault

HERE = Path(__file__).resolve().parent
TOOLS = ROOT / 'data/packages/installed/tools'


def extract(relative, name, globals_):
    path = TOOLS / relative
    tree = ast.parse(path.read_text())
    fn = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    scope = {'json':json, **globals_}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), scope)
    return scope[name]


class VirtualPath(PurePosixPath):
    def mkdir(self, *args, **kw):
        pass

    def resolve(self):
        return self

    def write_bytes(self, data):
        raise AssertionError('filesystem writes forbidden')


def main():
    results = []
    registry = load_registry()
    memory = extract('memory/handler.py', '_memory_read', {})
    db = NS(read=lambda *a: {'content':'synthetic memory','category':'','keywords':''})
    raw = memory(db, {'memory_id':1}, '/audit/project', 'audit')
    try:
        decode_envelope(stamp_success(raw), registry['self:memory'].contract['adapter'])
        raise AssertionError('expected decoder rejection')
    except Fault as fault:
        assert fault.code == 'ADAPTER_SHAPE'
        results.append({'id':'R1','case':'memory read success text','actual':fault.code,
                        'synthetic_input':True,'package_dispatch_executed':False})

    def fail_glob(*args, **kwargs):
        raise OSError('synthetic failure')
    file_find = extract('system_essentials/handler.py', '_execute', {
        '_OP_DISPATCHERS':{}, '_fs_find':NS(resolve_root=lambda *a:'/audit/project'),
        '_expand_braces':lambda p:[p], 'glob':NS(glob=fail_glob), 'os':os})
    raw = file_find({'pattern':'folder/*.txt'}, NS(tool_name='glob_files',project_path='/audit/project',agent_id='audit'))
    assert raw == '검색 오류: synthetic failure', raw
    try:
        decode_envelope(raw,registry['self:file_find'].contract['adapter'])
        raise AssertionError('expected protocol failure')
    except Fault as fault:
        assert fault.code == 'ADAPTER_SHAPE'
        results.append({'id':'R2','case':'file_find filesystem failure classified as envelope failure','actual':fault.code})

    calls = []
    async def capture(**kw):
        calls.append(kw)
    page = NS(pdf=capture, screenshot=capture)
    env = {'ensure_active':lambda:None,
           'BrowserSession':NS(get_instance=lambda:NS(raw_page=page)),
           'get_output_dir':lambda project, folder:VirtualPath(project)/'outputs'/folder,
           'datetime':datetime,'Path':VirtualPath}
    pdf = extract('browser-action/browser_content.py','browser_save_pdf',env)
    requested = '/audit/project/reports/requested.pdf'
    result = asyncio.run(pdf({'path':requested}, '/audit/project'))
    assert result['success'] and calls[-1]['path'] != requested
    results.append({'id':'P1','case':'browser PDF explicit path','requested':requested,
                    'actual':calls[-1]['path'],'file_writes':0})
    screenshot = extract('browser-action/browser_content.py','browser_screenshot',env)
    result = asyncio.run(screenshot({'path':'~workspace/reports/a.png'}, '/audit/project'))
    assert result['success'] and '/~workspace/' in calls[-1]['path']
    results.append({'id':'P2','case':'browser screenshot path dialect','actual':calls[-1]['path'],'file_writes':0})

    capture_env = {
        'os':os,'datetime':datetime, '_detect_source_type':lambda url:'image',
        '_find_ffmpeg':lambda:None,
        'get_output_dir':lambda project:str(VirtualPath(project or '/audit/workspace')/'outputs/cctv_captures'),
        '_capture_image':lambda *a:{'success':True,'file_size':1,'method':'fake'},
        'success_response':lambda **kw:kw, 'error_response':lambda message:{'error':message},
        'print':lambda *a:None}
    capture_engine = extract('cctv/capture.py','capture_cctv',capture_env)
    capture_entry = extract('cctv/handler.py','cctv_capture',{
        'load_module':lambda name:NS(capture_cctv=capture_engine)})
    result = capture_entry('https://example.invalid/frame.jpg', save_path='reports/a.jpg', project_path='/audit/project')
    assert result['file_path']=='/audit/workspace/outputs/cctv_captures/reports/a.jpg', result
    results.append({'id':'P3','case':'CCTV project argument lost before capture engine',
                    'actual':result['file_path'],'file_writes':0,'network_calls':0})

    codes = {
        'D1_play':'[limbs:music]{op:"play",mode:"client",query:"fixture"}',
        'D1_download':'[limbs:music]{op:"download",mode:"client",url:"https://example.invalid/video"}',
        'D2_resolved_during_audit_positive_control':'[others:neighbor]{op:"delete",id:1,pubkey:"npub_fixture"}',
        'D3':'[table:filter]{items:[{deposit:20000}],where:"deposit >= 20000"}',
        'D4_positive_control':'[self:photo]{start:"2026-09-01",end:"2026-09-29",has_gps:true}',
    }
    for name, code in codes.items():
        report = compile_program(code, registry).report()
        errors = [{k:i.get(k) for k in ('code','message')} for i in report['issues'] if i['severity']=='error']
        assert (not errors) if name.endswith('positive_control') else errors, (name,report)
        results.append({'id':name,'case':'compiler only','status':report['status'],'errors':errors,'executed':False})

    # Context7 is a rejected candidate: it converts a helper's error string back to
    # a failure envelope at the public search boundary.
    search = extract('context7/handler.py','_search',{'_get_docs':lambda *a:'문서 조회 실패: synthetic'})
    raw = search('fixture','/fixture/lib','fixture')
    try:
        decode_envelope(raw,registry['sense:devdocs'].contract['adapter'])
        raise AssertionError('expected TOOL failure')
    except Fault as fault:
        assert fault.code == 'TOOL'
        results.append({'id':'N1','case':'context7 helper text is wrapped','actual':fault.code,'network_calls':0})
    (HERE/'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(results)} offline probes matched source findings; no real tool actions')


if __name__ == '__main__':
    main()
