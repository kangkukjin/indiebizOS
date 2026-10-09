import json, re, sys, time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
BASE='/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-09_46회차/agent'
IN=BASE+'/input'; OUT=BASE+'/out'; EV=OUT+'/evidence'
import os; os.makedirs(EV, exist_ok=True)
acc=json.load(open(IN+'/account.json'))
trip=json.load(open(IN+'/trip.json'))
portals=json.load(open(IN+'/portals.json'))
log=[]; relogins=[]; dialogs=[]
def L(*a):
    s=' '.join(str(x) for x in a); print(s, flush=True); log.append(s)
def money(s):
    return int(re.sub(r'[^0-9]','',s)) if re.search(r'\d',s) else None

def on_login(pg):
    return '/login' in pg.url or pg.locator('input[name=pw]').count()>0

def login(pg, base, where):
    if not on_login(pg): pg.goto(base+'login')
    pg.fill('input[name=user]',acc['user']); pg.fill('input[name=pw]',acc['password'])
    pg.click('button[type=submit]'); pg.wait_for_load_state('load')
    if on_login(pg): raise RuntimeError('로그인 실패: '+where)
    consent(pg, where)

def consent(pg, where):
    btn=pg.locator('button:has-text("필수만 동의")')
    if btn.count() and btn.first.is_visible():
        btn.first.click(); pg.wait_for_load_state('load'); L('consent essential at',where, pg.url)

def guard(pg, base, name, where, target_url):
    """세션 끊김 감지 → 재로그인 → 같은 주소로 재진입"""
    if on_login(pg):
        relogins.append({'portal':name,'where':where,'url_seen':pg.url,'at':time.strftime('%H:%M:%S')})
        L('SESSION CUT', name, where, pg.url)
        login(pg, base, where)
        if target_url:
            pg.goto(target_url); pg.wait_for_load_state('load'); consent(pg, where)
        return True
    return False

def search(pg, p, tag):
    base=p['url']; name=p['name']
    pg.goto(base); pg.wait_for_load_state('load')
    login(pg, base, 'start')
    if '/search' not in pg.url: pg.goto(base+'search'); pg.wait_for_load_state('load')
    for attempt in range(3):
        guard(pg, base, name, 'search page', base+'search')
        consent(pg,'search')
        pg.screenshot(path=f'{EV}/{tag}_1_search.png')
        pg.click('button:has-text("날짜 선택")')
        pg.click(f'[aria-label="{trip["checkin"]}"]')
        pg.select_option('#nights', str(trip['nights']))
        for _ in range(12):
            g=int(pg.input_value('#guests'))
            if g==trip['guests']: break
            pg.click('[aria-label="인원 늘리기"]' if g<trip['guests'] else '[aria-label="인원 줄이기"]')
        shown={'checkin':pg.input_value('#checkin'),'picked':pg.text_content('#picked'),
               'nights':pg.input_value('#nights'),'guests_label':pg.text_content('#gshow'),'guests':pg.input_value('#guests')}
        L(tag,'widgets', json.dumps(shown, ensure_ascii=False))
        pg.screenshot(path=f'{EV}/{tag}_2_filled.png')
        pg.click('form[action="/rooms"] button[type=submit]'); pg.wait_for_load_state('load')
        if guard(pg, base, name, 'search submit', None):
            continue
        break
    head=pg.text_content('main h2')
    m=re.search(r'체크인\s*(\d{4}-\d{2}-\d{2}),\s*(\d+)박,\s*(\d+)명', head or '')
    cond={'heading':head,'checkin':m.group(1) if m else None,'nights':int(m.group(2)) if m else None,'guests':int(m.group(3)) if m else None}
    cond['matches_trip']= (cond['checkin']==trip['checkin'] and cond['nights']==trip['nights'] and cond['guests']==trip['guests'])
    rows=[]
    for tr in pg.locator('#rooms tbody tr').all():
        td=[t.inner_text().strip() for t in tr.locator('td').all()]
        link=tr.locator('a').first.get_attribute('href') if tr.locator('a').count() else None
        rows.append({'portal':name,'port':urlparse(base).port,'no':td[0],'room':td[1],'breakfast':td[2],
          'nightly_raw':td[3],'total_raw':td[4],'remain_raw':td[5],'nightly':money(td[3]),'total':money(td[4]),
          'remaining':money(td[5]) if '마감' not in td[5] else 0,'closed':'마감' in td[5],'hold_href':link,
          'total_check': (money(td[3]) or 0)*cond['nights']==money(td[4]) if cond['nights'] else None})
    pg.screenshot(path=f'{EV}/{tag}_3_rooms.png', full_page=True)
    open(f'{EV}/{tag}_rooms.html','w').write(pg.content())
    return {'portal':name,'url':base,'rooms_url':pg.url,'conditions':cond,'widgets':shown,'rows':rows}

res={'trip':trip}
with sync_playwright() as pw:
    b=pw.chromium.launch(headless=True)
    ctx=b.new_context()
    tabs=[]; results=[]
    for i,p in enumerate(portals):
        pg=ctx.new_page(); tabs.append(pg)
        results.append(search(pg,p,f'p{i+1}'))
    res['tabs']=[{'index':i,'portal':portals[i]['name'],'url':t.url} for i,t in enumerate(ctx.pages)]
    res['portals']=results
    allrows=[r for x in results for r in x['rows']]
    ok_cond=all(x['conditions']['matches_trip'] for x in results)
    cands=[r for r in allrows if not r['closed'] and r['total'] is not None and r['total']<=trip['budget_total']]
    cands.sort(key=lambda r:r['total'])
    sel=cands[0] if (cands and ok_cond) else None
    res['candidates']=[r['portal']+'/'+r['no'] for r in cands]; res['selected']=sel
    json.dump(res, open(OUT+'/_search_raw.json','w'), ensure_ascii=False, indent=1)
    L('conditions ok', ok_cond, 'selected', sel and (sel['portal'],sel['no'],sel['total']))
    hold={'attempted':False}
    if sel and len(cands)>1 and cands[1]['total']==sel['total']:
        L('TIE on total → 보류 안 함'); sel=None; hold['skipped']='동일 총액 동률'
    if sel and (len(sys.argv)<2 or sys.argv[1]!='--no-hold'):
        pi=[p['name'] for p in portals].index(sel['portal']); pg=tabs[pi]; base=portals[pi]['url']
        pg.bring_to_front()
        hold_url=base.rstrip('/')+sel['hold_href']
        pg.goto(hold_url); pg.wait_for_load_state('load')
        guard(pg, base, sel['portal'], 'hold page open', hold_url)
        open(f'{EV}/hold_1_form.html','w').write(pg.content()); pg.screenshot(path=f'{EV}/hold_1_form.png', full_page=True)
        submitted=0; final=None
        for attempt in range(3):
            consent(pg,'hold form')
            if '/hold/' not in pg.url: pg.goto(hold_url); pg.wait_for_load_state('load')
            body=pg.inner_text('body')
            hold['form_text_attempt_%d'%attempt]=body[:1500]
            frames=[f for f in pg.frames if f!=pg.main_frame]
            if re.search(r'보류번호', body):
                L('page already shows hold number; no submit'); final='existing'; break
            # 신청 직전 확인: 포트·객실·조건
            pre={'url':pg.url,'port':urlparse(pg.url).port,'expected_port':sel['port'],
                 'room_in_page': sel['no'] in body or sel['room'] in body,
                 'checkin_in_page': trip['checkin'] in body,'frames':[f.url for f in frames]}
            pre['ok']= pre['port']==pre['expected_port'] and pre['room_in_page'] and pre['checkin_in_page'] and bool(frames)
            hold['precheck_%d'%attempt]=pre; L('precheck', json.dumps(pre, ensure_ascii=False))
            if not pre['ok']: hold['stopped']='신청 직전 확인 실패'; break
            fr=frames[0]; cb=fr.locator('input[type=checkbox]')
            hold['iframe']={'url':fr.url,'checkbox_count':cb.count(),'text':fr.inner_text('body')[:500]}
            cb.first.check(); hold['iframe']['checked_after']=cb.first.is_checked()
            try:
                pg.wait_for_function("document.getElementById('agreed').value==='y'", timeout=3000)
            except Exception: pass
            hold['iframe']['parent_agreed']=pg.input_value('#agreed')
            if hold['iframe']['parent_agreed']!='y': hold['stopped']='약관 동의가 부모 양식에 반영 안 됨'; break
            def on_dialog(d):
                dialogs.append({'type':d.type,'message':d.message}); L('DIALOG',d.type,d.message); d.accept()
            pg.once('dialog', on_dialog)
            btn=pg.locator('button:has-text("신청")')
            hold['submit_button']=btn.first.inner_text()
            btn.first.click(); submitted+=1; hold['attempted']=True
            pg.wait_for_load_state('load'); time.sleep(0.5)
            open(f'{EV}/hold_2_after_submit_{attempt}.html','w').write(pg.content())
            if guard(pg, base, sel['portal'], 'after hold submit (attempt %d)'%attempt, hold_url):
                open(f'{EV}/hold_3_reentry_{attempt}.html','w').write(pg.content())
                pg.screenshot(path=f'{EV}/hold_3_reentry_{attempt}.png', full_page=True)
                hold['reentry_text_%d'%attempt]=pg.inner_text('body')[:1500]
                continue
            final='submitted'; break
        hold['submit_clicks']=submitted
        body=pg.inner_text('body'); hold['final_url']=pg.url; hold['final_text']=body
        nums=sorted(set(re.findall(r'보류번호\s*[:：]?\s*([A-Za-z0-9\-]+)', body)))
        hold['hold_numbers_on_page']=nums
        pg.screenshot(path=f'{EV}/hold_4_done.png', full_page=True)
        if nums:
            pg.pdf(path=OUT+'/hold.pdf', format='A4', print_background=True); hold['pdf']=OUT+'/hold.pdf'
    res['hold']=hold; res['relogins']=relogins; res['dialogs']=dialogs
    res['tabs_end']=[{'index':i,'url':t.url,'title':t.title()} for i,t in enumerate(ctx.pages)]
    res['session']={'driver':'playwright chromium headless','contexts':1,'pages':len(ctx.pages),'shared_browser_used':False}
    res['log']=log
    json.dump(res, open(OUT+'/_run_raw.json','w'), ensure_ascii=False, indent=1)
    b.close()
print('DONE')
