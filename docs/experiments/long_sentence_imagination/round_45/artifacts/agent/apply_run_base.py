"""구민체육센터 포털 수강 신청 — 헤드리스 playwright 단독 인스턴스.
사용: python -I apply_run.py <input_dir> <out_dir>
비밀번호·접수코드 값은 출력에 남기지 않는다."""
import json, re, sys, pathlib, datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

IN = pathlib.Path(sys.argv[1]); OUT = pathlib.Path(sys.argv[2])
acc = json.loads((IN/'account.json').read_text())
applicants = json.loads((IN/'applicants.json').read_text())
applicants = applicants['items'] if isinstance(applicants, dict) else applicants
codes = json.loads((IN/'codes.json').read_text())
base = acc['portal_url'].rstrip('/')
EXP = urlparse(acc['portal_url'])
ev = OUT/'evidence'; ev.mkdir(parents=True, exist_ok=True)
rc = OUT/'receipts'; rc.mkdir(parents=True, exist_ok=True)
now = lambda: datetime.datetime.now().astimezone().isoformat(timespec='seconds')
log = []

def same_portal(url):
    u = urlparse(url)
    return u.hostname == EXP.hostname and u.port == EXP.port

def guard(pg, where):
    if not same_portal(pg.url):
        raise RuntimeError(f'포털 이탈({where}): {pg.url}')

def wait_options(pg, sel):
    # 실제 option 이 채워질 때까지(불러오는 중/안내 option 만 있으면 대기)
    pg.wait_for_function("s=>{const e=document.querySelector(s);return e && [...e.options].some(o=>o.value!=='')}", arg=sel, timeout=15000)

def sel_label(pg, sel):
    return pg.eval_on_selector(sel, 'e=>({value:e.value,label:e.selectedOptions[0]?e.selectedOptions[0].textContent:null})')

res = {'session': {'portal_url': acc['portal_url'], 'browser': None, 'headless': True, 'started_at': now()},
       'list': {}, 'applicants': []}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    res['session']['browser'] = f'chromium {b.version} (playwright, 단독 인스턴스)'
    ctx = b.new_context(); pg = ctx.new_page()
    pg.goto(base + '/login'); pg.fill('input[name=user]', acc['user']); pg.fill('input[name=pw]', acc['password'])
    pg.click('button[type=submit]'); pg.wait_for_load_state('load'); guard(pg, 'login')
    res['session']['login'] = {'url_after': pg.url, 'title': pg.title()}
    # 1) 강좌 목록 전체
    pg.goto(base + '/courses'); pg.wait_for_load_state('load'); guard(pg, 'courses')
    rows = pg.eval_on_selector_all('#courses tbody tr', 'trs=>trs.map(t=>[...t.querySelectorAll("td")].slice(0,6).map(d=>d.textContent.trim()))')
    total_text = pg.inner_text('main p')
    table = [dict(zip(['id', 'name', 'center', 'time', 'fee', 'capacity'], r)) for r in rows]
    (ev/'courses_list.json').write_text(json.dumps({'header': total_text, 'rows': table, 'at': now()}, ensure_ascii=False, indent=1))
    pg.screenshot(path=str(ev/'courses_list.png'), full_page=True)
    res['list'] = {'header': total_text, 'row_count': len(table), 'file': 'evidence/courses_list.json'}
    by_id = {r['id']: r for r in table}
    # 신청 내역 페이지 후보(읽기 전용 GET) — 재제출 전 중복 확인용
    hist_url = None
    for cand in ['/my', '/applications', '/history', '/mypage']:
        r = ctx.request.get(base + cand)
        if r.status == 200 and '로그인' not in (r.text()[:300]):
            hist_url = cand; break
    res['session']['history_page'] = hist_url

    def history_has(name, course):
        if not hist_url: return None
        t = ctx.request.get(base + hist_url).text()
        return (name in t) and (course in t)

    for a in applicants:
        nm = a['name']; rec = {'name': nm, 'birth': a['birth'], 'region': a['region'], 'center': a['center'], 'course': a['course'],
                               'list_row': by_id.get(a['course']), 'attempts': [], 'code_used': nm in codes}
        res['applicants'].append(rec)
        for attempt in (1, 2):
            if attempt == 2:
                h = history_has(nm, a['course'])
                rec['pre_resubmit_history_check'] = {'page': hist_url, 'already_applied': h}
                if h: rec['attempts'].append({'n': 2, 'skipped': '신청 내역에 이미 있음'}); break
            pg.goto(base + '/apply'); pg.wait_for_load_state('load'); guard(pg, 'apply')
            pg.select_option('#region', value=a['region'])
            wait_options(pg, '#center')
            pg.select_option('#center', label=a['center'])
            wait_options(pg, '#course')
            copts = pg.eval_on_selector_all('#course option', 'os=>os.map(o=>({v:o.value,t:o.textContent}))')
            pg.select_option('#course', value=a['course'])
            pg.fill('#name', nm); pg.fill('#birth', a['birth'])
            pg.set_input_files('#cert', str(IN/a['cert']))
            pg.check('#agree')
            # 제출 직전 검사: 포트·선택값
            guard(pg, 'pre-submit')
            chk = {'url': pg.url, 'port_ok': same_portal(pg.url),
                   'region': sel_label(pg, '#region'), 'center': sel_label(pg, '#center'), 'course': sel_label(pg, '#course'),
                   'name': pg.input_value('#name'), 'birth': pg.input_value('#birth'),
                   'cert': pg.eval_on_selector('#cert', 'e=>e.files[0]?e.files[0].name:null'), 'agree': pg.is_checked('#agree')}
            ok = (chk['port_ok'] and chk['region']['value'] == a['region'] and (chk['center']['label'] or '').strip() == a['center']
                  and chk['course']['value'] == a['course'] and chk['name'] == nm and chk['birth'] == a['birth']
                  and chk['cert'] == a['cert'] and chk['agree'])
            att = {'n': attempt, 'at': now(), 'pre_submit_check': chk, 'pre_submit_ok': ok, 'course_option_label': chk['course']['label']}
            rec['attempts'].append(att)
            pg.screenshot(path=str(ev/f'{nm}_{attempt}_form.png'), full_page=True)
            if not ok:
                att['outcome'] = 'aborted'; att['reason'] = '제출 직전 검사 불일치'; break
            dialogs = []
            def on_dialog(d):
                dialogs.append({'type': d.type, 'message': d.message})
                if d.type == 'prompt': d.accept(codes[nm])
                else: d.accept()
            pg.on('dialog', on_dialog)
            with pg.expect_response(lambda r: r.request.method == 'POST' and '/apply' in r.url, timeout=20000) as ri:
                pg.click('#submit')
            resp = ri.value
            pg.wait_for_load_state('load')
            pg.remove_listener('dialog', on_dialog)
            guard(pg, 'post-submit')
            body = pg.inner_text('body')
            att.update({'dialogs': dialogs, 'http_status': resp.status, 'result_url': pg.url, 'result_title': pg.title(),
                        'result_text': body[:1500]})
            (ev/f'{nm}_{attempt}_result.html').write_text(pg.content())
            pg.screenshot(path=str(ev/f'{nm}_{attempt}_result.png'), full_page=True)
            m = re.search(r'접수\s*번호\s*[:：]?\s*([A-Za-z0-9\-]+)', body)
            if m and resp.status < 400:
                att['outcome'] = 'success'; att['receipt_no'] = m.group(1)
                pdf = rc/f'{nm}.pdf'; pg.pdf(path=str(pdf), format='A4', print_background=True)
                att['receipt_pdf'] = str(pdf)
                break
            transient = resp.status >= 500 or re.search(r'일시|잠시 후|다시 시도', body)
            att['outcome'] = 'transient_error' if transient else 'rejected'
            if not transient: break
    res['session']['finished_at'] = now()
    b.close()
(OUT/'portal_raw.json').write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps({'applicants': [{'name': r['name'], 'attempts': [{k: x.get(k) for k in ('n', 'outcome', 'http_status', 'receipt_no', 'pre_submit_ok', 'dialogs', 'skipped')} for x in r['attempts']]} for r in res['applicants']], 'history_page': res['session'].get('history_page'), 'rows': res['list']['row_count']}, ensure_ascii=False))
