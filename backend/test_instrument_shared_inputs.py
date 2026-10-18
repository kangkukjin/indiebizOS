"""One phone selection across modes, with direct command result rendering."""
import boot_paths  # noqa: F401
from pathlib import Path
import json

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def page():
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as p:
        if not Path(p.chromium.executable_path).exists():
            pytest.skip('Playwright Chromium 미설치')
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('dialog', lambda dialog: (errors.append(dialog.message), dialog.accept()))
        yield page
        browser.close()
        assert errors == []


@pytest.mark.parametrize("instrument", ["phone_control", "living_tv"])
def test_remote_single_selection_and_direct_result(page, instrument):
    manifest = yaml.safe_load((ROOT / f'data/instruments/{instrument}.yaml').read_text())
    manifest['id'] = instrument
    for i, mode in enumerate(manifest['modes']):
        mode.update(id=str(i), edition=2)
    core = (ROOT / 'backend/static/app_render_core.js').read_text().split('/* --- ESM export')[0]
    rest = (ROOT / 'frontend/surfaces/remote/launcher_appmode_rest_js.js').read_text()
    render = (ROOT / 'frontend/surfaces/remote/launcher_render_js.js').read_text()
    execution = render[render.index('function _inpLS('):render.index('/* 작성바(compose)')]
    page.set_content('<div id="appHome"></div><div id="appInst"></div>')
    page.add_script_tag(content=core)
    page.add_script_tag(content='''
let CUR={inst:null},VIEW_CTX=null,VIEW_VARS={},SPLIT=false,LIST=null;
const API='',IS_PHONE=false,CUSTOM_RENDERERS={};
const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const initMaps=()=>{};
const renderModeBody=(mode,d)=>'<p>'+mode.name+' '+JSON.stringify(d)+'</p>';
window.calls=[];window.pending=null;window.available=['a','b'];
async function ibl(req){
 window.calls.push(req);
 if(req.code.includes('[self:limb]'))return {items:window.available.map(id=>({device_id:id,alias:'폰 '+id}))};
 return await new Promise(resolve=>{window.pending=()=>resolve({success:true,actual:4,message:'적용 확인'});});
}
''')
    page.add_script_tag(content='const INSTRUMENTS=' + json.dumps([manifest], ensure_ascii=False) + ';')
    page.add_script_tag(content=rest)
    page.add_script_tag(content=execution)
    page.evaluate('openInstrument(0)')
    page.wait_for_function("document.querySelectorAll('#in_target option').length===3")
    assert page.locator('#in_target').count() == 1
    page.evaluate("void fireButton(0,document.querySelector('#modeBody .btnrow button'))")
    assert '먼저 입력하거나 선택' in page.inner_text('#instOut')
    assert page.evaluate('window.calls.length') == 1
    page.evaluate('void runMode()')
    assert page.evaluate('window.calls.length') == 1
    page.select_option('#in_target', 'a')
    for i in [1, 2, 3, 4, 0]:
        page.evaluate(f'setMode({i})')
        assert page.input_value('#in_target') == 'a'
        assert page.locator('#modeBody #in_target').count() == 0
        assert page.evaluate('gatherInputs().target') == 'a'
    # The same list and select survive every tab; no repeated list round trips.
    assert page.evaluate('window.calls.length') == 1
    page.evaluate("document.getElementById('instOut').innerHTML='old phone result'")
    page.select_option('#in_target', 'b')
    assert page.inner_text('#instOut') == ''
    page.evaluate('setMode(1)')
    page.locator('#modeBody .btnrow button').first.click()
    page.wait_for_function('window.pending!==null')
    assert page.is_disabled('#in_target')
    assert page.evaluate('window.calls.at(-1).inputs.target') == 'b'
    page.evaluate('setMode(4)')  # Busy mode is also protected from late rendering.
    assert page.evaluate('CUR.mode.id') == '1'
    page.evaluate('window.pending()')
    page.wait_for_function("document.getElementById('instOut').textContent.includes('적용 확인')")
    assert page.evaluate('window.calls.length') == 2
    assert not page.is_disabled('#in_target')
    page.evaluate('window.pending=null; void runMode()')
    page.wait_for_function('window.pending!==null')
    assert page.is_disabled('#in_target')
    assert page.evaluate('window.calls.at(-1).inputs.target') == 'b'
    page.evaluate('window.pending()')
    page.wait_for_function("!document.getElementById('in_target').disabled")
    # Refresh removing the selected phone clears selection and its stale result.
    page.evaluate("window.available=['a'];refreshInstrumentSelects()")
    page.wait_for_function("document.querySelectorAll('#in_target option').length===2")
    assert page.input_value('#in_target') == ''
    assert page.inner_text('#instOut') == ''
    page.evaluate('openInstrument(0)')
    page.wait_for_function("document.querySelectorAll('#in_target option').length===2")
    assert page.input_value('#in_target') == ''


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
