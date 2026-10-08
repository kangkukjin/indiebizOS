
import json,sys
A=sys.argv[1]; O=A+'/out'
r=json.load(open(O+'/reconciliation.json',encoding='utf-8')); f=json.load(open(O+'/forecast.json',encoding='utf-8'))
c=json.load(open(O+'/contracts.json',encoding='utf-8')); k=json.load(open(A+'/kpi_work.json',encoding='utf-8'))
w=lambda n:f'{n:,}원'
t=k['targets']; rev=k['sep_revenue']; pur=k['sep_purchases']; gm=k['gm']
d=r['deposits']; rc=r['receivables']; wd=r['withdrawals']; ag=rc['aging']
overdue=sum(v for b,v in ag.items() if b!='기한내')
L=[]; a=L.append
a('# 한빛포장 2026년 9월 월말 경영 메모'); a(''); a('기준일 2026-09-30. 모든 수치는 out 폴더의 reconciliation.json·forecast.json·contracts.json에서 계산한 값이다.'); a('')
a('## 1. 목표 대비 실적'); a('')
a('| 항목 | 목표 | 실적 | 차이 |'); a('|---|---|---|---|')
a(f"| 9월 매출(9월 발행 청구 {k['sep_invoices']}건 합) | {w(t['revenue_target'])} | {w(rev)} | {w(rev-t['revenue_target'])} (달성률 {rev/t['revenue_target']*100:.1f}%) |")
a(f"| 매출총이익률 ((매출−9월 매입 {w(pur)})/매출) | {t['gross_margin_target']*100:.1f}% | {gm*100:.2f}% | {(gm-t['gross_margin_target'])*100:+.2f}%p |")
a(''); a('두 목표 모두 미달이다. 8월 메모의 "매출 목표 미달" 리스크가 9월에도 이어졌다.'); a('')
a('## 2. 미수금과 상위 거래처'); a('')
a(f"- 9월 입금 {d['count']}건, {w(d['total'])}: 청구 결제 {w(d['applied_to_invoices'])} + 선입금 {w(d['prepayment_total'])} + 미확인 입금 {w(d['unidentified_total'])} (합계 일치). 처리 방식은 정확일치 {d['by_method'].get('정확일치',0)}건, 오래된 순 충당 {d['by_method'].get('오래된순 충당',0)}건이다.")
for u in d['unidentified']: a(f"- 미확인 입금: {u['date']} '{u['counterparty']}' {w(u['amount'])} (메모 '{u['memo']}'). 거래처 원장에 없는 이름이다.")
for p in d['prepayments']: a(f"- 선입금: {p['client']}({p['client_id']}) {w(p['amount'])}, {p['date']}. 미결 청구가 없어 이후 청구 상계용으로 둔다.")
a(f"- 9/30 미수 잔액: {w(rc['total_open'])} ({rc['open_invoice_count']}건). 연체액은 {w(overdue)}이다."); a('')
a('| 기한내 | 1-30일 | 31-60일 | 61-90일 | 90일+ | 합계 |'); a('|---|---|---|---|---|---|')
a('| '+' | '.join(w(ag[b]) for b in ['기한내','1-30','31-60','61-90','90+'])+f" | {w(sum(ag.values()))} |"); a('')
a('상위 미수 거래처 5곳(잔액 순):'); a('')
a('| 순위 | 거래처 | 잔액 | 건수 | 연체 |'); a('|---|---|---|---|---|')
for x in rc['top5_clients']: a(f"| {x['rank']} | {x['client']}({x['client_id']}) | {w(x['balance'])} | {x['count']} | {w(x['overdue'])} |")
lo=[o for o in rc['open_invoices'] if o['bucket'] in ('31-60','61-90','90+')]
a(''); a('31일 이상 연체 청구: '+', '.join(f"{o['client']} {o['invoice']} {w(o['balance'])}({o['days_past_due']}일)" for o in lo)+'.')
a(f"- 하나로푸드(C18)는 9월 입금이 0건이며 {w([x for x in rc['top5_clients'] if x['client_id']=='C18'][0]['balance'])}이 남아 있다.")
a(f"- 입금 메모의 INV 번호와 규칙상 배분이 다른 입금이 {len(d['memo_ref_differences'])}건 있다(reconciliation.json memo_ref_differences). 규칙대로 금액 기준으로 배분했다."); a('')
a('## 3. 설명 안 되는 출금'); a('')
a(f"9월 출금 {wd['count']}건 {w(wd['total'])} 가운데 {w(wd['matched_total'])}을 대응했다(매입 {w(wd['matched_by_category']['매입'])}, 급여 {w(wd['matched_by_category']['급여'])}, 4대보험 {w(wd['matched_by_category']['4대보험'])}, 고정비 {w(wd['matched_by_category']['고정비'])}). 대응되지 않은 출금은 {len(wd['unmatched'])}건 {w(wd['unmatched_total'])}이다."); a('')
a('| 날짜 | 상대 | 금액 | 메모 | 사유 |'); a('|---|---|---|---|---|')
for u in wd['unmatched']: a(f"| {u['date']} | {u['counterparty']} | {w(u['amount'])} | {u['memo']} | {u['reason']} |")
pc=r['payroll_check']
a(''); a(f"급여 순지급 행별 합 {w(pc['net_pay_row_sum'])}과 4대보험 회사부담 행별 합 {w(pc['insurance_row_sum'])}은 각 시트의 합계 행과 같다. 둘 다 출금액과 일치한다. 다만 4대보험 시트의 {len(pc['insurance_component_vs_total_column_diffs'])}명은 항목(국민연금·건강·고용·산재) 합이 회사부담합계보다 1원 작다(고용보험 단수). 9월 매입 {wd['september_purchases']['count']}건(미대응 매입 {len(wd['september_purchases']['unpaid_in_september'])}건)은 공급처명·금액으로 모두 출금과 대응됐다."); a('')
a('## 4. 현금 전망 (10~12월)'); a('')
a(f"출발 잔고 {w(f['starting_balance'])}: {f['starting_balance_basis']}. 은행 잔고 검증 3항목(기초+입금−출금=CSV 마지막 잔고, CSV 기말잔고=요약, 입금 건수=요약)은 "+('모두 일치했다.' if not r['bank_checks']['any_mismatch'] else '불일치가 있어 원천 확인이 필요하다.')); a('')
a('| 월 | 기초 | 유입(미결 청구) | 유출 | 월말 잔고 | 최소 잔고 '+w(t['min_cash_balance'])+' |'); a('|---|---|---|---|---|---|')
for m in f['months']: a(f"| {m['month']} | {w(m['opening'])} | {w(m['inflow_receivables'])} | {w(m['outflow']['total'])} | {w(m['closing'])} | {'**깨짐**' if m['breaks_min_balance'] else '유지'} |")
o=f['months'][0]['outflow']
a(''); a(f"월 유출은 계약 {w(o['contracts'])} + 급여 {w(o['payroll_net'])} + 4대보험 {w(o['insurance_employer'])} + 매입 {w(o['purchases_(=9월 매입 총액)'])}이다. 유입은 연체분을 10월에 몰아 넣은 현재 미결 청구뿐이다. 10월 이후 새로 발행할 청구는 규칙상 넣지 않았다. 그래서 "+', '.join(f['months_breaking_min'])+'이 최소 잔고를 깬다. 이 결과는 새 매출이 없다는 가정의 하한 시나리오다.'); a('')
a('## 5. 계약 조치'); a('')
a('| 계약 | 공급자 | 9월 실효 요금 | 만료일(남은 일) | 통보 기한 | 9월 출금 | 표시 |'); a('|---|---|---|---|---|---|---|')
for x in c['contracts']:
    fl=[]
    if x['expires_within_30_days']: fl.append('만료 30일 내')
    if x['notice_deadline_passed']: fl.append('통보 기한 경과')
    if not x['fee_matches_withdrawal']: fl.append(f"출금 차이 {w(x['fee_vs_withdrawal_diff'])}")
    a(f"| {x['id']} {x['service']} | {x['supplier']} | {w(x['sept_effective_fee'])} | {x['expiry']} ({x['days_to_expiry']}일) | {x['notice_deadline'] or '해당 없음(자동갱신 없음)'} | {w(x['september_withdrawal_total'])} | {', '.join(fl) or '-'} |")
a('')
a('- K01 클라우드원·K05 넷라인은 통보 기한(09-15, 09-20)이 지나 12개월 자동 갱신이 확정적이다. K05는 각주 [1]에 따라 9/1부터 5% 인상된 231,000원이 적용되고 있다.')
a('- K02 세이프가드는 2026-10-11까지 해지 통보를 할 수 있다. 계속 이용할지 지금 결정해야 한다.')
a(f"- K04 오피스렌탈은 계약 요금 {w(c['contracts'][3]['sept_effective_fee'])}인데 {w(c['contracts'][3]['september_withdrawal_total'])}이 출금됐다(차이 {w(c['contracts'][3]['fee_vs_withdrawal_diff'])}). 계약서에 인상 조항이 없으므로 차액 근거를 요구한다."); a('')
a('## 6. 지난달 결정 2건의 상태'); a('')
c07=k['c07_deposits']
before=[x for x in c07 if x['date']<='2026-09-15']; after=[x for x in c07 if x['date']>'2026-09-15']
a(f"1. **동해수산(C07) 미수 독촉**: 9/15까지 {len(before)}건 {w(sum(x['amount'] for x in before))}이 입금돼 INV-0040·INV-0023을 결제했다. 따라서 '9/15까지 입금 없음' 조건은 성립하지 않았다. 가장 오래된 INV-0003(만기 08-04, 2,700,000원)은 9/15까지 미결로 남았다. 이후 {', '.join(x['date'][5:]+' '+w(sum(al['applied'] for al in x['allocations'] if al['invoice']=='INV-0003')) for x in after if any(al['invoice']=='INV-0003' for al in x['allocations']))}으로 완납됐다. 9/30 현재 동해수산의 연체는 {w(sum(x['balance'] for x in k['c07_open'] if x['bucket']!='기한내'))}이다. 남은 잔액은 기한내 {w(sum(x['balance'] for x in k['c07_open']))}(INV-0115·INV-0082)이다. 거래 중단 검토의 근거는 해소된 상태로 판단한다. 다만 독촉의 실행 여부는 자료로 확인할 수 없다.")
a(f"2. **K04 복합기 임대 해지 검토(9월 말까지 대안 견적)**: 대안 견적을 받았는지는 자료에 없어 **미확인**이다. 계약상 갱신 거절 통보 기한은 {c['contracts'][3]['notice_deadline']}로 아직 남아 있다. 만료 전 중도 해지 조건은 계약서에 없다. 9월에는 계약보다 30,000원 많은 190,000원이 출금됐다."); a('')
a('## 7. 리스크 상위 3과 추천 조치'); a('')
m2=f['months'][1]; m3=f['months'][2]
a(f"1. **현금 고갈**: 새 매출 없이 현재 비용이 이어지면 11월 말 잔고가 {w(m2['closing'])}으로 최소 잔고 {w(t['min_cash_balance'])}을 깨고, 12월 말에는 {w(m3['closing'])}이 된다. 월 유출은 {w(o['total'])}이다. → 10~11월 청구 발행 계획과 회수 일정을 주 단위로 점검하고, 매입 발주 시점을 조정한다. 필요하면 11월 이전에 운전자금 한도를 확보한다.")
a(f"2. **매출·마진 동반 미달**: 매출 달성률 {rev/t['revenue_target']*100:.1f}%, 매출총이익률 {gm*100:.2f}%로 목표 대비 {(gm-t['gross_margin_target'])*100:+.2f}%p다. 9월 매입 {w(pur)}이 매출의 {pur/rev*100:.1f}%다. → 매입 단가와 거래처별 판매 단가를 점검한다. 9월 매입 중 10월 이후 매출을 위한 재고분이 있는지 확인한다.")
a(f"3. **설명 안 되는 출금과 미수 연체**: 대응되지 않은 출금 {w(wd['unmatched_total'])}(스마트리스 리스료, 미래카드, 현금인출, 계약 요금과 다른 오피스렌탈 190,000원)이 있고, 연체 미수는 {w(overdue)}이다. → 스마트리스 계약서가 고정비 계약 목록에 없으니 확보한다. 카드·현금 사용 증빙을 받는다. 연체 상위(라온농산·오션푸드·하나로푸드) 독촉을 시작한다."); a('')
a('## 8. 미확인 항목과 질문'); a('')
a(f"- 미확인 입금 '알수없음무역' {w(d['unidentified_total'])}의 송금 주체와 성격은? 어느 거래처의 대금인가?")
a('- 스마트리스 2,100,000원 리스료: 어떤 계약인가? 고정비 계약서 5건에 없다. 매월 나가는 돈이라면 전망 유출이 더 커진다(현재 전망에는 미포함).')
a('- 미래카드 870,000원·현금인출 450,000원의 사용처 증빙은 있는가?')
a('- 오피스렌탈 190,000원 출금의 근거는? 부가세나 별도 요금이면 계약서 요금(부가세 별도 160,000원)과 어떻게 맞는가?')
a('- 계약서 요금은 모두 "부가세 별도"인데 실제 출금은 K04를 빼고 부가세 없는 금액과 같다. 부가세를 별도로 내고 있는가?')
a('- K04 대안 견적을 받았는가?(8월 결정 2)')
a(f"- 정확일치 후보가 둘 이상인 입금 {len(d['multiple_exact_candidates'])}건은 규칙에 따라 만기·id 순 첫 청구에 배분했다. 입금 메모의 INV 번호와 다른 배분 {len(d['memo_ref_differences'])}건도 있다. 거래처가 지정한 청구로 바꿔야 하는가?")
a('- 청구서 원장 전체를 9/1 현재 미결로 봤다(8월 이전 입금 자료 없음). 7~8월에 이미 받은 청구가 있으면 미수가 줄어든다.')
a('- 새벽유통 선입금 1,000,000원: 어느 주문분인가? 이후 청구와 상계할지 정해야 한다.')
a('- 전망은 10~12월 신규 매출을 넣지 않은 규칙 기반 계산이다. 신규 청구 계획이 있으면 반영해 다시 계산해야 한다.')
open(O+'/memo.md','w',encoding='utf-8').write('\n'.join(L)+'\n'); print('memo ok')
