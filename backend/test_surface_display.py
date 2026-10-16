"""표시 코드/DOM 교체가 최신 초안과 실행 호스트 수명을 보존하는지 검사한다."""
import boot_paths  # noqa: F401
import json

import pytest
from playwright.sync_api import sync_playwright
from member_shell import member_html
from surface_assets import source_build
from surface_display import member_display


@pytest.fixture
def display_page(tmp_path):
    with source_build():
        html = member_html()
        descriptor = member_display(member_html(display=False), 'member')
    path = tmp_path / 'member.html'
    path.write_text(html)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('''window.polls=0;window.commands=[];
        window.DesktopMember={request:async(path,body)=>{
          if(path==='tasks'){window.polls++;return []}
          if(['approvals','media','results'].includes(path))return [];
          if(path==='apps')return {instruments:[],dictionary:[]};
          if(path==='workspace')return {workspace:'/test'};
          window.commands.push({path,body});return {success:true};
        }};''')
        page.goto(path.as_uri())
        page.wait_for_function('window.IndieDisplay && window.polls > 0')
        yield page, descriptor, errors
        browser.close()


def candidate(descriptor):
    result = dict(descriptor)
    result['version'] = 'test-next'
    result['code'] = result['code'].replace('새 세션', '새 대화 시작')
    result['styles'] = [s + '\n#newTask{border-radius:3px}' for s in result['styles']]
    result['code'] = result['code'].replace("return label[v.type]||label[e.type]||''", "return '새 표시 코드'")
    return result


def test_display_swap_preserves_live_dom_and_runtime(display_page):
    page, initial, errors = display_page
    page.locator('#message').fill('입력 중인 최신 초안')
    page.evaluate('''() => {
      document.getElementById('fileEditor').value='저장 전 파일';
      document.getElementById('message').setSelectionRange(2,5);
      window.savedFrame=document.getElementById('appFrame');
      window.savedWindow=savedFrame.contentWindow;
      window.savedAudio=document.getElementById('memberAudio');
      window.savedRequest=memberRequest;window.beforeCommands=commands.length;
    }''')
    result = page.evaluate('(value)=>IndieDisplay.apply(value)', candidate(initial))
    assert result['version'] == 'test-next'
    assert page.locator('#newTask').inner_text() == '＋ 새 대화 시작'
    assert page.locator('#message').input_value() == '입력 중인 최신 초안'
    assert page.evaluate("document.getElementById('fileEditor').value") == '저장 전 파일'
    assert page.evaluate("document.getElementById('message').selectionStart") == 2
    assert page.evaluate("savedFrame===document.getElementById('appFrame')&&savedWindow===savedFrame.contentWindow")
    assert page.evaluate("savedAudio===document.getElementById('memberAudio')&&savedRequest===memberRequest")
    assert page.evaluate('memberProgressText({})') == '새 표시 코드'
    assert page.evaluate('commands.length===beforeCommands')
    assert not errors, errors


def test_composition_wait_uses_latest_input(display_page):
    page, initial, errors = display_page
    page.evaluate("document.getElementById('message').dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}))")
    page.evaluate('(value)=>{window.install=IndieDisplay.apply(value);window.installed=false;install.then(()=>installed=true)}', candidate(initial))
    page.locator('#message').fill('준비 중 새로 입력한 초안')
    assert not page.evaluate('installed')
    page.evaluate("document.getElementById('message').dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}))")
    page.wait_for_function('installed')
    assert page.locator('#message').input_value() == '준비 중 새로 입력한 초안'
    assert not errors, errors


def test_failed_dom_handoff_restores_code_and_view(display_page):
    page, initial, errors = display_page
    broken = candidate(initial)
    # Node type is incompatible, but the pinned input still exists: fail during commit.
    broken['template'] = broken['template'].replace('<textarea id="message"', '<input id="message"')
    page.locator('#message').fill('실패 뒤에도 남을 초안')
    result = page.evaluate('async value=>{try{await IndieDisplay.apply(value);return "accepted"}catch(e){return e.message}}', broken)
    assert result != 'accepted'
    assert page.locator('#newTask').inner_text() == '＋ 새 세션'
    assert page.locator('#message').input_value() == '실패 뒤에도 남을 초안'
    assert page.evaluate('IndieDisplay.current().version') == initial['version']
    assert page.evaluate('memberProgressText({})') == ''
    assert not errors, errors


def test_host_change_and_missing_state_island_rejected(display_page):
    page, initial, errors = display_page
    for key, value in [('host', 'different'), ('template', initial['template'].replace('id="fileEditor"','id="wrong"'))]:
        broken = dict(initial, **{key:value})
        assert page.evaluate('async value=>{try{await IndieDisplay.apply(value);return false}catch(e){return true}}', broken)
    assert page.evaluate('IndieDisplay.current().version') == initial['version']
    assert not errors, errors


def test_new_button_keeps_state_islands_and_uses_existing_action(display_page):
    page, initial, errors = display_page
    updated = dict(initial, version='button-added')
    updated['template'] = initial['template'].replace('<div id="chatEmpty">', '<div id="chatEmpty"><button id="extraHelp" onclick="document.getElementById(\'message\').focus()">도움말</button>')
    page.locator('#message').fill('추가 버튼 옆의 초안')
    page.evaluate("window.editor=document.getElementById('message');window.frame=document.getElementById('appFrame').contentWindow")
    page.evaluate('(value)=>IndieDisplay.apply(value)', updated)
    page.locator('#extraHelp').click()
    assert page.evaluate("editor===document.activeElement&&frame===document.getElementById('appFrame').contentWindow")
    assert page.locator('#message').input_value() == '추가 버튼 옆의 초안'
    assert not errors


def test_shared_button_change_does_not_change_member_or_frame_host(tmp_path, monkeypatch):
    import surface_assets
    from launcher_surface_remote import remote_display
    sources = surface_assets.asset_sources()
    with source_build():
        before = member_display(member_html(display=False), 'member')
        remote_before = remote_display()
    path = tmp_path / 'conversation.json'
    path.write_text(sources['shared/conversation.json'].read_text().replace('히스토리', '기록 보기'))
    sources['shared/conversation.json'] = path
    monkeypatch.setattr(surface_assets, 'asset_sources', lambda: sources)
    with source_build():
        after = member_display(member_html(display=False), 'member')
        remote_after = remote_display()
    assert before['host'] == after['host']
    assert before['frame']['version'] == after['frame']['version']
    assert before['version'] != after['version']
    assert remote_before['host'] == remote_after['host']


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
