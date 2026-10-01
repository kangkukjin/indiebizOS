"""Classify observed rounds without equating all checks or exploration with waste."""
import json
from collections import defaultdict
from fixture import HERE, dump


def main():
    programs=[json.loads(s) for s in (HERE/'ai_programs.jsonl').read_text().splitlines()]
    by_seq={(p['episode'],p['seq']):p for p in programs}
    rows=json.loads((HERE/'round_costs.json').read_text())
    summaries=json.loads((HERE/'ai_metrics.json').read_text())
    totals=defaultdict(lambda:dict(rounds=0,input=0,output=0,cache_read=0))
    for r in rows:
        issued=[by_seq[(r['episode'],n)] for n in r['issued_tool_inputs']]
        labels=[]
        if r['phase']!='execute':
            labels=[{'plan':'계획·계약 탐색','review':'중간 감독 검수','evaluate':'최종 평가',
                     'classify':'요구 분류','capability_guard':'완료 후 응답 점검'}.get(r['phase'],r['phase'])]
        else:
            for p in issued:
                q=p['request'] or {}; code=q.get('code',''); leaves=p.get('leaf_counts',{})
                if p.get('ok') is False:label='검사 거절을 받은 작성'
                elif q.get('describe') or '/skills/' in code:label='계약·교재 탐색'
                elif q.get('read_result',{}).get('calls'):label='이전 호출 목록 탐색'
                elif q.get('read_result'):label='저장 본문 확인'
                elif q.get('check'):
                    before=[x for x in programs if x['episode']==r['episode'] and x['seq']<p['seq']]
                    label='거절 후 재작성·검사' if before and before[-1].get('ok') is False else '실행 전 검사'
                elif leaves.get('self:write'):label='파일 저장·재읽기'
                elif leaves.get('self:read') and '/input' in json.dumps(q,ensure_ascii=False):label='원자료 수집'
                elif q.get('op')=='bind':label='과제 원장 연결'
                elif 'verified:true' in code or 'verified: true' in code:label='결과·원천 대조 검증'
                else:label='계산·보고서 구성'
                if label not in labels:labels.append(label)
            if not labels:labels=['추론·응답 정리(독립 도구 호출 없음)']
        r['purpose']=' + '.join(labels)
        r['necessity_assessment']='당시 요구·계약·확인 범위에 비춰 분류. 검사·탐색을 일괄 낭비로 판단하지 않음.'
        if any('거절' in s for s in labels):
            r['necessity_assessment']='작성 오류로 추가된 수정 경로. 라운드 전체가 제거 가능한 순수 낭비라는 뜻은 아님.'
        v=totals[(r['episode'],r['purpose'])];v['rounds']+=1
        for source,target in [('input_tokens','input'),('output_tokens','output'),('cached_input_tokens','cache_read')]:v[target]+=r['usage'].get(source,0)
    for episode in summaries:
        if episode['ended_at'] is None:continue
        own=[r for r in rows if r['episode']==episode['id']]
        assert sum(r['usage']['input_tokens'] for r in own)==episode['totals']['input'],episode['id']
        assert sum(r['usage']['output_tokens'] for r in own)==episode['totals']['output'],episode['id']
    dump(HERE/'round_costs.json',rows)
    dump(HERE/'cost_by_purpose.json',[dict(episode=e,purpose=p,**v) for (e,p),v in totals.items()])


if __name__=='__main__':main()
