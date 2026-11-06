"""Actual React editor: multi-file drafts survive navigation and close after save."""
import functools
import http.server
import json
from pathlib import Path
import subprocess
import threading

import pytest


@pytest.mark.system
def test_multifile_draft_navigation_rename_and_save_in_browser(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    root = Path(__file__).resolve().parents[1] / 'frontend'
    builder = tmp_path / 'build.cjs'
    output = tmp_path / 'main.js'
    builder.write_text('const esbuild=require(' + json.dumps(str(root / 'node_modules/esbuild')) + ');\n'
                       + 'const root=' + json.dumps(root.as_posix()) + ';\n'
                       + 'const output=' + json.dumps(str(output)) + ';\n' + BUNDLE)
    subprocess.run(['node', str(builder)], check=True, capture_output=True, timeout=30)
    (tmp_path / 'index.html').write_text('<meta charset="UTF-8"><div id="root"></div><script src="/main.js"></script>')
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.get_by_role('button',name='a.ts',exact=True).click()
                page.get_by_role('button',name='편집',exact=True).click()
                page.get_by_label('파일 내용').fill('export const answer = 7;\n')
                page.get_by_role('button',name='b.ts',exact=True).click()
                page.get_by_role('button',name='a.ts',exact=True).click()
                expect(page.get_by_label('파일 내용')).to_have_value('export const answer = 7;\n')
                page.get_by_role('button',name='코드 분석 열기',exact=True).click()
                page.get_by_label('새 심볼 이름').fill('result')
                page.get_by_role('button',name='이름 변경',exact=True).click()
                expect(page.get_by_label('파일 내용')).to_have_value('export const result = 7;\n')
                page.get_by_role('button',name='b.ts',exact=True).click()
                expect(page.get_by_label('파일 내용')).to_have_value('import {result} from "./a";\nresult;\n')
                page.get_by_role('button',name='초안 전체 저장',exact=True).click()
                expect(page.get_by_text('저장·기록됨',exact=True)).to_be_visible()
                assert page.evaluate('window.fixture.files["a.ts"]')=='export const result = 7;\n'
                assert page.evaluate('window.fixture.files["b.ts"]')=='import {result} from "./a";\nresult;\n'
                assert page.evaluate('window.fixture.getDraft()') is None, page.evaluate('window.fixture.getDraft()')
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


BUNDLE = r'''esbuild.buildSync({stdin:{contents:`import React from 'react'; import {createRoot} from 'react-dom/client';
import {FilesTab} from '${root}/src/components/generic/code/FilesTab';
import {analysisIO} from '${root}/src/components/generic/code/ibl';
const files={'a.ts':'export const answer = 1;\\n','b.ts':'import {answer} from "./a";\\nanswer;\\n'};
let value=null; let sequence=0;
analysisIO.servers=async()=>({items:[]});
analysisIO.draft=async(resource,body)=>{
 if(body.view && (!value || body.view!==value.view || body.expected!==value.revision)) throw Error('revision conflict');
 if(body.action==='close'){value=null; return {};}
 if(body.action==='save'){Object.assign(files,value.files);value={...value,revision:value.revision+1,files:{}};}
 else {value=value||{view:'draft-'+(++sequence),revision:0,files:{}};value={...value,revision:value.revision+1,files:{...value.files,[body.path]:body.text}};}
 return structuredClone(value);
};
const ibl={resource:'test',files:async()=>Object.keys(files).map(path=>({path,bytes:files[path].length})),file:async(path)=>({text:files[path],binary:false,lines:2}),versions:async()=>[],save:async()=>({}),
 analysis:async()=>({items:[]}),analysisPropose:async()=>({proposal:'rename'}),analysisApply:async()=>{
 value={...value,revision:value.revision+1,files:Object.fromEntries(Object.entries({...files,...value.files}).map(([p,t])=>[p,t.replaceAll('answer','result')]))};return structuredClone({...value,applied:true});}
};
window.fixture={files,getDraft:()=>value};
createRoot(document.getElementById('root')).render(<FilesTab ibl={ibl} detail={{name:'test',path:'/test'}} locked={false} onChanged={()=>{}}/>);`,loader:'tsx',resolveDir:root},bundle:true,format:'iife',jsx:'automatic',outfile:output,define:{'import.meta.env':'{}','process.env.NODE_ENV':'"development"'}});
'''
