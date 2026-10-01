"""Browser integration of the built desktop and actual server-generated remote shell.
Run after vite build, with a Python that provides playwright. API data is synthetic;
translation catalogs are the real generated artifact, not mocked translations.
"""
import json
import argparse
import yaml
from urllib.request import urlopen
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
LIVE_REMOTE_HTML = None

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'dist'), **kwargs)

    def do_GET(self):
        if self.path == '/launcher/app':
            html = (LIVE_REMOTE_HTML or json.loads((ROOT / 'i18n/remote.json').read_text())['html']).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html)
        else:
            super().do_GET()

    def log_message(self, *args):
        pass


def main():
    global LIVE_REMOTE_HTML
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-url')
    args = parser.parse_args()
    if args.live_url:
        with urlopen(args.live_url.rstrip('/') + '/launcher/app',timeout=10) as response:
            LIVE_REMOTE_HTML = response.read().decode('utf-8')
        assert LIVE_REMOTE_HTML == json.loads((ROOT / 'i18n/remote.json').read_text())['html'], 'live remote differs from verified generated shell'
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    reports = [{'remoteSource': args.live_url or 'isolated generated shell', 'businessAPI':'intercepted; real handlers receive no test writes'}]
    catalog = json.loads((ROOT / 'i18n/catalog.json').read_text())
    source_nodes = yaml.safe_load((ROOT.parent / 'data/ibl_nodes.yaml').read_text())['nodes']
    dictionary_probe = source_nodes['sense']['actions']['world']
    manifest_probe = {**source_nodes['sense']['actions']['weather']['app'], 'id': 'weather'}
    def tr(source):
        matches = [m for m in catalog['messages'].values() if m['source'].strip() == source.strip() and m.get('translations', {}).get('en')]
        assert matches, ('missing translation', source)
        return matches[0]['translations']['en']
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for surface, url in [('desktop', '/'), ('remote', '/launcher/app')]:
            context = browser.new_context(viewport={'width': 1280, 'height': 900})
            page = context.new_page()
            errors = []
            requests = []
            executions = []
            gear = {'current_gear':'균형','gears':['절약','균형','최대'], 'tiers':['경량','중급','고급'],
                    'axis_names':['분류','평가','실행','의식'],
                    'presets':{g:{a:'중급' for a in ['분류','평가','실행','의식']} for g in ['절약','균형','최대']},
                    'axes':{a:{'tier':'중급'} for a in ['분류','평가','실행','의식']},
                    'axis_info':{'분류':{'label':'분류','description':'실행·숙고 경로 선택과 기억 증류에 사용합니다.'}, '평가':{'label':'보조 AI'},'실행':{'label':'실행'},'의식':{'label':'의식'}},
                    'consciousness_enabled':True, 'sensory_models':[]}
            page.on('pageerror', lambda error: errors.append(error.stack))
            def api(route):
                path = urlsplit(route.request.url).path
                if route.request.url.startswith(origin) and (path in ['/', '/launcher/app'] or path.startswith('/assets/')):
                    route.continue_()
                    return
                if route.request.method == 'POST' and path in ['/ibl/execute','/launcher/execute']:
                    executions.append(route.request.post_data_json)
                payload = {}
                if path == '/launcher/config': payload = {'has_password': False, 'host': 'desktop'}
                elif path == '/ibl/actions/catalog': payload = {'nodes': {'sense': {'actions': {'world': dictionary_probe}, 'count': 1}}, 'total': 1}
                elif path == '/projects': payload = {'projects': []}
                elif path == '/switches': payload = {'switches': []}
                elif path == '/folders': payload = {'folders': []}
                elif path == '/launcher/app-layout': payload = {'version':1,'positions':{},'folders':{},'membership':{},'removed':[],'uninstalled':[],'promoted':[]}
                elif path == '/launcher/instruments': payload = {'instruments':[{'id':'user-app','name':'사진','icon':'★','modes':[]}, manifest_probe]}
                elif path == '/health': payload = {'status': 'ok'}
                elif path == '/world-pulse/dashboard': payload = {'ibl_health':{'healthy':True,'items':[]},'services':{}}
                elif path == '/model-gear':
                    if route.request.method == 'PUT':
                        body = route.request.post_data_json
                        requests.append(body)
                        gear['current_gear'] = body['gear']
                    payload = gear
                elif path == '/model-gear/overrides':
                    payload = {'agents':[{'id':'test','name':'절약','project':'사용자 프로젝트'}], 'overrides':{}}
                elif path == '/model-gear/presets':
                    body = route.request.post_data_json
                    requests.append(body)
                    gear['presets'] = body['presets']
                    payload = gear
                route.fulfill(status=200, content_type='application/json', body=json.dumps(payload), headers={'Access-Control-Allow-Origin':'*'})
            page.route('**/*', api)
            page.goto(origin + url)
            picker = page.get_by_label('Language / 언어').filter(visible=True)
            picker.first.wait_for(timeout=30000)
            if surface == 'desktop':
                page.get_by_title('화면 모드 선택', exact=True).click()
                page.get_by_role('button', name='조종실', exact=True).click()
                panel = page.locator('.cockpit-content > div').filter(has=page.get_by_role('switch')).first
            else:
                page.locator('#t-manual').click()
                panel = page.locator('#gearLever')
            page.wait_for_timeout(500)
            panel.get_by_text('절약',exact=True).wait_for(timeout=5000)
            korean = page.locator('body').inner_text()
            picker.first.select_option('en')
            page.wait_for_timeout(300)
            english = page.locator('body').inner_text()
            if surface == 'desktop':
                catalog = json.loads((ROOT / 'i18n/catalog.json').read_text())
                changed = next(m for m in catalog['messages'].values() if m['source'] == '화면 모드 선택')
                assert changed['translations']['en'] != changed['source']
                assert page.get_by_title(changed['translations']['en'], exact=True).count() == 1
            assert english != korean, (surface, english[:500])
            if surface == 'desktop':
                page.get_by_role('heading',name=tr('환영합니다!'),exact=True).wait_for()
                headings = []
                for index in range(14):
                    heading = page.locator('h2').filter(visible=True).inner_text()
                    assert not __import__('re').search('[가-힣]', heading), ('guide heading',index,heading)
                    headings.append(heading)
                    if index < 13: page.keyboard.press('ArrowRight')
                assert len(set(headings)) == 14
                reports.append({'surface':'desktop','guidePagesChecked':headings})
                page.keyboard.press('Escape')
            for name in ['절약','균형','최대']:
                panel.get_by_text(tr(name), exact=True).wait_for()
                assert panel.get_by_text(name, exact=True).count() == 0
            panel.get_by_text(tr('절약'),exact=True).click()
            page.wait_for_timeout(150)
            assert requests[-1] == {'gear':'절약'}, (surface,requests)
            panel.get_by_text(tr('최대'),exact=True).click()
            page.wait_for_timeout(150)
            assert requests[-1] == {'gear':'최대'}
            # Open real dynamic settings, preserve raw select values and custom agent names.
            if surface == 'remote': panel.locator('[data-act="toggle"]').click()
            else: panel.get_by_role('button',name=tr('설정'),exact=True).click()
            panel.get_by_text('사용자 프로젝트',exact=True).wait_for()
            changed_messages = [m for m in catalog['messages'].values() if m['source']=='기어 프리셋 — 인지 축별 AI 모델 등급']
            changed = next(m for m in changed_messages if m['context'].startswith('remote:') == (surface=='remote'))
            panel.get_by_text(changed['translations']['en'],exact=True).wait_for()
            agent_label = panel.get_by_text('사용자 프로젝트',exact=True).locator('..').inner_text()
            assert '절약' in agent_label and tr('절약') not in agent_label, ('user-defined agent name changed', agent_label)
            selects = panel.locator('select')
            assert selects.count() >= 12
            panel_text = panel.inner_text().replace('사용자 프로젝트','').replace('절약','')
            assert not __import__('re').search('[가-힣]',panel_text), (surface,'untranslated gear UI',panel_text)
            page.screenshot(path='/tmp/indiebiz-ui-'+surface+'-en.png')
            first = selects.first
            first.select_option('고급')
            assert first.input_value() == '고급'
            assert first.locator('option[value="고급"]').inner_text() == tr('고급')
            if surface == 'remote': panel.locator('[data-act="savePresets"]').click()
            else: panel.get_by_role('button',name=tr('저장'),exact=True).click()
            page.wait_for_timeout(200)
            assert requests[-1]['presets']['절약']['분류'] == '고급'
            picker.first.select_option('ko')
            panel.get_by_text('최대',exact=True).first.wait_for()
            assert first.input_value() == '고급'
            picker.first.select_option('en')
            reports.append({'surface':surface,'gearButtons':[tr(n) for n in ['절약','균형','최대']], 'changedSourceDisplayed':changed['translations']['en'], 'rawRequests':requests,'userNamedEconomyPreserved':True,'presetValuePreserved':True})
            assert page.locator('html').get_attribute('lang') == 'en'
            assert page.evaluate("localStorage.getItem('indiebiz.ui.locale')") == 'en'
            # Content entered or returned by users remains byte-for-byte intact on switches.
            page.evaluate("""() => {const p=document.createElement('p');p.id='user-content';p.textContent='사용자 대화·파일명 비밀값 $& <b>';document.body.append(p);const i=document.createElement('input');i.id='draft';i.value='입력 중인 한국어';document.body.append(i)}""")
            picker.first.select_option('ko')
            assert page.locator('#user-content').inner_text() == '사용자 대화·파일명 비밀값 $& <b>'
            assert page.locator('#draft').input_value() == '입력 중인 한국어'
            picker.first.select_option('en')
            page.reload()
            picker.first.wait_for()
            assert picker.first.input_value() == 'en'
            assert page.locator('html').get_attribute('lang') == 'en'
            picker.first.select_option('ko')
            assert page.locator('html').get_attribute('lang') == 'ko'
            # Return to the same user-visible source labels after a full English cycle.
            assert ('모델 기어' if surface=='desktop' else '자율주행') in page.locator('body').inner_text()
            if surface == 'desktop':
                picker.first.select_option('en')
                dictionary_button = page.get_by_role('button',name=tr('IBL 사전'),exact=True)
                dictionary_button.click()
                page.get_by_text(tr(dictionary_probe['description']),exact=True).wait_for()
                page.get_by_text(tr(dictionary_probe['target_description']),exact=False).first.wait_for()
                assert page.get_by_text(dictionary_probe['description'],exact=True).count() == 0
                dictionary_button.click()
                reports.append({'surface':'desktop','dictionaryDescriptionTranslated':True,'dictionarySourceUnchanged':dictionary_probe['description']})
                page.get_by_title(tr('화면 모드 선택'),exact=True).click()
                page.get_by_role('button',name=tr('앱'),exact=True).click()
                photos = next(m['translations']['en'] for m in catalog['messages'].values() if m['context']=='app.static' and m['source']=='사진')
                page.get_by_text(photos,exact=True).wait_for()
                page.get_by_text('사진',exact=True).wait_for()  # custom app with the same name stays Korean
                reports.append({'surface':'desktop','builtInAppTranslated':photos,'customAppNamePreserved':'사진'})
            if surface == 'remote':
                page.evaluate("apBrowseRoot()")
                picker.first.select_option('en')
                assert page.locator('#apBrowse').get_by_text('시스템 AI', exact=True).count() == 0
            if surface == 'remote':
                page.get_by_role('button',name=__import__('re').compile('Apps.*Speed')).click()
                page.locator('#appHome .tile').filter(has_text=tr('날씨')).click()
            else:
                page.get_by_text(tr('날씨'),exact=True).dblclick()
            city = page.get_by_placeholder(tr('도시명 (한/영)'),exact=True)
            city.wait_for()
            city.fill('사용자가 입력한 오송')
            page.wait_for_timeout(200)
            calls_before = len(executions)
            picker.first.select_option('ko')
            city_ko = page.get_by_placeholder('도시명 (한/영)',exact=True)
            city_ko.wait_for()
            assert city_ko.input_value() == '사용자가 입력한 오송'
            picker.first.select_option('en')
            city.wait_for()
            assert city.input_value() == '사용자가 입력한 오송'
            page.wait_for_timeout(200)
            assert len(executions) == calls_before, 'locale switch must not execute an action'
            assert manifest_probe['inputs'][0]['default'] == '서울'
            reports.append({'surface':surface,'manifestPlaceholder':tr('도시명 (한/영)'), 'typedValuePreserved':True,'localeChangeExecutesNoAction':True})
            assert not errors, (surface, errors)
            reports.append({'surface': surface, 'switchPersistRestore': True, 'userContentPreserved': True, 'pageErrors': errors, 'englishSample': english[:400]})
            if surface == 'desktop':
                page.evaluate("localStorage.setItem('indiebiz.ui.locale','en')")
                for route_name in ['guides', 'vocabulary', 'prompt-composition']:
                    window = context.new_page()
                    def window_api(route):
                        path = urlsplit(route.request.url).path
                        if route.request.url.startswith(origin) and (path == '/' or path.startswith('/assets/')):
                            route.continue_(); return
                        payload = {'items': [], 'guides': [], 'packages': [], 'agents': [], 'projects': [],
                                   'default_sample': '', 'folders': {}, 'positions': {}, 'membership': {},
                                   'missing_files': [], 'total_bytes': 0, 'budget_bytes': 36000,
                                   'no_prompt_jobs': [], 'model': {}, 'totals': {}, 'assembled': {},
                                   'version': 1, 'error': 'No prompt selected', 'layers': [], 'sections': [], 'fragments': []}
                        route.fulfill(status=200, content_type='application/json', body=json.dumps(payload), headers={'Access-Control-Allow-Origin':'*'})
                    window.route('**/*', window_api)
                    window_errors = []
                    window.on('pageerror', lambda error: window_errors.append(str(error)))
                    window.goto(origin + '/#/' + route_name)
                    window.wait_for_timeout(700)
                    text = window.locator('body').inner_text()
                    assert not window_errors, (route_name, window_errors)
                    assert text.strip(), ('blank system window', route_name)
                    assert not __import__('re').search('[가-힣]', text.replace('한국어','')), (route_name, text)
                    attrs = window.locator('[title],[placeholder],[aria-label]').evaluate_all("els=>els.flatMap(e=>['title','placeholder','aria-label'].map(k=>e.getAttribute(k)||''))")
                    remaining = [s for s in attrs if __import__('re').search('[가-힣]',s.replace('언어',''))]
                    assert not remaining, (route_name,'untranslated attributes',remaining)
                    reports.append({'systemWindow':route_name,'text':text,'attributesChecked':len(attrs),'pageErrors':window_errors,'data':'empty synthetic records; document content excluded'})
                    window.close()
            context.close()
        browser.close()
    server.shutdown()
    print(json.dumps(reports, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
