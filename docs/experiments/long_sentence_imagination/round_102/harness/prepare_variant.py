from api import *
import copy,hashlib
V=BASE/'harness/variant_private';V.mkdir(exist_ok=True)
new=[]
for i in range(200):new.append({'quote_id':f'D-{i:03}','vendor':'D','item':f'K{i:03}','pack_price':str((135+i)*5),'pack':'5','shipping':'80','delivery':'2026-10-30','valid_until':'2026-11-12','confirmed_copy':True,'from_archive':False,'source':'D-2026-10-28','note':''})
(V/'new_vendor.json').write_text(json.dumps(new,ensure_ascii=False))
rules='''기존 원천/정책은 102회차와 동일 판본. 이번 요구는 비교 계획이며 원장에는 절대 추가하지 않는다.
D는 pack_price(포장당 원), pack(개/포장), shipping(품목별 한 주문의 고정 운송비 원). 부족이 0이면 주문·배송비 모두0. 부족>0이면 ceil(부족/pack)*pack_price+shipping. 기존 공급업체 배송비0.
유효성·별칭·중복·필요일 규칙은 기존과 동일. 납기 우선: 유효후보 delivery,cost,vendor 순. 예산 우선: cost,delivery,vendor 순. 각 안의 도서관 합계와 예산 초과 여부를 표시한다. 예산을 넘겨도 비교 제안 금액 자체는 지우지 않는다.
재고이동 안: L1->L3만 가능. 품목별 max(L1실사용가능-L1요청,0)와 L3부족 중 작은 수량을 보낸다. 단가 7원/개, 2026-10-29 도착(전 품목). 이동 원천은 예약재고 제외. L1요청을 침해하지 않는다. L3는 이동분만큼 부족을 줄여 다시 두 정책을 비교한다. 이동 안 합계는 구매비+이동비이며 두 값을 구분.
반환은 base/with_transfer 각각 deadline/budget의 libraries와 total_cost, transfers(item/from/to/quantity/cost), transfer_cost, 총합을 포함. 이름이 달라도 의미 동등하고 전건 대조 가능하면 된다. 이전 출고는 이 새 계획에서 재사용/추가하지 않는다.
'''
(V/'RULES_VARIANT.txt').write_text(rules)
e=json.loads((BASE/'harness/expected.json').read_text());original=json.loads((BASE/'source/quotes_ab.json').read_text());original += [json.loads(x) for x in (BASE/'source/quotes_c_archive.txt').read_text().splitlines()]
for q in original:q['from_archive']=q['vendor']=='C';q['shipping']=0
for q in new:
 q['pack']=int(q['pack']);q['unit_price']=int(q['pack_price'])//q['pack'];q['shipping']=int(q['shipping'])
quotes=original+new
m={(l['library'],r['item']):r for l in e['libraries'] for r in l['lines']}
transfers=[]
for item in sorted(r['item'] for r in e['libraries'][0]['lines']):
 a=m['L1',item];b=m['L3',item];qty=min(max(a['available']-a['requested'],0),b['shortage'])
 if qty:transfers.append({'item':item,'from':'L1','to':'L3','quantity':qty,'cost':qty*7})
tmap={x['item']:x['quantity'] for x in transfers}
result={'transfers':transfers,'transfer_cost':sum(x['cost'] for x in transfers)}
for transfer,key in [(False,'base'),(True,'with_transfer')]:
 plans={}
 for policy in ['deadline','budget']:
  libs=[]
  for li in e['libraries']:
   lines=[];lib=li['library'];need='2026-11-01' if lib=='L3' else '2026-11-10'
   for r in li['lines']:
    available=r['available']+(tmap.get(r['item'],0) if transfer and lib=='L3' else 0);short=max(0,r['requested']-available)
    valid=[]
    for q in quotes:
     if q['item']!=r['item'] or q['unit_price'] is None or q['delivery'] is None or q['delivery']>need or q['valid_until']<'2026-10-28' or (q['from_archive'] and not q['confirmed_copy']):continue
     qty=((short+q['pack']-1)//q['pack'])*q['pack'];cost=qty*q['unit_price']+q['shipping']
     valid.append((q,qty,cost))
    chosen=min(valid,key=lambda x:(x[0]['delivery'],x[2],x[0]['vendor']) if policy=='deadline' else (x[2],x[0]['delivery'],x[0]['vendor'])) if short and valid else None
    lines.append({'item':r['item'],'shortage':short,'purchase_qty':chosen[1] if chosen else 0,'cost':chosen[2] if chosen else 0,'vendor':chosen[0]['vendor'] if chosen else None,'quote_id':chosen[0]['quote_id'] if chosen else None,'status':'stock' if short==0 else 'ready' if chosen else 'hold'})
   total=sum(x['cost'] for x in lines);libs.append({'library':lib,'lines':lines,'total_cost':total,'over_budget':total>150000})
  total=sum(x['total_cost'] for x in libs);plans[policy]={'libraries':libs,'total_cost':total,'total_with_transfer':total+(result['transfer_cost'] if transfer else 0)}
 result[key]=plans
(BASE/'harness/variant_expected.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print('variant expectations',[(k,{p:v['total_with_transfer'] for p,v in result[k].items()}) for k in ['base','with_transfer']],result['transfer_cost'],len(transfers))
