"""9회차 합성 자료 — 온라인 상점 2025 상반기 주문·배송·반품·환불 (seed 9). input/ 에 자료, expected.json 은 이 폴더(입력 밖)에."""
import csv, json, random, datetime as dt
from pathlib import Path
H=Path(__file__).resolve().parent; I=H/'input'; rnd=random.Random(9)
D=dt.date; iso=lambda d:d.isoformat(); sl=lambda d:d.strftime('%Y/%m/%d')
SLA={"수도권":2,"지방":3,"제주":5}; BASE=D(2025,7,10); LOST=14
orders=[]
for m in range(1,7):
    days=(D(2025,m+1,1)-D(2025,m,1)).days
    for n in range(1,rnd.randint(960,1040)+1):
        orders.append(dict(주문번호=f"O{m:02d}{n:05d}",주문일=D(2025,m,rnd.randint(1,days)),고객=f"C{rnd.randint(1,800):04d}",
            지역=rnd.choices(["수도권","지방","제주"],[60,33,7])[0],금액=rnd.randint(50,3000)*100,상태="취소" if rnd.random()<0.04 else "결제완료"))
live=[o for o in orders if o['상태']=="결제완료"]; canc=[o for o in orders if o['상태']=="취소"]
noship=set(o['주문번호'] for o in rnd.sample([o for o in live if o['주문일']<D(2025,6,15)],12))
A=[];B=[]
def transit(o,car,late_ok=True):
    s=SLA[o['지역']]; p={"수도권":.10,"지방":.12,"제주":.15}[o['지역']]*(1.8 if car=="B" else 1)
    if late_ok and rnd.random()<p: return s+rnd.randint(1,3)
    return rnd.randint(max(1,s-1),s)
carrier={}
for o in live:
    if o['주문번호'] in noship: continue
    car="A" if rnd.random()<0.55 else "B"; carrier[o['주문번호']]=car
    sh=o['주문일']+dt.timedelta(days=rnd.randint(0,2)); dl=sh+dt.timedelta(days=transit(o,car))
    if car=="B" and o['주문일']>=D(2025,6,27) and rnd.random()<0.3: dl=None
    (A if car=="A" else B).append([o,sh,dl])
# 분실 의심 5: B, 발송 6/20 이전, 도착 없음
lost=rnd.sample([r for r in B if r[2] and r[1]<=D(2025,6,20)],5)
for r in lost: r[2]=None
lostids=set(r[0]['주문번호'] for r in lost)
# 중복 배송 8: 5 같은 택배사 같은 날짜(지연 아님), 3 양쪽 택배사
okrec=lambda r:r[2] and (r[2]-r[1]).days<=SLA[r[0]['지역']] and r[0]['주문번호'] not in lostids
dupsame=rnd.sample([r for r in A if okrec(r)],3)+rnd.sample([r for r in B if okrec(r)],2)
for r in dupsame: (A if r in A else B).append(list(r))
dupcross=rnd.sample([r for r in A if okrec(r) and r not in dupsame],3)
for r in dupcross: B.append([r[0],r[1],r[1]+dt.timedelta(days=1)])
dupids=sorted(set(r[0]['주문번호'] for r in dupsame+dupcross))
# 취소인데 배송 5
cship=rnd.sample(canc,5)
for o in cship:
    sh=o['주문일']+dt.timedelta(days=1); (A if rnd.random()<.5 else B).append([o,sh,sh+dt.timedelta(days=1)])
rnd.shuffle(A); rnd.shuffle(B)
REASON={"불량·파손":["박스가 찌그러져서 왔고 안에 제품도 깨져 있었어요","전원이 안 켜집니다","지퍼가 고장난 채로 옴","화면에 줄이 가 있음 불량인듯","받자마자 봉제선이 터져 있었습니다","액체가 새서 다 젖어 있었음"],
 "오배송":["주문한 색상이 아닌 다른 색이 왔어요","사이즈 M 시켰는데 XL 옴","전혀 다른 상품이 들어 있었습니다","수량이 하나 모자랍니다","옆집 택배가 저한테 왔네요 상품이 다름"],
 "단순 변심":["그냥 마음이 바뀌었어요","생각보다 필요가 없어서요","충동구매였습니다 죄송","선물하려 했는데 필요 없어짐","다른 데서 더 싸게 팔길래","집에 같은 게 있었네요"],
 "배송 지연":["너무 늦게 와서 이미 다른 데서 삼","행사 날짜 지나서 도착함 필요없음","일주일 넘게 걸려서 취소하려다 반품","배송이 늦어 여행 전에 못 받음"],
 "기대와 다름":["사진이랑 실물 색이 너무 달라요","재질이 생각보다 얇고 싸구려 같음","사이즈표대로 샀는데 작아요","설명에는 방수라더니 아님","향이 너무 독해서 못 쓰겠어요"]}
flat=[(k,t) for k,v in REASON.items() for t in v]
deliv=[r for r in A+B if r[2] and r[0]['상태']=="결제완료" and r[0]['주문번호'] not in dupids]
retn=[]
for r in rnd.sample(deliv,300):
    k,t=rnd.choice(flat); retn.append(dict(주문번호=r[0]['주문번호'],반품일=iso(r[2]+dt.timedelta(days=rnd.randint(1,10))),사유=t,_유형=k,_금액=r[0]['금액']))
norefund=set(x['주문번호'] for x in rnd.sample(retn,15))
refunds=[]; mism=[]
for x in retn:
    if x['주문번호'] in norefund: continue
    amt=x['_금액']
    refunds.append([x['주문번호'],iso(D.fromisoformat(x['반품일'])+dt.timedelta(days=rnd.randint(1,5))),amt])
for rf in rnd.sample(refunds,6): rf[2]-=rnd.choice([3000,5000,2500]); mism.append(rf[0])
retids=set(x['주문번호'] for x in retn)
ghost=rnd.sample([o for o in live if o['주문번호'] not in retids and o['주문번호'] not in noship and o['주문일']<D(2025,6,1)],4)
for o in ghost: refunds.append([o['주문번호'],iso(o['주문일']+dt.timedelta(days=12)),o['금액']])
rnd.shuffle(refunds)
# 쓰기
for m in range(1,7):
    with open(I/'orders'/f'orders_2025-{m:02d}.csv','w',newline='') as f:
        w=csv.writer(f); w.writerow(['주문번호','주문일','고객','지역','금액','상태'])
        for o in orders:
            if o['주문일'].month==m: w.writerow([o['주문번호'],iso(o['주문일']),o['고객'],o['지역'],o['금액'],o['상태']])
with open(I/'shipments'/'carrier_A.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(['주문번호','발송일','도착일'])
    for o,s,d in A: w.writerow([o['주문번호'],iso(s),iso(d) if d else ''])
json.dump({"carrier":"B","shipments":[{"order_id":o['주문번호'],"shipped":sl(s),"delivered":sl(d) if d else None,"tracking":f"B{rnd.randint(10**9,10**10-1)}"} for o,s,d in B]},open(I/'shipments'/'carrier_B.json','w'),ensure_ascii=False,indent=0)
with open(I/'returns.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(['주문번호','반품일','사유'])
    for x in retn: w.writerow([x['주문번호'],x['반품일'],x['사유']])
with open(I/'refunds.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(['주문번호','환불일','환불금액']); w.writerows(refunds)
json.dump({"허용배송일수":SLA,"기준일":iso(BASE),"분실의심일수":LOST},open(I/'sla.json','w'),ensure_ascii=False,indent=1)
# 기대값 (독립 계산)
recs=[("A",o,s,d) for o,s,d in A]+[("B",o,s,d) for o,s,d in B]
uniq={}
for c,o,s,d in recs: uniq[(c,o['주문번호'],s,d)]=(c,o,s,d)
ur=list(uniq.values())
shipped_ids={}
for c,o,s,d in recs: shipped_ids.setdefault(o['주문번호'],[]).append(c)
late=[(c,o,s,d) for c,o,s,d in ur if d and (d-s).days>SLA[o['지역']]]
done=[(c,o,s,d) for c,o,s,d in ur if d]
def rate(key):
    out={}
    for c,o,s,d in done:
        k=key(c,o); out.setdefault(k,[0,0]); out[k][1]+=1
    for c,o,s,d in late: out[key(c,o)][0]+=1
    return {k:{"지연":v[0],"도착":v[1],"지연율%":round(100*v[0]/v[1],1)} for k,v in sorted(out.items())}
lostx=sorted(o['주문번호'] for c,o,s,d in ur if d is None and (BASE-s).days>LOST)
omap={o['주문번호']:o for o in orders}; rfmap={}
for oid,day,amt in refunds: rfmap[oid]=amt
monthly={}
for o in orders:
    m=o['주문일'].month; x=monthly.setdefault(f"{m:02d}",dict(주문수=0,취소=0,매출=0,반품=0))
    x['주문수']+=1
    if o['상태']=="취소": x['취소']+=1
    else: x['매출']+=o['금액']
for x in retn: monthly[omap[x['주문번호']]['주문일'].strftime('%m')]['반품']+=1
exp=dict(주문행수=len(orders),취소주문=len(canc),배송기록행수={"A":len(A),"B":len(B)},반품행수=len(retn),환불행수=len(refunds),
 배송기록없는주문=sorted(noship),중복배송주문=dupids,취소인데배송=sorted(o['주문번호'] for o in cship),
 지연건수=len(late),택배사별지연=rate(lambda c,o:c),지역별지연=rate(lambda c,o:o['지역']),
 분실의심=lostx,도착기록없음_전체=sum(1 for c,o,s,d in ur if d is None),
 반품환불없음=sorted(norefund),환불금액다름=sorted(mism),반품없이환불=sorted(o['주문번호'] for o in ghost),
 반품사유유형_심은것={k:sum(1 for x in retn if x['_유형']==k) for k in REASON},서로다른사유문장=len(set(x['사유'] for x in retn)),
 월별=monthly,총매출_취소제외=sum(o['금액'] for o in live))
json.dump(exp,open(H/'expected.json','w'),ensure_ascii=False,indent=1)
print({k:(v if not isinstance(v,(list,dict)) else (len(v) if isinstance(v,list) else v)) for k,v in exp.items() if k not in('월별',)})
