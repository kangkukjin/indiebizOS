"""6회차 합성 입력 — 2025년 개인 가계부(월별 CSV 12개, 규칙, 고정지출). 비민감. 결정론(seed 6)."""
import csv, json, random, os, sys
from collections import defaultdict
random.seed(6)
OUT = os.path.dirname(os.path.abspath(__file__))
VAR = os.path.join(os.path.dirname(OUT), 'input_variant')
# 가게 목록: (설명, 분류, 금액범위, 주간빈도)
MERCH = [
 ("김밥천국","식비",(4500,9000),3),("스타벅스","식비",(4500,7800),3),("이디야커피","식비",(3200,5600),2),
 ("배달의민족","식비",(14000,32000),2),("쿠팡이츠","식비",(12000,29000),1),("홈플러스","식비",(23000,96000),1),
 ("이마트","식비",(31000,120000),1),("GS25","식비",(1500,8900),3),("CU편의점","식비",(1200,7600),3),
 ("카카오T","교통",(4800,18000),2),("티머니지하철","교통",(1400,2100),3),("SK에너지 주유","교통",(50000,80000),0.5),
 ("약국","의료",(3500,18000),0.5),("서울내과","의료",(8000,25000),0.25),
 ("쿠팡","쇼핑",(9000,68000),1.5),("무신사","쇼핑",(29000,89000),0.3),("다이소","쇼핑",(3000,15000),1),
 ("CGV","문화",(15000,15000),0.4),("교보문고","문화",(12000,38000),0.3),
]
# 규칙에 없는 가게(AI 분류 대상) — 기대 분류는 expected 에만
UNCAT = [("PAYPAL *STEAMGAMES","문화"),("NAVERPAY 결제","쇼핑"),("AMZN Mktp US","쇼핑"),("APPLE.COM/BILL","구독"),
 ("OLIVEYOUNG 강남","쇼핑"),("HAIRSHOP BLUE","미용"),("TAXI 8823","교통"),("KAKAOPAY 결제","쇼핑"),
 ("SSG.COM","식비"),("YANOLJA","여행"),("KTX 코레일","교통"),("맘스터치","식비"),("파리바게뜨","식비"),
 ("메가MGC커피","식비"),("클래스101","문화"),("당근페이","쇼핑"),("동네세탁소","생활"),("우체국","생활")]
FIXED = [  # 이름,키워드,금액,일,분류
 ("넷플릭스","넷플릭스",17000,5,"구독"),("유튜브프리미엄","유튜브프리미엄",14900,12,"구독"),
 ("스포티파이","스포티파이",10900,20,"구독"),("멜론","멜론",10900,8,"구독"),("왓챠","왓챠",12900,15,"구독"),
 ("쿠팡와우","쿠팡와우 멤버십",7890,3,"구독"),("iCloud","iCloud 저장공간",3300,10,"구독"),
 ("관리비","아파트 관리비",180000,25,"주거"),("통신비","SKT 통신요금",55000,27,"주거"),
]
rules = [{"키워드":"환불","분류":"환불"}] + [{"키워드":m[0],"분류":m[1]} for m in MERCH] + [{"키워드":f[1],"분류":f[4]} for f in FIXED]
fixed = [{"이름":f[0],"키워드":f[1],"금액":f[2],"결제일":f[3],"분류":f[4]} for f in FIXED]
DAYS = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}
rows_by_month = defaultdict(list)
def add(m,d,desc,amt,pay="카드"):
    rows_by_month[m].append({"일자":f"2025-{m:02d}-{d:02d}","설명":desc,"금액":str(amt),"결제수단":pay})
for m in range(1,13):
    for desc,cat,(lo,hi),freq in MERCH:
        n = int(round(freq*4.3*1.6*random.uniform(0.7,1.3)))
        mult = 2.6 if (cat=="식비" and m==12) else 1.0   # 12월 식비 급증(기대: 튄 달)
        for _ in range(n):
            add(m,random.randint(1,DAYS[m]),desc,int(random.randint(lo,hi)*mult//100*100))
    for desc,cat in UNCAT:
        for _ in range(random.choice([0,1,1,2])):
            add(m,random.randint(1,DAYS[m]),desc,random.randint(3000,60000)//100*100)
    for name,kw,amt,day,cat in FIXED:
        if name=="넷플릭스" and m==6: continue          # 빠진 달
        if name=="관리비" and m==9: continue            # 빠진 달
        if name=="통신비" and m==4: amt=89000           # 평소와 다른 금액
        add(m,day,kw,amt,"자동이체" if cat=="주거" else "카드")
# 의료 급증(2월 병원 큰 결제) — 기대: 튄 달
add(2,17,"서울내과",350000)
# 환불 3건(음수)
add(3,9,"환불 무신사",-39000); add(7,22,"환불 쿠팡",-25000); add(10,5,"환불 교보문고",-18000)
# 중복 결제 3건(같은 날·가게·금액 두 번)
for m,d,desc,amt in [(3,14,"스타벅스",6100),(8,2,"이마트",84300),(11,20,"CGV",15000)]:
    add(m,d,desc,amt); add(m,d,desc,amt)
def write(root, skip_month=None, malformed=False):
    os.makedirs(os.path.join(root,'ledger'),exist_ok=True)
    for m in range(1,13):
        if m==skip_month: continue
        rows = sorted(rows_by_month[m], key=lambda r:(r["일자"],r["설명"]))
        if malformed and m==3:
            rows.insert(5, {"일자":"2025-03-03","설명":"GS25","금액":"1,200원","결제수단":"카드"})
        with open(os.path.join(root,'ledger',f'tx_2025-{m:02d}.csv'),'w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=["일자","설명","금액","결제수단"]); w.writeheader(); w.writerows(rows)
    json.dump(rules,open(os.path.join(root,'rules.json'),'w'),ensure_ascii=False,indent=1)
    json.dump(fixed,open(os.path.join(root,'fixed.json'),'w'),ensure_ascii=False,indent=1)
write(OUT); write(VAR, skip_month=7, malformed=True)
# ── 기대값(gen 기준 손계산) ──
allrows=[r for m in range(1,13) for r in rows_by_month[m]]
catof={}
for m in MERCH: catof[m[0]]=m[1]
for f in FIXED: catof[f[1]]=f[4]
exp_uncat={d:c for d,c in UNCAT}
def cat(desc):
    if desc.startswith("환불"): return "환불"
    return catof.get(desc) or ("AI:"+exp_uncat[desc])
bycat=defaultdict(lambda: defaultdict(int))
for r in allrows:
    a=int(r["금액"]); c=cat(r["설명"]); m=r["일자"][5:7]
    if a<0: continue
    bycat[c][m]+=a
spikes=[]
for c,ms in bycat.items():
    for m,v in ms.items():
        others=[x for k,x in ms.items() if k!=m]
        if others and v>=2*sum(others)/len(others): spikes.append((c,m,v,round(sum(others)/len(others))))
dups=defaultdict(int)
for r in allrows: dups[(r["일자"],r["설명"],r["금액"])]+=1
exp={"행수":len(allrows),"월별행수":{f"{m:02d}":len(rows_by_month[m]) for m in range(1,13)},
 "총지출(환불제외)":sum(int(r["금액"]) for r in allrows if int(r["금액"])>0),"환불합":sum(int(r["금액"]) for r in allrows if int(r["금액"])<0),
 "중복결제":[k for k,v in dups.items() if v>1],"고정지출_빠진달":[["넷플릭스","06"],["관리비","09"]],"고정지출_금액다름":[["통신비","04",89000]],
 "튄달":spikes,"AI분류대상_가게수":len(UNCAT),"AI분류대상_행수":sum(1 for r in allrows if r["설명"] in exp_uncat),
 "구독겹침_기대":[["스포티파이","멜론"],["넷플릭스","왓챠"]],"분류별연간":{c:sum(v.values()) for c,v in bycat.items()}}
json.dump(exp,open(os.path.join(OUT,'expected.json'),'w'),ensure_ascii=False,indent=1)
print(json.dumps(exp,ensure_ascii=False,indent=1))
