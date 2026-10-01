import csv, json, random, math
random.seed(20260929)
D=["12-12","12-13","12-19"]
teams=["기획","개발","영업","디자인","운영","재무"]
rows=[]
for i in range(1,121):
    r=random.random()
    att="Y" if r<0.72 else ("미정" if r<0.87 else "N")
    ds=[d for d in D if random.random()<0.6] if att!="N" else []
    if att!="N" and not ds: ds=[random.choice(D)]
    dr=random.random()
    diet="채식" if dr<0.12 else ("견과류 알레르기" if dr<0.17 else "")
    note=""
    if random.random()<0.08: note='늦게 도착, 7시 이후'
    if random.random()<0.05: note='"주차 필요, 차량 2대"'  # 인용 쉼표 (csv writer가 처리)
    rows.append({"id":f"E{i:03d}","team":random.choice(teams),"attend":att,"dates":";".join(ds),"diet":diet,"note":note.strip('"')})
with open("input/responses.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
venues=[
 {"id":"V1","name":"한강 루프탑홀","capacity":90,"dates":["12-12","12-19"],"price_per_head":45000,"rental_fee":800000,"vegetarian":True,"review_file":"reviews/V1.txt"},
 {"id":"V2","name":"성수 창고 라운지","capacity":70,"dates":["12-12","12-13","12-19"],"price_per_head":38000,"rental_fee":500000,"vegetarian":None,"review_file":"reviews/V2.txt"},
 {"id":"V3","name":"광화문 연회장","capacity":150,"dates":["12-13","12-19"],"price_per_head":52000,"rental_fee":0,"vegetarian":True,"review_file":"reviews/V3.txt"},
 {"id":"V4","name":"을지로 비스트로","capacity":60,"dates":["12-12","12-13"],"price_per_head":35000,"rental_fee":300000,"vegetarian":False,"review_file":"reviews/V4.txt"},
]
json.dump({"event":"2026 송년회","budget":3500000,"venues":venues},open("input/venues.json","w"),ensure_ascii=False,indent=1)
import os
os.makedirs("input/reviews",exist_ok=True)
rv={"V1":["야경이 정말 좋고 직원이 친절했어요.","음향 장비가 자주 끊겨서 사회자가 고생했습니다.","엘리베이터가 하나라 입장에 20분 걸렸어요.","채식 코스가 따로 있어서 좋았습니다."],
 "V2":["분위기 힙하고 넓어요.","난방이 약해서 12월엔 추웠습니다. 담요 요청 필요.","주차 공간이 거의 없어요.","케이터링 양이 부족했다는 말이 많았습니다.","대관 시간 초과 요금이 비쌉니다."],
 "V3":["격식 있는 행사에 좋고 음향 완벽.","가격이 다소 비싸지만 서비스가 확실함.","분위기가 딱딱하다는 의견이 있었어요."],
 "V4":["음식 맛이 최고.","60명 꽉 채우니 너무 좁았어요.","채식 메뉴 요청했는데 준비가 안 된다고 했어요."]}
for k,v in rv.items():
    open(f"input/reviews/{k}.txt","w").write("\n".join(v)+"\n")
# expected
def cnt(att,d): return sum(1 for r in rows if r["attend"]==att and d in r["dates"].split(";"))
exp={}
for d in D:
    y=cnt("Y",d); m=cnt("미정",d)
    veg=sum(1 for r in rows if r["attend"]=="Y" and d in r["dates"].split(";") and r["diet"]=="채식")
    alg=sum(1 for r in rows if r["attend"]=="Y" and d in r["dates"].split(";") and r["diet"]=="견과류 알레르기")
    exp[d]={"확정":y,"미정":m,"채식":veg,"알레르기":alg}
print(json.dumps(exp,ensure_ascii=False))
print("att", {a:sum(1 for r in rows if r['attend']==a) for a in ["Y","미정","N"]})
opts=[]
for v in venues:
    for d in v["dates"]:
        e=exp[d]; need=e["확정"]+e["미정"]
        cost=v["rental_fee"]+v["price_per_head"]*e["확정"]
        veg_ok = "확인필요" if v["vegetarian"] is None else v["vegetarian"]
        ok = v["capacity"]>=need and cost<=3500000 and not (e["채식"]>0 and v["vegetarian"] is False)
        opts.append((v["id"],d,need,v["capacity"],cost,veg_ok,ok))
for o in opts: print(o)
