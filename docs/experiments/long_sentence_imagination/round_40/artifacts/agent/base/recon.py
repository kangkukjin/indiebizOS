
import json,sys,csv,datetime as dt,collections,openpyxl,io
B,OUT,CF=sys.argv[1],sys.argv[2],sys.argv[3]
D=lambda s:dt.date.fromisoformat(s)
ASOF=D('2026-09-30')
def jl(n): return json.load(open(f'{B}/{n}',encoding='utf-8-sig'))
inv=jl('invoices.json'); pur=jl('purchases.json'); clients=jl('clients.json'); vendors=jl('vendors.json')
summ=jl('bank_summary.json'); tgt=jl('targets.json'); contracts=json.load(open(CF,encoding='utf-8'))
raw=open(f'{B}/bank_2026-09.csv',encoding='utf-8-sig',newline='').read()
rows=list(csv.DictReader(io.StringIO(raw)))
for i,r in enumerate(rows):
    r['line']=i+2; r['amount']=int(r['amount'].replace(',','')); r['balance']=int(r['balance'].replace(',',''))
types=collections.Counter(r['type'] for r in rows)
assert set(types)<= {'입금','출금'}, types
dep=[r for r in rows if r['type']=='입금']; wd=[r for r in rows if r['type']=='출금']
# ---------- 1. 입금-청구 대사
name2c={}
for c in clients:
    for n in c['bank_names']:
        assert n not in name2c, n; name2c[n]=c['id']
cname={c['id']:c['name'] for c in clients}
bal={i['id']:i['amount'] for i in inv}
invmap={i['id']:i for i in inv}
alloc_log=[]; prepay=[]; unknown=[]; memo_diff=[]
dep_sorted=sorted(dep,key=lambda r:(r['date'],r['line']))  # 같은 날짜는 CSV 순서
for r in dep_sorted:
    cid=name2c.get(r['counterparty'])
    rec={'line':r['line'],'date':r['date'],'counterparty':r['counterparty'],'amount':r['amount'],'memo':r['memo']}
    if cid is None:
        rec.update(status='미확인 입금',client_id=None); unknown.append(rec); alloc_log.append(rec); continue
    opn=sorted([i for i in inv if i['client_id']==cid and bal[i['id']]>0 and i['issued']<=r['date']],key=lambda i:(i['due'],i['id']))
    rec['client_id']=cid; rec['client']=cname[cid]; rec['allocations']=[]
    ex=[i for i in opn if bal[i['id']]==r['amount']]
    left=r['amount']
    if ex:
        i=ex[0]; rec['method']='정확일치'; rec['exact_candidates']=[e['id'] for e in ex]; rec['allocations'].append({'invoice':i['id'],'applied':left,'invoice_balance_after':0}); bal[i['id']]=0; left=0
    else:
        rec['method']='오래된순 충당' if opn else '선입금(미결 청구 없음)'
        for i in opn:
            if left==0: break
            a=min(left,bal[i['id']]); bal[i['id']]-=a; left-=a
            rec['allocations'].append({'invoice':i['id'],'applied':a,'invoice_balance_after':bal[i['id']]})
    rec['prepayment']=left
    if left>0: prepay.append({'line':r['line'],'date':r['date'],'client_id':cid,'client':cname[cid],'amount':left})
    paid=[a['invoice'] for a in rec['allocations']]
    if 'INV-' in r['memo']:
        ref='INV-'+r['memo'].split('INV-')[1][:4]
        if paid!=[ref]: memo_diff.append({'line':r['line'],'memo_ref':ref,'allocated':paid,'memo_ref_client':invmap.get(ref,{}).get('client_id'),'deposit_client':cid})
    alloc_log.append(rec)
dep_total=sum(r['amount'] for r in dep)
applied_total=sum(a['applied'] for r in alloc_log for a in r.get('allocations',[]))
prepay_total=sum(p['amount'] for p in prepay); unknown_total=sum(u['amount'] for u in unknown)
assert applied_total+prepay_total+unknown_total==dep_total
openinv=[]
for i in sorted(inv,key=lambda i:(i['due'],i['id'])):
    if bal[i['id']]>0:
        dpd=(ASOF-D(i['due'])).days
        b='기한내' if dpd<=0 else '1-30' if dpd<=30 else '31-60' if dpd<=60 else '61-90' if dpd<=90 else '90+'
        openinv.append({'invoice':i['id'],'client_id':i['client_id'],'client':i['client'],'issued':i['issued'],'due':i['due'],'amount':i['amount'],'balance':bal[i['id']],'days_past_due':max(dpd,0),'bucket':b,'partially_paid':bal[i['id']]<i['amount']})
BK=['기한내','1-30','31-60','61-90','90+']
buckets={k:sum(o['balance'] for o in openinv if o['bucket']==k) for k in BK}
ar_total=sum(o['balance'] for o in openinv)
assert sum(buckets.values())==ar_total
assert ar_total==sum(i['amount'] for i in inv)-applied_total
bycl=collections.defaultdict(lambda:{'balance':0,'count':0,'overdue':0,'buckets':{k:0 for k in BK}})
for o in openinv:
    x=bycl[o['client_id']]; x['balance']+=o['balance']; x['count']+=1; x['buckets'][o['bucket']]+=o['balance']
    if o['bucket']!='기한내': x['overdue']+=o['balance']
prep_by=collections.Counter()
for p in prepay: prep_by[p['client_id']]+=p['amount']
top5=sorted(bycl.items(),key=lambda kv:(-kv[1]['balance'],kv[0]))[:5]
top5=[{'rank':n+1,'client_id':k,'client':cname[k],**v,'prepayment_credit':prep_by.get(k,0)} for n,(k,v) in enumerate(top5)]
# ---------- 2. 출금 대사
wb=openpyxl.load_workbook(f'{B}/payroll_2026-09.xlsx',data_only=True)
def sheet_total(sh,col):
    ws=wb[sh]; hdr=[c.value for c in ws[1]]; ci=hdr.index(col)
    data=[];tot=None
    for row in ws.iter_rows(min_row=2,values_only=True):
        if row[0] is None: continue
        if str(row[0]).strip()=='합계': tot=row[ci]; continue
        data.append((row[0],row[ci]))
    return data,sum(v for _,v in data),tot
pd,psum,ptot=sheet_total('급여','순지급'); idat,isum,itot=sheet_total('4대보험','회사부담합계')
# 4대보험 구성항목 합과 회사부담합계 열 대조
ws=wb['4대보험']; comp_diff=[]
for row in ws.iter_rows(min_row=2,values_only=True):
    if row[0] and row[0]!='합계' and sum(row[1:5])!=row[5]: comp_diff.append({'name':row[0],'components_sum':sum(row[1:5]),'회사부담합계':row[5],'diff':row[5]-sum(row[1:5])})
payroll={'net_pay_rows':len(pd),'net_pay_row_sum':psum,'net_pay_total_row':ptot,'row_sum_equals_total_row':psum==ptot,
 'insurance_rows':len(idat),'insurance_row_sum':isum,'insurance_total_row':itot,'insurance_row_sum_equals_total_row':isum==itot,
 'insurance_component_vs_total_column_diffs':comp_diff,'note':'합계 행은 데이터 합산에서 제외하고 행별 합을 합계 행과 대조했다. 출금 대응에는 회사부담합계 열을 쓴다.'}
v2={}
for v in vendors:
    for n in v['bank_names']: v2[n]=v['id']
vname={v['id']:v['name'] for v in vendors}
sep_pur=sorted([p for p in pur if p['date'].startswith('2026-09')],key=lambda p:(p['date'],p['id']))
pused=set(); kused=set(); matched=[]; unmatched=[]
for r in sorted(wd,key=lambda r:(r['date'],r['line'])):
    rec={'line':r['line'],'date':r['date'],'counterparty':r['counterparty'],'amount':r['amount'],'memo':r['memo']}
    vid=v2.get(r['counterparty'])
    pc=[p for p in sep_pur if p['id'] not in pused and p['vendor_id']==vid and p['amount']==r['amount']] if vid else []
    kc=[k for k in contracts if k['id'] not in kused and k['supplier']==r['counterparty'] and k['sept_effective_fee']==r['amount']]
    if r['amount']==ptot and psum==ptot and '급여' in (r['counterparty']+r['memo']) :
        rec.update(category='급여',ref='급여 순지급 합계')
    elif r['amount']==itot and isum==itot and '4대보험' in (r['counterparty']+r['memo']):
        rec.update(category='4대보험',ref='4대보험 회사부담 합계')
    elif kc:
        k=kc[0]; kused.add(k['id']); rec.update(category='고정비',ref=k['id'])
        if pc: rec['ambiguity']=f"같은 공급처·금액의 9월 매입 {pc[0]['id']}도 있음 — 계약으로 대응"
    elif pc:
        p=pc[0]; pused.add(p['id']); rec.update(category='매입',ref=p['id'],purchase_date=p['date'])
    else:
        why=[]
        if vid: why.append('공급처는 있으나 같은 금액의 미대응 9월 매입 없음')
        ks=[k for k in contracts if k['supplier']==r['counterparty']]
        if ks: why.append(f"계약 {ks[0]['id']} 9월 실효 요금 {ks[0]['sept_effective_fee']}와 다름")
        if not vid and not ks: why.append('공급처·계약·급여·4대보험 어디에도 없음')
        rec['reason']='; '.join(why); unmatched.append(rec); continue
    matched.append(rec)
wd_total=sum(r['amount'] for r in wd)
m_total=sum(r['amount'] for r in matched); u_total=sum(r['amount'] for r in unmatched)
assert m_total+u_total==wd_total
unpaid_pur=[p for p in sep_pur if p['id'] not in pused]
cat_tot=collections.Counter()
for r in matched: cat_tot[r['category']]+=r['amount']
# ---------- 3. 잔고 검증
chain=[]; prev=summ['opening_balance']
for r in rows:
    exp=prev+(r['amount'] if r['type']=='입금' else -r['amount'])
    if exp!=r['balance']: chain.append({'line':r['line'],'expected':exp,'csv_balance':r['balance'],'diff':r['balance']-exp})
    prev=r['balance']
calc_close=summ['opening_balance']+dep_total-wd_total; csv_close=rows[-1]['balance']
def chk(name,a,b,la,lb):
    ok=a==b; return {'check':name,la:a,lb:b,'diff':a-b,'ok':ok,'status':'일치' if ok else '원천 확인 필요'}
checks=[chk('요약 기초잔고+CSV 입금합−CSV 출금합 vs CSV 마지막 잔고',calc_close,csv_close,'computed','csv_last_balance'),
 chk('CSV 기말잔고 vs 요약 기말잔고',csv_close,summ['closing_balance'],'csv_last_balance','summary_closing_balance'),
 chk('CSV 입금 건수 vs 요약 입금 건수',len(dep),summ['deposit_count'],'csv_deposit_count','summary_deposit_count'),
 chk('(참고) CSV 출금 건수 vs 요약',len(wd),summ['withdrawal_count'],'csv','summary'),
 chk('(참고) CSV 입금 합 vs 요약',dep_total,summ['deposit_total'],'csv','summary'),
 chk('(참고) CSV 출금 합 vs 요약',wd_total,summ['withdrawal_total'],'csv','summary')]
recon={'as_of':'2026-09-30','interpretations':[
 '청구서 원장(invoices.json) 전부를 9/1 현재 미결로 본다(8월 이전 입금 자료 없음).',
 '같은 날짜 입금은 CSV 행 순서로 처리했다.',
 '정확일치 후보가 여럿이면 만기·id 순 첫 청구를 결제했다. 오래된 순 = 만기·id 순.',
 '은행 표시명은 bank_names와 글자 그대로 같을 때만 대응했다(정규화 없음).',
 '입금 메모의 INV 번호는 규칙상 쓰지 않았다. 배분 결과와 다른 경우는 memo_ref_differences에 남겼다.',
 '선입금은 이후 청구에 자동 상계하지 않고 거래처별 선입금으로 남겼다. 미수 잔액은 총액 기준이며 선입금은 별도 표시.',
 '출금 대응 순서: 급여(합계 일치) → 4대보험(합계 일치) → 고정비(계약 공급자+9월 실효요금) → 9월 매입(공급처 표시명+금액, 1:1, 매입일·id 순). 매입일과 출금일의 선후는 따지지 않았다.',
 '계약서 요금은 부가세 별도로 적혀 있으나 대응은 계약서 월 요금(부가세 제외) 그대로 비교했다.'],
 'deposits':{'count':len(dep),'total':dep_total,'applied_to_invoices':applied_total,'prepayment_total':prepay_total,'unidentified_total':unknown_total,
   'check_applied+prepay+unidentified=total':applied_total+prepay_total+unknown_total==dep_total,
   'by_method':dict(collections.Counter(r.get('method',r.get('status')) for r in alloc_log)),
   'multiple_exact_candidates':[{'line':x['line'],'date':x['date'],'counterparty':x['counterparty'],'amount':x['amount'],'candidates':x['exact_candidates'],'chosen':x['exact_candidates'][0],'rule':'만기·id 순 첫 청구 선택'} for x in alloc_log if len(x.get('exact_candidates',[]))>1],
   'log':alloc_log,'prepayments':prepay,'unidentified':unknown,'memo_ref_differences':memo_diff},
 'receivables':{'total_open':ar_total,'open_invoice_count':len(openinv),'aging':buckets,'check_bucket_sum=total':sum(buckets.values())==ar_total,
   'total_prepayment_credit':prepay_total,'top5_clients':top5,'open_invoices':openinv,
   'by_client':[{'client_id':k,'client':cname[k],**v,'prepayment_credit':prep_by.get(k,0)} for k,v in sorted(bycl.items(),key=lambda kv:(-kv[1]['balance'],kv[0]))]},
 'payroll_check':payroll,
 'withdrawals':{'count':len(wd),'total':wd_total,'matched_total':m_total,'unmatched_total':u_total,'check_matched+unmatched=total':m_total+u_total==wd_total,
   'matched_by_category':dict(cat_tot),'matched':matched,'unmatched':unmatched,
   'september_purchases':{'count':len(sep_pur),'total':sum(p['amount'] for p in sep_pur),'unpaid_in_september':unpaid_pur,'unpaid_total':sum(p['amount'] for p in unpaid_pur)}},
 'bank_checks':{'opening_balance_used':summ['opening_balance'],'csv_deposit_total':dep_total,'csv_withdrawal_total':wd_total,'checks':checks,
   'running_balance_breaks':chain,'any_mismatch':any(not c['ok'] for c in checks) or bool(chain)}}
json.dump(recon,open(f'{OUT}/reconciliation.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
# ---------- 4. 계약
cout=[]
for k in contracts:
    exp=D(k['expiry']); days=(exp-ASOF).days
    nd=(exp-dt.timedelta(days=k['notice_days'])) if k['notice_applies_to']=='갱신 거절' else None
    actual=[r for r in wd if r['counterparty']==k['supplier'] and k['service_kw'] in r['memo']]
    act=sum(r['amount'] for r in actual)
    cout.append({**{x:k[x] for x in ['id','supplier','service','base_monthly_fee','start','term_months','auto_renew','notice_days','notice_applies_to','expiry','fee_clause','sept_effective_fee','fee_calc']},
     'days_to_expiry':days,'expires_within_30_days':0<=days<=30,
     'notice_deadline':nd.isoformat() if nd else None,'notice_deadline_passed':(nd<ASOF) if nd else None,
     'notice_note':k.get('notice_note'),
     'september_withdrawals':[{'line':r['line'],'date':r['date'],'amount':r['amount'],'memo':r['memo']} for r in actual],
     'september_withdrawal_total':act,'fee_vs_withdrawal_diff':act-k['sept_effective_fee'],'fee_matches_withdrawal':act==k['sept_effective_fee']})
json.dump({'as_of':'2026-09-30','contracts':cout,
  'flags':{'expires_within_30_days':[c['id'] for c in cout if c['expires_within_30_days']],
           'notice_deadline_passed':[c['id'] for c in cout if c['notice_deadline_passed']],
           'fee_differs_from_withdrawal':[c['id'] for c in cout if not c['fee_matches_withdrawal']]},
  'interpretations':['통보 기한일 = 만료일 − 통보 일수(갱신 거절 통보). 기준일 이전이면 경과.','실제 출금은 계약 공급자 표시명이면서 메모에 서비스명이 든 9월 출금이다.','만료 30일 안 = 0 ≤ 만료일−2026-09-30 ≤ 30일.']},
  open(f'{OUT}/contracts.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
# ---------- 3b. 전망
months=['2026-10','2026-11','2026-12']
inflow={m:0 for m in months}; inflow_detail={m:[] for m in months}; beyond=[]
for o in openinv:
    m='2026-10' if o['due']<='2026-09-30' else o['due'][:7]
    if m in inflow: inflow[m]+=o['balance']; inflow_detail[m].append(o['invoice'])
    else: beyond.append(o)
def active(c,m):
    first=D(m+'-01'); 
    if c['auto_renew']: return D(c['start'])<=first
    return D(c['start'])<=first<D(c['expiry'])
pur_sep=sum(p['amount'] for p in sep_pur)
start=csv_close; fc=[]; cur=start
for m in months:
    act=[c for c in cout if active(c,m)]
    cfee=sum(c['sept_effective_fee'] for c in act)
    out_=cfee+ptot+itot+pur_sep
    beg=cur; cur=beg+inflow[m]-out_
    fc.append({'month':m,'opening':beg,'inflow_receivables':inflow[m],'inflow_invoices':inflow_detail[m],
      'outflow':{'contracts':cfee,'contracts_active':[c['id'] for c in act],'payroll_net':ptot,'insurance_employer':itot,'purchases_(=9월 매입 총액)':pur_sep,'total':out_},
      'closing':cur,'min_cash_balance':tgt['min_cash_balance'],'breaks_min_balance':cur<tgt['min_cash_balance']})
json.dump({'as_of':'2026-09-30','starting_balance':start,
 'starting_balance_basis':'CSV 마지막 잔고(2026-09-30 행). 은행 요약 기말잔고 '+str(summ['closing_balance'])+('와 일치' if csv_close==summ['closing_balance'] else '와 불일치 — 원천 확인 필요'),
 'rules':['유입 = 미결 청구 잔액을 만기 달에, 9/30 이전 만기(연체)는 10월','유출 = 그 달 활성 계약 월 요금(9월 실효 요금) + 급여 순지급 합계 + 4대보험 회사부담 합계 + 9월 매입 총액','선입금·미확인 입금은 전망에 넣지 않음','연체 청구가 10월에 전액 회수된다는 가정은 규칙에 따른 것이며 회수 보장은 아님'],
 'contract_activity_assumption':'자동갱신 계약은 해지 통보 확인이 없으므로 갱신되어 계속 활성으로 봤다(K02는 10-11까지 통보 가능). K03은 2027-01-01 만료라 12월까지 활성.',
 'months':fc,'months_breaking_min':[f['month'] for f in fc if f['breaks_min_balance']],
 'receivables_due_after_2026_12':[{'invoice':o['invoice'],'due':o['due'],'balance':o['balance']} for o in beyond],
 'check_inflow_sum+beyond=open_ar':sum(inflow.values())+sum(o['balance'] for o in beyond)==ar_total},
 open(f'{OUT}/forecast.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
sep_rev=sum(i['amount'] for i in inv if i['issued'].startswith('2026-09'))
json.dump({'sep_revenue':sep_rev,'sep_invoices':sum(1 for i in inv if i['issued'].startswith('2026-09')),'sep_purchases':pur_sep,'gm':(sep_rev-pur_sep)/sep_rev,'targets':tgt,
 'c07_deposits':[r for r in alloc_log if r.get('client_id')=='C07'],'c07_open':[o for o in openinv if o['client_id']=='C07']},open(f'{OUT}/../kpi_work.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('ok')
