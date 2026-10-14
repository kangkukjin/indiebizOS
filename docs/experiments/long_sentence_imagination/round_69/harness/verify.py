"""Independent oracle; verify persisted artifacts, never produce task outputs."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

def expected(data):
    rows=[]; policy=data['policy']
    for slot,book,venue in itertools.product(data['slots'],data['books'],data['venues']):
        ps=[p for p in data['members'] if p['id'] not in data['cancelled'] and p['slots'] is not None and slot['id'] in p['slots']]
        ids=[p['id'] for p in ps]; n=len(ids)
        readers={h['member_id'] for h in data['history'] if h['book_id']==book['id'] and h['member_id'] in ids}
        score=sum(len(set(p['interests'])&set(book['tags'])) for p in ps)
        cost=None if venue['fee'] is None else venue['fee']+n*policy['snack_per_person']
        checks=[(n<policy['minimum'],'인원부족'),(book['pages']>policy['max_pages'],'분량초과'),(n>venue['capacity'],'정원초과'),(slot['id'] not in venue['slots'],'장소시간불가'),(any(p['wheelchair'] for p in ps) and not venue['accessible'],'접근성불가'),(cost is None,'비용미확인'),(cost is not None and cost>policy['budget'],'예산초과')]
        rows.append(dict(slot_id=slot['id'],date=slot['date'],book_id=book['id'],venue_id=venue['id'],attendees=ids,count=n,interest=score,unread=n-len(readers),cost=cost,reasons=[r for ok,r in checks if ok]))
    viable=[r for r in rows if not r['reasons']]
    chosen=min(viable,key=lambda r:(-r['count'],-r['interest'],-r['unread'],r['cost'],r['date'],r['book_id'],r['venue_id'])) if viable else None
    return rows,chosen

def normalize_ai(actual):
    """Map observed field labels, without weakening the task's semantic checks."""
    reason_map={'수용 인원 초과':'정원초과','장소 비용 미확인':'비용미확인',
                '장소 이용 불가 시간':'장소시간불가','책 분량 초과':'분량초과',
                '휠체어 이용자':'접근성불가','최소 인원':'인원부족','예산 초과':'예산초과'}
    def row(r):
        return dict(slot_id=r['slot'],date=r['date'],book_id=r['book'],venue_id=r['venue'],
                    attendees=r['attendees'],count=r['attendee_count'],interest=r['interest_score'],
                    unread=r['unread_count'],cost=r.get('total_cost',r.get('cost',{}).get('total')),
                    reasons=[next((v for k,v in reason_map.items() if s.startswith(k)),s)
                             for s in r.get('rejection_reasons',[])])
    return {**actual,'candidates':[row(r) for r in actual['candidates']],
            'selected':row(actual['selected']) if actual['selected'] else None,
            'unknown_members':[r['id'] if isinstance(r,dict) else r for r in actual['unknown_members']],
            'questions':[{**q,'evidence_ids':q['records'],'next_step':q['next_check_suggestion']} for q in actual['questions']]}

def verify(inp,out,ai=False):
    data=json.loads(inp.read_text()); actual=json.loads((out/'plan.json').read_text()); rows,chosen=expected(data)
    if ai: actual=normalize_ai(actual)
    errors=[]
    def check(ok,label):
        if not ok: errors.append(label)
    key=lambda r:(r['slot_id'],r['book_id'],r['venue_id'])
    by={key(r):r for r in actual['candidates']}
    check(len(actual['candidates'])==len(rows)==len(by),'candidate count / unique keys')
    for row in rows:
        got=by.get(key(row),{})
        for f,value in row.items():
            observed=got.get(f)
            if f in ('reasons','attendees') and isinstance(observed,list): observed=sorted(observed);value=sorted(value)
            check(observed==value,f'{key(row)} {f}: {observed!r} != {value!r}')
    selected=actual['selected']
    check((selected is None)==(chosen is None),'selected null')
    if chosen and selected: check(key(selected)==key(chosen),'chosen rank')
    check(actual['unknown_members']==[p['id'] for p in data['members'] if p['slots'] is None and p['id'] not in data['cancelled']],'unknown members')
    topics={'접근성':{'N01','N02'},'독서속도':{'N03','N04'},'경험과근거':{'N07','N08'}}
    check(len(actual['questions'])==3,'questions count')
    for q in actual['questions']:
        check(set(q['evidence_ids'])==topics.get(q['topic']),f'question evidence {q["topic"]}')
        check(bool(q['question']) and bool(q['next_step']),'question text')
    check(len(actual['drafts'])>=(2 if chosen else 0),'draft count')
    if not chosen: check(not actual['drafts'],'no drafts without a choice')
    for draft in actual['drafts']:
        check(draft['status']=='draft','draft status')
    report=(out/'report.md').read_text()
    rules=actual.get('confirmed_rules',[])
    check(bool(rules),'confirmed rules preserved')
    rules_text=json.dumps(rules,ensure_ascii=False)
    check('3분' in rules_text and 'N06' in rules_text,'confirmed rule content and evidence')
    check('3분' in report,'report confirmed rule')
    for topic in topics: check(topic in report,'report topic '+topic)
    if chosen:
        for f in ('date','book_id','venue_id','cost'): check(str(chosen[f]) in report.replace(',',''), 'report selected '+f)
    return {'input_sha256':hashlib.sha256(inp.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256((out/'plan.json').read_bytes()).hexdigest(),'candidates':len(rows),'selected':chosen,'errors':errors,'passed':not errors}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--evidence',type=Path);p.add_argument('--ai',action='store_true');a=p.parse_args()
    result=verify(a.input,a.output,a.ai); text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.evidence:a.evidence.write_text(text)
    print(text)
    raise SystemExit(0 if result['passed'] else 1)
