"""화면 표시 모듈의 인계 계약. 실행 코드와 표시 코드를 다른 지문으로 묶는다."""
import hashlib
import json
import re

from surface_assets import read_asset


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def describe(html, surface, display, shared, *, rendered_code=None, raw_html=None, kernel="shared/display-host.js", messages=None):
    code = shared + '\n' + display
    # Functions are authored separately from state, requests, polling and native adapters.
    names = sorted((['getConversation'] if shared else []) + re.findall(r'^function\s+(\w+)\s*\(', display, re.M))
    scripts = re.findall(r'<script\b[^>]*>([\s\S]*?)</script>', raw_html or html, re.I)
    host = '\n'.join(scripts).replace(shared, '').replace(display, '')
    host = re.sub(r'const MEMBER_FRAME_HTML=[^\n]+\n', 'const MEMBER_FRAME_HTML=<frame-display>\n', host)
    styles = re.findall(r'<style\b[^>]*>([\s\S]*?)</style>', html, re.I)
    template = re.sub(r'<script\b[^>]*>[\s\S]*?</script>', '', html, flags=re.I)
    template = re.sub(r'<style\b[^>]*>[\s\S]*?</style>', '', template, flags=re.I)
    result = dict(format='indiebiz-display-1', surface=surface, state=1,
                  host=_digest(host + read_asset(kernel)),
                  code=rendered_code or code, names=names, styles=styles, template=template)
    if surface == 'frame':
        result['host'] = _digest(result['host'] + read_asset('member/frame-display-bridge.js'))
    result['messages'] = messages or {}
    result['requiredIds'] = sorted(set(re.findall(r"(?:getElementById|\$)\(['\"]([^'\"]+)['\"]\)", host)))
    result['version'] = _digest(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return result


def member_display(html, surface):
    from launcher_render_core import load_conversation_js
    from member_app_frame import frame_display
    result = describe(html, surface, read_asset('member/display.js'), load_conversation_js())
    result['frame'] = frame_display()
    result['host'] = _digest(result['host'] + result['frame']['host'])
    result['version'] = _digest(json.dumps({k:v for k,v in result.items() if k != 'version'}, sort_keys=True, ensure_ascii=False))
    return result


def launcher_display(html, surface, *, raw_html=None, rendered_code=None, messages=None):
    from launcher_render_core import load_conversation_js
    return describe(html, surface, read_asset('remote/conversation-display.js') + read_asset('remote/display.js'), load_conversation_js(),
                    raw_html=raw_html, rendered_code=rendered_code, messages=messages)


def display_bootstrap(descriptor, poll=None):
    value = json.dumps(descriptor, ensure_ascii=False).replace('<', '\\u003c')
    if descriptor['surface'] in ('member', 'browser', 'desktop'):
        refresh = 'function(){ getConversation().arrange(document.getElementById("taskSessionMenu"),{older:"taskOlder",history:"taskHistoryOpen",new:"newTask",dictionary:"memberDictionaryOpen"}); renderMemberDictionary();renderMemberFiles(memberFileDisplay); }'
    else:
        refresh = 'function(){getConversation().arrange(document.getElementById("apSessions"),{older:"apSessionOlder",history:"apHistory",new:"apSessionNew",dictionary:"apDictionary"});if(apSessionContext){apSessionContext.listSignature="";apRenderSessionList();}}'
    return (read_asset('shared/display-host.js') + '\nIndieDisplay.start(' + value + ', ' + refresh + ');\n'
            + ('IndieDisplay.watch(' + json.dumps(poll) + ');\n' if poll else ''))
