#!/usr/bin/env python3
"""system_docs/*.md 의 옛 IBL 액션명을 현재 캐노니컬 형태로 마이그레이션 (Tier A: 능력이 살아있는 rename/op흡수).
사용: python scripts/migrate_systemdocs_actions.py [--apply]"""
import re, sys, glob, os
APPLY = '--apply' in sys.argv
# (old_qualified, new_qualified, inject_params)  inject_params = '' 이면 단순 개명
MAP = [
    ('self:list_goals',     'self:goal',    'op: "list"'),
    ('self:goal_status',    'self:goal',    'op: "status"'),
    ('self:kill_goal',      'self:goal',    'op: "kill"'),
    ('self:log_attempt',    'self:goal',    'op: "log"'),
    ('self:get_attempts',   'self:goal',    'op: "attempts"'),
    ('sense:posts',         'self:blog',    'op: "posts"'),
    ('sense:search_photos', 'self:photo',   'op: "search"'),
    ('sense:rag_search',    'self:memory',  'op: "search"'),
    ('sense:save_health',   'self:health',  'op: "save"'),
    ('sense:apt_trade',     'sense:realty', 'op: "query"'),
    ('limbs:browser_navigate','limbs:browser','op: "navigate"'),
    ('limbs:chrome_connect','limbs:browser','op: "chrome"'),
    ('limbs:radio_play',    'limbs:radio',  'op: "play"'),
    ('limbs:play',          'limbs:music',  'op: "play"'),
    ('limbs:download',      'limbs:music',  'op: "download"'),
    ('others:search_contact','others:neighbors',''),
    ('others:ask_sync',     'others:delegate','mode: "sync"'),
    ('others:delegate_workflow','others:delegate','mode: "workflow"'),
    ('others:delegate_project','others:delegate','scope: "cross"'),
]

def transform(text, old, new, inject):
    n=0
    # 1) [old]{X}  (X 비어있지 않음)
    def repl_braces(m):
        nonlocal n
        inner=m.group(1).strip()
        if inject and inner:
            body=f'{inject}, {inner}'
        elif inject:
            body=inject
        else:
            body=inner
        n+=1
        return f'[{new}]{{{body}}}' if body else f'[{new}]{{}}'
    text=re.sub(r'\['+re.escape(old)+r'\]\{([^{}]*)\}', repl_braces, text)
    # 2) [old] 뒤에 중괄호 없는 경우
    def repl_bare(m):
        nonlocal n; n+=1
        return f'[{new}]{{{inject}}}' if inject else f'[{new}]'
    text=re.sub(r'\['+re.escape(old)+r'\](?!\{)', repl_bare, text)
    return text, n

files=sorted(glob.glob('data/system_docs/*.md'))
grand=0
for f in files:
    txt=open(f,encoding='utf-8').read(); orig=txt; cnt={}
    for old,new,inj in MAP:
        txt,n=transform(txt,old,new,inj)
        if n: cnt[old]=n
    if cnt:
        total=sum(cnt.values()); grand+=total
        print(f"\n{f}: {total} 건")
        for k,v in cnt.items(): print(f"    {k}: {v}")
        if APPLY:
            open(f,'w',encoding='utf-8').write(txt)
print(f"\n{'APPLIED' if APPLY else 'DRY-RUN'} 총 {grand}건")
