import sys, json, re, time, pathlib
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INP = pathlib.Path(sys.argv[1]); OUT = pathlib.Path(sys.argv[2])
SHOTS = OUT / 'shots'; SHOTS.mkdir(parents=True, exist_ok=True)
console_cfg = json.loads((INP / 'console.json').read_text())
policy = json.loads((INP / 'policy.json').read_text())
BASE = console_cfg['url'].rstrip('/')
MAX_TRY = 3
ev = {'base': BASE, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'edits': [], 'display': {}, 'export': {}, 'back': {}, 'network': {}, 'errors': []}
net = []
t0 = time.time()

def shot(pg, name):
    try:
        pg.screenshot(path=str(SHOTS / f'{name}.png'), full_page=True)
    except Exception as e:
        ev['errors'].append(f'shot {name}: {e}')

def read_display(pg):
    return pg.eval_on_selector_all('#list li', 'els=>els.map(e=>({id:e.dataset.id,name:e.childNodes[0].textContent.trim()}))')

def save_dump():
    ev['network']['all'] = net
    (OUT / 'evidence.json').write_text(json.dumps(ev, ensure_ascii=False, indent=1))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(accept_downloads=True)
    def on_resp(r):
        net.append({'t': round(time.time()-t0, 2), 'method': r.request.method, 'url': r.url, 'status': r.status, 'ok': r.ok, 'failure': None})
    def on_fail(rq):
        net.append({'t': round(time.time()-t0, 2), 'method': rq.method, 'url': rq.url, 'status': None, 'ok': False, 'failure': rq.failure})
    ctx.on('response', on_resp)
    ctx.on('requestfailed', on_fail)
    main = ctx.new_page()
    console_log = []
    ctx.on('console', lambda m: console_log.append({'type': m.type, 'text': m.text}))

    # ---------- 1) edits ----------
    for ed in policy['edits']:
        name, price, desc = ed['name'], int(ed['price']), ed['desc']
        rec = {'name': name, 'target_price': price, 'target_desc': desc, 'picked': None, 'id': None,
               'before': None, 'attempts': [], 'attempt_count': 0, 'saved': False, 'server_after': None,
               'popup_closed': None, 'tabs_after_close': None, 'back_on_original': None}
        try:
            # autocomplete search (retry if suggest list empty)
            opt = None; cands = []
            for k in range(MAX_TRY):
                main.goto(BASE + '/products', wait_until='load')
                main.locator('#q').press_sequentially(name, delay=40)
                try:
                    main.wait_for_selector('#sug li', timeout=4000)
                except PWTimeout:
                    cands = []; continue
                cands = main.eval_on_selector_all('#sug li', 'els=>els.map(e=>({id:e.dataset.id,name:e.textContent.trim()}))')
                exact = [c for c in cands if c['name'] == name]
                if len(exact) == 1:
                    opt = exact[0]; break
            rec['suggestions'] = cands
            if not opt:
                rec['error'] = '자동완성에서 정확히 같은 이름의 후보를 찾지 못함'; ev['edits'].append(rec); continue
            main.locator('#sug li', has_text=re.compile('^' + re.escape(name) + '$')).click()
            main.wait_for_selector('#picked')
            picked = main.inner_text('#picked')
            rec['picked'] = picked; rec['id'] = opt['id']
            rec['picked_ok'] = f'{name} ({opt["id"]})' in picked
            orig_url = main.url
            # open edit popup
            with ctx.expect_page() as pi:
                main.locator(f'a[aria-label="{name} 편집"]').click()
            pop = pi.value; pop.wait_for_load_state('load')
            h1 = pop.inner_text('h1'); body = pop.inner_text('body')
            rec['popup_url'] = pop.url
            rec['edit_identity_ok'] = (h1.strip() == f'상품 편집 — {name}') and (f'상품번호 {opt["id"]}' in body)
            rec['before'] = {'price': int(pop.input_value('#price')), 'desc': pop.inner_text('#desc').strip()}
            if not rec['edit_identity_ok']:
                rec['error'] = f'편집 화면 신원 불일치: {h1}'; pop.close(); ev['edits'].append(rec); continue
            for k in range(1, MAX_TRY + 1):
                a = {'n': k}
                # set slider by keyboard
                cur = int(pop.input_value('#price'))
                sl = pop.locator('#price'); sl.focus()
                step = 1000
                diff = (price - cur) // step
                key = 'ArrowRight' if diff > 0 else 'ArrowLeft'
                for _ in range(abs(diff)):
                    sl.press(key)
                a['slider_value'] = int(pop.input_value('#price'))
                a['slider_output'] = pop.inner_text('#pv')
                if a['slider_value'] != price:
                    a['slider_fallback'] = True
                    pop.eval_on_selector('#price', f'(e)=>{{e.value="{price}";e.dispatchEvent(new Event("input",{{bubbles:true}}))}}')
                    a['slider_value'] = int(pop.input_value('#price'))
                pop.locator('#desc').fill(desc)
                a['desc_value'] = pop.inner_text('#desc').strip()
                a['inputs_ok'] = a['slider_value'] == price and a['desc_value'] == desc
                pop.click('#save')
                try:
                    pop.wait_for_function("()=>{const t=document.getElementById('msg').textContent;return t.startsWith('저장됨')||t.startsWith('저장 실패')}", timeout=15000)
                    a['msg'] = pop.inner_text('#msg')
                except PWTimeout:
                    a['msg'] = 'TIMEOUT: ' + pop.inner_text('#msg')
                shot(pop, f'edit_{opt["id"]}_try{k}')
                a['msg_success'] = a['msg'].startswith('저장됨') and f'{price:,}원' in a['msg']
                # verify against server by reloading the edit tab
                pop.reload(wait_until='load')
                srv = {'price': int(pop.input_value('#price')), 'desc': pop.inner_text('#desc').strip()}
                a['server_after_reload'] = srv
                a['server_matches'] = srv['price'] == price and srv['desc'] == desc
                rec['attempts'].append(a)
                if a['server_matches']:
                    # 서버에 이미 반영되었으면 더 저장하지 않는다(중복 저장 방지)
                    rec['saved'] = True; break
            rec['attempt_count'] = len(rec['attempts'])
            rec['server_after'] = rec['attempts'][-1]['server_after_reload'] if rec['attempts'] else None
            pop.close()
            rec['popup_closed'] = pop.is_closed()
            main.bring_to_front()
            rec['tabs_after_close'] = len(ctx.pages)
            rec['back_on_original'] = (main.url == orig_url) and len(ctx.pages) == 1
            rec['main_url_after'] = main.url
        except Exception as e:
            rec['error'] = repr(e)
        ev['edits'].append(rec); save_dump()

    # ---------- 2) display reorder ----------
    d = ev['display']
    main.goto(BASE + '/display', wait_until='load')
    before = read_display(main)
    d['before'] = before
    ids_by_name = {x['name']: x['id'] for x in before}
    top_names = policy['display_top']
    missing = [n for n in top_names if n not in ids_by_name]
    d['missing_top'] = missing
    rest = [x['name'] for x in before if x['name'] not in top_names]
    target = top_names + rest
    d['target'] = target
    shot(main, 'display_before')
    d['drags'] = []
    for rnd in range(1, MAX_TRY + 1):
        cur = [x['name'] for x in read_display(main)]
        if cur == target: break
        for k, nm in enumerate(top_names):
            cur = [x['name'] for x in read_display(main)]
            if cur[k] == nm: continue
            src = main.locator(f'#list li[data-id="{ids_by_name[nm]}"]')
            dst = main.locator(f'#list li[data-id="{ids_by_name[cur[k]]}"]')
            sb = src.bounding_box(); db = dst.bounding_box()
            st_before = main.inner_text('#st')
            main.mouse.move(sb['x'] + sb['width']/2, sb['y'] + sb['height']/2)
            main.mouse.down()
            main.mouse.move(db['x'] + db['width']/2, db['y'] + db['height']*0.25, steps=12)
            main.mouse.up()
            try:
                main.wait_for_function("(b)=>{const t=document.getElementById('st').textContent;return t!==b&&t!=='순서 저장 중…'}", arg=st_before, timeout=10000)
            except PWTimeout:
                pass
            d['drags'].append({'round': rnd, 'item': nm, 'onto': cur[k], 'status': main.inner_text('#st'), 'dom_after': [x['name'] for x in read_display(main)]})
        # reload = server state
        main.reload(wait_until='load')
        d.setdefault('reloads', []).append([x['name'] for x in read_display(main)])
    after = read_display(main)
    d['after_reload'] = after
    d['after_names'] = [x['name'] for x in after]
    d['matches_target'] = d['after_names'] == target
    d['rounds'] = len(d['reloads'])
    shot(main, 'display_after_reload')
    save_dump()

    # ---------- 3) export ----------
    x = ev['export']; x['tries'] = []
    for k in range(1, MAX_TRY + 1):
        tr = {'n': k}
        main.goto(BASE + '/export', wait_until='load')
        main.click('#start')
        try:
            main.wait_for_function("()=>document.getElementById('pg').textContent.startsWith('내보내기 완료')", timeout=30000, polling=200)
            tr['progress'] = main.inner_text('#pg'); tr['done'] = True
        except PWTimeout:
            tr['progress'] = main.inner_text('#pg'); tr['done'] = False
            x['tries'].append(tr); continue
        try:
            link = main.locator('#dl a')
            tr['href'] = link.get_attribute('href')
            with main.expect_download(timeout=15000) as di:
                link.click()
            dl = di.value
            tr['download_failure'] = dl.failure()
            if not tr['download_failure']:
                dl.save_as(str(OUT / 'display.csv'))
                tr['suggested_filename'] = dl.suggested_filename
                tr['saved'] = True
        except Exception as e:
            tr['download_error'] = repr(e)
        x['tries'].append(tr)
        if tr.get('saved'): break
    x['saved'] = any(t.get('saved') for t in x['tries'])
    shot(main, 'export_done')
    save_dump()

    # ---------- 4) back ----------
    b = ev['back']
    b['url_before_back'] = main.url
    main.go_back(wait_until='load')
    b['url_after_back'] = main.url
    b['h1'] = main.inner_text('h1')
    if '/display' not in main.url:
        # 내보내기 재시도로 기록이 여러 개면 진열 화면이 나올 때까지 뒤로 간다(최대 3회)
        for _ in range(3):
            main.go_back(wait_until='load'); b.setdefault('extra_backs', []).append(main.url)
            if '/display' in main.url: break
        b['url_after_back'] = main.url; b['h1'] = main.inner_text('h1')
    names = [y['name'] for y in read_display(main)] if '/display' in main.url else None
    b['order'] = names
    b['matches_target'] = names == target
    shot(main, 'display_after_back')

    # final server check of edits (separate tab, closed again)
    chk = ctx.new_page(); fin = []
    for r in ev['edits']:
        if r.get('id'):
            chk.goto(BASE + '/edit/' + r['id'], wait_until='load')
            fin.append({'id': r['id'], 'name': r['name'], 'price': int(chk.input_value('#price')), 'desc': chk.inner_text('#desc').strip()})
    chk.close()
    ev['final_edit_check'] = fin

    ev['open_tabs_at_end'] = len(ctx.pages)
    ev['tab_urls_at_end'] = [pg.url for pg in ctx.pages]
    ev['console'] = console_log
    ev['network']['failed'] = [n for n in net if (n['status'] is None) or n['status'] >= 400]
    ev['network']['total'] = len(net)
    ev['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    save_dump()
    browser.close()
print(json.dumps({k: ev[k] for k in ['edits', 'display', 'export', 'back', 'open_tabs_at_end', 'final_edit_check']}, ensure_ascii=False, indent=1))
print('NET_FAILED', json.dumps(ev['network']['failed'], ensure_ascii=False))
