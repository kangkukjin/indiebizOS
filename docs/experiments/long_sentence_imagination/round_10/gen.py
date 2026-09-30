"""10회차 합성 자료 — 학원 월간 운영 점검(2025-09, 2025-10, 수리 뒤 재측정용 2025-11). input_09/·input_10/ 에 자료, expected_MM.json 은 입력 밖."""
import csv, json, random, datetime as dt
from pathlib import Path
H=Path(__file__).resolve().parent
NOTES={"조치 필요":["아이가 수업 내용을 전혀 못 따라간다고 집에서 웁니다","숙제 양이 너무 많아 새벽까지 합니다 조정 부탁드려요","같은 반 아이와 다툼이 있었다는데 확인 부탁드립니다","지난달 환불 요청드렸는데 아직 처리가 안 됐어요","선생님 말투가 무섭다고 학원 가기 싫어합니다","차량 하차 위치가 계속 바뀌어 아이가 헤맸습니다"],
 "문의":["다음 달 시험 범위가 어디까지인가요","보강 수업은 언제 잡을 수 있을까요","형제 할인 적용되는지 궁금합니다","교재는 따로 구매해야 하나요","겨울방학 특강 일정 알려주세요"],
 "감사·칭찬":["요즘 수학에 자신감이 붙었다고 좋아합니다 감사합니다","선생님이 꼼꼼히 봐주셔서 성적이 올랐어요","아이가 학원 가는 날을 기다립니다","상담 전화 친절하게 해주셔서 고맙습니다"],
 "단순 전달":["이번 주 금요일은 가족 행사로 결석합니다","다음 주부터 차량 이용 안 합니다","연락처가 바뀌었습니다 010으로 시작하는 새 번호입니다","독감이라 며칠 쉬겠습니다"]}
FLAT=[(k,t) for k,v in NOTES.items() for t in v]
def build(month, seed, twist):
    rnd=random.Random(seed); I=H/f'input_{month:02d}'; (I/'attendance').mkdir(parents=True,exist_ok=True)
    classes=[("초등수학A",180000),("초등수학B",180000),("중등수학A",240000),("중등수학B",240000),("중등영어A",220000),("고등수학A",300000),("고등영어A",280000),("논술A",200000)]
    students=[]
    for n in range(1,321):
        c=rnd.choice(classes); students.append(dict(학번=f"S{n:04d}",이름=f"학생{n:03d}",반=c[0],수강료=c[1],상태="퇴원" if rnd.random()<0.06 else "재원"))
    active=[s for s in students if s['상태']=="재원"]; left=[s for s in students if s['상태']=="퇴원"]
    days=[d for d in (dt.date(2025,month,1)+dt.timedelta(n) for n in range(31)) if d.month==month and d.weekday()<5]
    # 출결: 재원생 × 수업일. 상태 출석/지각/결석
    low=set(s['학번'] for s in rnd.sample(active,14)); streak=set(s['학번'] for s in rnd.sample([s for s in active if s['학번'] not in low],9))
    att=[]
    for s in active:
        p_abs=0.30 if s['학번'] in low else 0.04
        seq=[]
        for d in days:
            r=rnd.random(); seq.append("결석" if r<p_abs else "지각" if r<p_abs+0.05 else "출석")
        if s['학번'] in streak:
            k=rnd.randint(0,len(days)-3); seq[k:k+3]=["결석"]*3
        for d,st in zip(days,seq): att.append([s['학번'],d.isoformat(),st])
    ghost=rnd.sample(left,4)
    for s in ghost:
        for d in rnd.sample(days,3): att.append([s['학번'],d.isoformat(),"출석"])
    rnd.shuffle(att)
    weeks={}
    for row in att:
        d=dt.date.fromisoformat(row[1]); weeks.setdefault((d.day-1)//7+1,[]).append(row)
    for w,rows in weeks.items():
        if twist=="format" and w==3:   # 10월 3주차: 열 순서·이름이 다르고 상태가 O/L/X
            with open(I/'attendance'/f'week{w}.csv','w',newline='') as f:
                wr=csv.writer(f); wr.writerow(['date','student_id','mark'])
                for sid,d,st in rows: wr.writerow([d,sid,{"출석":"O","지각":"L","결석":"X"}[st]])
        else:
            with open(I/'attendance'/f'week{w}.csv','w',newline='') as f:
                wr=csv.writer(f); wr.writerow(['학번','일자','상태']); wr.writerows(rows)
    # 성적: 이전·이번 시험
    drop=set(s['학번'] for s in rnd.sample(active,11)); scores=[]
    for s in active:
        prev=rnd.randint(45,100); cur=max(0,min(100,prev+rnd.randint(-12,12)))
        if s['학번'] in drop: prev=rnd.randint(70,100); cur=prev-rnd.randint(20,35)
        e={"id":s['학번'],"prev":prev,"cur":cur}
        if rnd.random()<0.03 and s['학번'] not in drop: e["cur"]=None   # 미응시
        scores.append(e)
    json.dump({"month":f"2025-{month:02d}","exam":{"prev":"지난달 월말평가","cur":"이번 달 월말평가"},"scores":scores},open(I/'scores.json','w'),ensure_ascii=False,indent=0)
    # 수납
    unpaid=set(s['학번'] for s in rnd.sample(active,13)); pays=[]
    for s in active:
        if s['학번'] in unpaid: continue
        pays.append([s['학번'],dt.date(2025,month,rnd.randint(1,10)).isoformat(),s['수강료']])
    dup=rnd.sample(pays,5)
    for p in dup: pays.append([p[0],(dt.date.fromisoformat(p[1])+dt.timedelta(1)).isoformat(),p[2]])
    short=rnd.sample([p for p in pays if p not in dup and pays.count(p)==1 and sum(1 for q in pays if q[0]==p[0])==1],6)
    for p in short: p[2]-=rnd.choice([20000,30000,50000])
    rnd.shuffle(pays)
    with open(I/'students.csv','w',newline='') as f:
        wr=csv.writer(f); wr.writerow(['학번','이름','반','수강료','상태'])
        for s in students: wr.writerow([s['학번'],s['이름'],s['반'],s['수강료'],s['상태']])
    with open(I/'payments.csv','w',newline='') as f:
        wr=csv.writer(f); wr.writerow(['학번','납부일','금액']); wr.writerows(pays)
    notes=[]
    for s in rnd.sample(active,60):
        k,t=rnd.choice(FLAT); notes.append(dict(학번=s['학번'],일자=rnd.choice(days).isoformat(),메모=t,_유형=k))
    with open(I/'notes.csv','w',newline='') as f:
        wr=csv.writer(f); wr.writerow(['학번','일자','메모'])
        for n in notes: wr.writerow([n['학번'],n['일자'],n['메모']])
    json.dump({"출석률_기준":0.8,"연속결석_기준":3,"성적하락_기준":20,"지각은_출석으로_친다":True},open(I/'policy.json','w'),ensure_ascii=False,indent=1)
    # 기대값(독립 계산)
    by={}
    for sid,d,st in att: by.setdefault(sid,[]).append((d,st))
    act_ids=set(s['학번'] for s in active); cls={s['학번']:s['반'] for s in students}
    lowx=[];strx=[];rate={}
    for sid in sorted(act_ids):
        seq=[st for d,st in sorted(by.get(sid,[]))]; ok=sum(1 for st in seq if st!="결석"); r=ok/len(seq); rate[sid]=r
        if r<0.8: lowx.append(sid)
        run=mx=0
        for st in seq:
            run=run+1 if st=="결석" else 0; mx=max(mx,run)
        if mx>=3: strx.append(sid)
    paid={}
    for sid,d,a in pays: paid.setdefault(sid,[]).append(a)
    fee={s['학번']:s['수강료'] for s in students}
    cl={}
    for sid in act_ids:
        c=cl.setdefault(cls[sid],dict(학생수=0,출석=0,수업=0,점수합=0,응시=0)); c['학생수']+=1
        seq=[st for d,st in by[sid]]; c['출석']+=sum(1 for st in seq if st!="결석"); c['수업']+=len(seq)
    for e in scores:
        if e['cur'] is not None: c=cl[cls[e['id']]]; c['점수합']+=e['cur']; c['응시']+=1
    exp=dict(재원=len(active),퇴원=len(left),출결행수=len(att),출결파일=len(weeks),성적행수=len(scores),수납행수=len(pays),메모행수=len(notes),
        출석률미달=lowx,연속결석=strx,성적하락=sorted(e['id'] for e in scores if e['cur'] is not None and e['prev']-e['cur']>=20),미응시=sorted(e['id'] for e in scores if e['cur'] is None),
        미납=sorted(sid for sid in act_ids if sid not in paid),중복납부=sorted(sid for sid,v in paid.items() if len(v)>1),
        금액부족=sorted(sid for sid,v in paid.items() if len(v)==1 and v[0]<fee[sid]),퇴원생출석=sorted(set(s['학번'] for s in ghost)),
        반별={k:{"학생수":v['학생수'],"출석률%":round(100*v['출석']/v['수업'],1),"평균점수":round(v['점수합']/v['응시'],1)} for k,v in sorted(cl.items())},
        메모유형_심은것={k:sum(1 for n in notes if n['_유형']==k) for k in NOTES},수납합계=sum(a for v in paid.values() for a in v))
    json.dump(exp,open(H/f'expected_{month:02d}.json','w'),ensure_ascii=False,indent=1)
    print(month,{k:(len(v) if isinstance(v,list) else v) for k,v in exp.items() if k not in('반별',)})
import sys
for m,seed,tw in ((9,109,None),(10,110,"format"),(11,111,None)):
    if len(sys.argv)<2 or str(m) in sys.argv[1:]: build(m,seed,tw)
