"""40회차 합성 자료·변형·독립 oracle. IBL 과제 계산은 하지 않는다(oracle 은 대조용, AI 입력 사본에서 제외).

사용: prepare.py generate  — source/ 에 자료 생성, trainer/·agent/ 사본(base·A 절단·C CRLF+NFD 변형 폴더)
      prepare.py oracle    — oracle/expected.json (기본·변형 A·변형 B 기대값)
규칙(과제문과 동일):
  입금 매칭 — 입금을 날짜순으로 처리. 표시명→거래처(clients.json bank_names). 그 거래처의 미결 청구(발행일 ≤ 입금일, 만기·id 순) 중
  잔액이 입금액과 정확히 같은 것이 있으면 그것을 결제, 없으면 가장 오래된 미결 청구부터 차례로 충당, 남는 금액은 선입금. 거래처 미확인 입금은 unmatched.
  aging(2026-09-30 기준 잔액) — 기한내 / 1-30 / 31-60 / 61-90 / 90+
  출금 매칭 — 매입(공급처 표시명+금액 정확), 급여(순지급 합계)·4대보험(합계), 계약(공급자 표시명+월 요금), 나머지 = unexplained
  전망 — 10·11·12월: 유입 = 미결 잔액을 만기 달에(연체는 10월), 유출 = 활성 계약 월 요금 + 급여 순지급 + 4대보험 + 9월 매입 총액. 잔고 < 최소 잔고인 달 표시
"""
import csv
import json
import random
import shutil
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_40회차'
ASOF = date(2026, 9, 30)

CLIENTS = [  # id, 정식명, 은행 표시명(변형 포함), 결제조건(일)
    ("C01", "한빛상사", ["한빛상사"], 30), ("C02", "(주)대성유통", ["(주)대성유통", "대성유통"], 30),
    ("C03", "한빛 주식회사", ["한빛 주식회사", "(주)한빛"], 45), ("C04", "그린마켓", ["그린마켓"], 30),
    ("C05", "미래식품", ["미래식품", "미래식품(주)"], 30), ("C06", "서울포장재", ["서울포장재"], 60),
    ("C07", "동해수산", ["동해수산"], 30), ("C08", "누리커머스", ["누리커머스", "㈜누리커머스"], 30),
    ("C09", "제일물산", ["제일물산"], 30), ("C10", "청담베이커리", ["청담베이커리"], 15),
    ("C11", "라온농산", ["라온농산"], 30), ("C12", "바른유통", ["바른유통", "바른 유통"], 30),
    ("C13", "경기제과", ["경기제과"], 30), ("C14", "오션푸드", ["오션푸드"], 45),
    ("C15", "별빛마트", ["별빛마트"], 30), ("C16", "태양상회", ["태양상회"], 30),
    ("C17", "소담식자재", ["소담식자재", "소담 식자재"], 30), ("C18", "하나로푸드", ["하나로푸드"], 30),
    ("C19", "참좋은마트", ["참좋은마트"], 30), ("C20", "우리수산", ["우리수산"], 30),
    ("C21", "새벽유통", ["새벽유통"], 30),   # 청구 없음 — 선입금 함정
]
VENDORS = [("V01", "코리아펄프"), ("V02", "동양잉크"), ("V03", "세진기계"), ("V04", "한솔물류"), ("V05", "에코필름"),
           ("V06", "대한전력"), ("V07", "삼일사무"), ("V08", "모던포장기"), ("V09", "청정화학"), ("V10", "우성운송")]
CONTRACTS = [  # id, 공급자, 서비스, 월 요금, 시작, 기간(월), 자동갱신, 통보일, 9월 실제 청구, 각주
    ("K01", "클라우드원", "ERP 구독", 480000, date(2025, 10, 15), 12, True, 30, 480000, None),
    ("K02", "세이프가드", "보안 관제", 350000, date(2025, 10, 25), 12, True, 14, 350000, None),
    ("K03", "한솔물류", "창고 보관", 1200000, date(2026, 1, 1), 12, False, 30, 1200000, None),
    ("K04", "오피스렌탈", "복합기 임대", 160000, date(2025, 4, 1), 24, True, 60, 190000, None),             # 단가 불일치(조항 없음)
    ("K05", "넷라인", "전용회선", 220000, date(2025, 10, 20), 12, True, 30, 231000, "2026년 9월 1일부터 월 요금을 5% 인상한다."),  # 각주 인상 → 불일치 아님
]
PAYROLL = [("김민수", 4200000), ("이서연", 3900000), ("박지훈", 3600000), ("최수아", 3400000), ("정우진", 3300000), ("강하은", 3100000),
           ("조현우", 3000000), ("윤서준", 2900000), ("장예린", 2800000), ("임도윤", 2800000), ("한지우", 2700000), ("오시우", 2600000)]


def renewal_date(start, months):
    y, m = start.year, start.month + months
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, start.day)


def gen_invoices(rng):
    inv, n = [], 1
    for month in (7, 8, 9):
        for _ in range(40):
            cid, name, _, terms = rng.choice(CLIENTS[:20])
            issued = date(2026, month, rng.randint(1, 28))
            amount = rng.randint(3, 30) * 100000
            inv.append({"id": f"INV-{n:04d}", "client_id": cid, "client": name, "issued": issued.isoformat(),
                        "due": (issued + timedelta(days=terms)).isoformat(), "amount": amount})
            n += 1
    inv.sort(key=lambda r: (r["issued"], r["id"]))
    return inv


def gen_purchases(rng):
    rows = []
    for month in (7, 8, 9):
        for i in range(30):
            vid, vname = rng.choice(VENDORS)
            d = date(2026, month, rng.randint(1, 28))
            rows.append({"id": f"PO-{month:02d}{i + 1:02d}", "vendor_id": vid, "vendor": vname, "date": d.isoformat(), "amount": rng.randint(2, 20) * 100000})
    # 같은 금액·다른 공급처 2쌍(9월)
    rows[-1]["amount"] = rows[-2]["amount"] = 2300000; rows[-1]["vendor_id"], rows[-1]["vendor"] = "V02", "동양잉크"; rows[-2]["vendor_id"], rows[-2]["vendor"] = "V05", "에코필름"
    rows[-3]["amount"] = rows[-4]["amount"] = 1700000; rows[-3]["vendor_id"], rows[-3]["vendor"] = "V07", "삼일사무"; rows[-4]["vendor_id"], rows[-4]["vendor"] = "V09", "청정화학"
    return rows


def generate():
    rng = random.Random(40)
    if OUT.exists():
        shutil.rmtree(OUT)
    src = OUT / 'source'; src.mkdir(parents=True)
    (OUT / 'oracle').mkdir()
    invoices = gen_invoices(rng)
    purchases = gen_purchases(rng)
    clients = [{"id": c, "name": n, "bank_names": b, "payment_terms_days": t} for c, n, b, t in CLIENTS]
    vendors = [{"id": v, "name": n, "bank_names": [n]} for v, n in VENDORS]
    # ---- 은행 거래(9월) ----
    tx = []
    opening = 48_500_000
    # 입금: 7·8월 청구 대부분 + 9월 청구 일부. 함정: 부분 입금 4, 분할 입금 2(=한 청구를 두 번에), 초과(선입금) 1, 미확인 1
    paid_plan = {}
    for r in invoices:
        m = int(r["issued"][5:7])
        p = {7: 0.9, 8: 0.75, 9: 0.35}[m]
        if rng.random() < p:
            paid_plan[r["id"]] = "full"
    ids = list(paid_plan)
    for k in ids[:4]:
        paid_plan[k] = "partial"
    for k in ids[4:6]:
        paid_plan[k] = "split"
    paid_plan[ids[6]] = "over"
    by_client = {c["id"]: c for c in clients}
    for r in invoices:
        kind = paid_plan.get(r["id"])
        if not kind:
            continue
        c = by_client[r["client_id"]]
        disp = rng.choice(c["bank_names"])
        d = date(2026, 9, rng.randint(1, 29))
        if kind == "full":
            tx.append((d, "입금", r["amount"], disp, f"{r['id']} 대금"))
        elif kind == "partial":
            tx.append((d, "입금", r["amount"] // 2, disp, "대금 일부"))
        elif kind == "split":
            a = r["amount"] * 3 // 10
            tx.append((d, "입금", a, disp, "대금 1차")); tx.append((min(d + timedelta(days=3), date(2026, 9, 30)), "입금", r["amount"] - a, disp, "대금 2차"))
        elif kind == "over":
            tx.append((d, "입금", r["amount"] + 500000, disp, "대금(선입금 포함)"))
    tx.append((date(2026, 9, 12), "입금", 1_250_000, "알수없음무역", "송금"))  # 미확인 입금
    tx.append((date(2026, 9, 28), "입금", 1_000_000, "새벽유통", "선입금"))      # 청구 없는 거래처 → 선입금
    # 출금: 9월 매입 전부(지급) + 급여 + 4대보험 + 계약 5 + 미설명 3
    for r in purchases:
        if r["date"].startswith("2026-09"):
            tx.append((date.fromisoformat(r["date"]) + timedelta(days=rng.randint(0, 2)), "출금", r["amount"], r["vendor"], "매입대금"))
    net_total = sum(a for _, a in PAYROLL); ins_total = int(sum(a for _, a in PAYROLL) * 0.093)
    tx.append((date(2026, 9, 25), "출금", net_total, "급여이체", "9월 급여"))
    tx.append((date(2026, 9, 10), "출금", ins_total, "국민건강보험공단외", "4대보험"))
    for k in CONTRACTS:
        tx.append((date(2026, 9, 5), "출금", k[8], k[1], f"{k[2]} 9월"))
    tx.append((date(2026, 9, 8), "출금", 870000, "미래카드", "카드대금"))
    tx.append((date(2026, 9, 17), "출금", 450000, "현금인출", "ATM"))
    tx.append((date(2026, 9, 29), "출금", 2_100_000, "스마트리스", "리스료"))
    tx = [t for t in tx if t[0] <= date(2026, 9, 30)]
    tx.sort(key=lambda t: (t[0], t[1] != "입금", t[2]))
    bal = opening
    with open(src / 'bank_2026-09.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(["date", "type", "amount", "counterparty", "memo", "balance"])
        for d, ty, a, cp, memo in tx:
            bal += a if ty == "입금" else -a
            w.writerow([d.isoformat(), ty, a, cp, memo, bal])
    (src / 'bank_summary.json').write_text(json.dumps({"month": "2026-09", "opening_balance": opening, "closing_balance": bal,
                                                        "deposit_count": sum(1 for t in tx if t[1] == "입금"), "withdrawal_count": sum(1 for t in tx if t[1] == "출금"),
                                                        "deposit_total": sum(t[2] for t in tx if t[1] == "입금"), "withdrawal_total": sum(t[2] for t in tx if t[1] == "출금")}, ensure_ascii=False, indent=1))
    (src / 'invoices.json').write_text(json.dumps(invoices, ensure_ascii=False, indent=1))
    (src / 'purchases.json').write_text(json.dumps(purchases, ensure_ascii=False, indent=1))
    (src / 'clients.json').write_text(json.dumps(clients, ensure_ascii=False, indent=1))
    (src / 'vendors.json').write_text(json.dumps(vendors, ensure_ascii=False, indent=1))
    # ---- 급여 XLSX ----
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "급여"
    ws.append(["이름", "직급", "기본급", "수당", "공제", "순지급"])
    for i, (n, base) in enumerate(PAYROLL):
        ws.append([n, "사원" if i > 2 else "대리", base, 200000, int(base * 0.08) + 200000, base - int(base * 0.08)])
    ws.append(["합계", "", sum(b for _, b in PAYROLL), 200000 * 12, sum(int(b * 0.08) + 200000 for _, b in PAYROLL), sum(b - int(b * 0.08) for _, b in PAYROLL)])
    ws2 = wb.create_sheet("4대보험")
    ws2.append(["이름", "국민연금", "건강보험", "고용보험", "산재보험", "회사부담합계"])
    for n, base in PAYROLL:
        ws2.append([n, int(base * 0.045), int(base * 0.035), int(base * 0.009), int(base * 0.004), int(base * 0.093)])
    ws2.append(["합계", "", "", "", "", sum(int(b * 0.093) for _, b in PAYROLL)])
    wb.save(src / 'payroll_2026-09.xlsx')
    # 급여 순지급 합계 = 은행 출금과 같아야 함: 은행에는 net_total(기본급 합)을 썼으므로 보정
    net_sheet = sum(b - int(b * 0.08) for _, b in PAYROLL)
    rows = list(csv.reader(open(src / 'bank_2026-09.csv', encoding='utf-8')))
    for r in rows[1:]:
        if r[4] == "9월 급여":
            r[2] = str(net_sheet)
    bal = opening
    for r in rows[1:]:
        bal += int(r[2]) if r[1] == "입금" else -int(r[2]); r[5] = str(bal)
    with open(src / 'bank_2026-09.csv', 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(rows)
    summ = json.loads((src / 'bank_summary.json').read_text()); summ["closing_balance"] = bal
    summ["withdrawal_total"] = sum(int(r[2]) for r in rows[1:] if r[1] == "출금"); (src / 'bank_summary.json').write_text(json.dumps(summ, ensure_ascii=False, indent=1))
    # ---- 계약서 ----
    (src / 'contracts').mkdir()
    for cid, sup, svc, fee, start, months, auto, notice, _, foot in CONTRACTS:
        rd = renewal_date(start, months)
        text = f"""# {svc} 서비스 계약서 ({cid})

**공급자**: {sup}
**수요자**: 한빛포장 주식회사

## 제1조 (목적)
본 계약은 공급자가 수요자에게 {svc} 서비스를 제공하고 수요자는 그 대가를 지급하는 조건을 정한다.

## 제2조 (요금)
월 이용 요금은 **{fee:,}원**(부가세 별도)으로 하며, 매월 5일에 자동 이체한다.{(' [1]' if foot else '')}

## 제3조 (계약 기간)
계약 기간은 {start.isoformat()}부터 {months}개월로 하며, 기간 만료일은 {rd.isoformat()}이다.
{'기간 만료 ' + str(notice) + '일 전까지 서면 해지 통보가 없으면 동일 조건으로 ' + str(months) + '개월 자동 갱신된다.' if auto else '기간 만료 시 계약은 종료되며, 연장은 별도 합의로 한다. 중도 해지는 ' + str(notice) + '일 전 통보로 한다.'}

## 제4조 (의무)
공급자는 서비스 수준을 유지하고 수요자는 요금을 기한 내 지급한다.

## 제5조 (기타)
본 계약에 정하지 않은 사항은 상법과 관례에 따른다.
{('[1] ' + foot) if foot else ''}
"""
        (src / 'contracts' / f'{cid}_{sup}.md').write_text(text, encoding='utf-8')
    (src / 'targets.json').write_text(json.dumps({"month": "2026-09", "revenue_target": 70_000_000, "gross_margin_target": 0.45, "min_cash_balance": 30_000_000}, ensure_ascii=False, indent=1))
    (src / 'memo_2026-08.md').write_text("""# 2026년 8월 경영 메모

## 결정 사항
1. 동해수산(C07) 미수금 독촉 — 9월 15일까지 입금이 없으면 거래 중단을 검토한다.
2. 복합기 임대 계약(K04, 오피스렌탈) 해지 검토 — 9월 말까지 대안 견적을 받는다.

## 리스크
- 8월 매출 목표 미달(목표 7,000만 원).
""", encoding='utf-8')
    # ---- 사본·변형 ----
    for who in ("trainer", "agent"):
        shutil.copytree(src, OUT / who / 'base')
        a = OUT / who / 'variantA'; shutil.copytree(src, a)
        rows = list(csv.reader(open(a / 'bank_2026-09.csv', encoding='utf-8')))
        with open(a / 'bank_2026-09.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([rows[0]] + [r for r in rows[1:] if r[0] <= "2026-09-23"])
        c = OUT / who / 'variantC'; shutil.copytree(src, c)
        k2 = next(c.glob('contracts/K02_*.md'))
        k2.write_bytes(unicodedata.normalize('NFD', k2.read_text(encoding='utf-8')).replace('\n', '\r\n').encode('utf-8'))
        for o in ('out', 'outA', 'outB', 'outC'):
            (OUT / who / o).mkdir(parents=True, exist_ok=True)
    print("generated: invoices", len(invoices), "purchases", len(purchases), "bank rows", len(tx), "closing", bal)


# ---------- oracle ----------
def load(folder):
    rows = list(csv.DictReader(open(folder / 'bank_2026-09.csv', encoding='utf-8')))
    for r in rows:
        r["amount"] = int(r["amount"]); r["balance"] = int(r["balance"])
    return {"bank": rows, "invoices": json.loads((folder / 'invoices.json').read_text()), "purchases": json.loads((folder / 'purchases.json').read_text()),
            "clients": json.loads((folder / 'clients.json').read_text()), "vendors": json.loads((folder / 'vendors.json').read_text()),
            "summary": json.loads((folder / 'bank_summary.json').read_text()), "targets": json.loads((folder / 'targets.json').read_text())}


def reconcile(d, asof=ASOF):
    name2client = {bn: c["id"] for c in d["clients"] for bn in c["bank_names"]}
    balance = {r["id"]: r["amount"] for r in d["invoices"]}
    inv_by_client = {}
    for r in d["invoices"]:
        inv_by_client.setdefault(r["client_id"], []).append(r)
    matches, unmatched, advances = [], [], {}
    for t in sorted((t for t in d["bank"] if t["type"] == "입금"), key=lambda t: (t["date"], t["amount"])):
        cid = name2client.get(t["counterparty"])
        if not cid:
            unmatched.append({"date": t["date"], "amount": t["amount"], "counterparty": t["counterparty"]}); continue
        opens = sorted([r for r in inv_by_client.get(cid, []) if balance[r["id"]] > 0 and r["issued"] <= t["date"]], key=lambda r: (r["due"], r["id"]))
        remaining = t["amount"]
        exact = [r for r in opens if balance[r["id"]] == remaining]
        if exact:
            balance[exact[0]["id"]] = 0; matches.append({"deposit_date": t["date"], "invoice": exact[0]["id"], "applied": remaining}); remaining = 0
        else:
            for r in opens:
                if remaining <= 0:
                    break
                ap = min(remaining, balance[r["id"]]); balance[r["id"]] -= ap; remaining -= ap
                matches.append({"deposit_date": t["date"], "invoice": r["id"], "applied": ap})
        if remaining > 0:
            advances[cid] = advances.get(cid, 0) + remaining
    buckets = {"기한내": 0, "1-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    per_client = {}
    open_rows = []
    for r in d["invoices"]:
        b = balance[r["id"]]
        if b <= 0:
            continue
        days = (asof - date.fromisoformat(r["due"])).days
        k = "기한내" if days <= 0 else "1-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        buckets[k] += b; per_client[r["client_id"]] = per_client.get(r["client_id"], 0) + b
        open_rows.append({"invoice": r["id"], "client_id": r["client_id"], "due": r["due"], "balance": b, "bucket": k})
    top = sorted(per_client.items(), key=lambda x: (-x[1], x[0]))[:5]
    return {"aging": buckets, "open_total": sum(buckets.values()), "top_clients": [{"client_id": c, "balance": b} for c, b in top],
            "unmatched_deposits": unmatched, "advances": advances, "open_invoices": sorted(open_rows, key=lambda r: r["invoice"]), "applied_count": len(matches)}


def outflows(d, payroll_net, insurance, contract_fees):
    name2vendor = {bn: v["id"] for v in d["vendors"] for bn in v["bank_names"]}
    pur_open = {}
    for p in d["purchases"]:
        if p["date"].startswith("2026-09"):
            pur_open.setdefault((p["vendor_id"], p["amount"]), []).append(p["id"])
    explained, unexplained = [], []
    for t in [t for t in d["bank"] if t["type"] == "출금"]:
        vid = name2vendor.get(t["counterparty"])
        key = (vid, t["amount"])
        if vid and pur_open.get(key):
            explained.append({"date": t["date"], "amount": t["amount"], "kind": "purchase", "ref": pur_open[key].pop(0)}); continue
        if t["amount"] == payroll_net and "급여" in t["memo"]:
            explained.append({"date": t["date"], "amount": t["amount"], "kind": "payroll", "ref": "급여"}); continue
        if t["amount"] == insurance:
            explained.append({"date": t["date"], "amount": t["amount"], "kind": "insurance", "ref": "4대보험"}); continue
        if t["counterparty"] in contract_fees:
            explained.append({"date": t["date"], "amount": t["amount"], "kind": "contract", "ref": t["counterparty"], "contract_fee": contract_fees[t["counterparty"]], "mismatch": t["amount"] != contract_fees[t["counterparty"]]}); continue
        unexplained.append({"date": t["date"], "amount": t["amount"], "counterparty": t["counterparty"], "memo": t["memo"]})
    return explained, unexplained


def oracle():
    src = OUT / 'source'
    payroll_net = sum(b - int(b * 0.08) for _, b in PAYROLL); insurance = sum(int(b * 0.093) for _, b in PAYROLL)
    contracts = []
    for cid, sup, svc, fee, start, months, auto, notice, billed, foot in CONTRACTS:
        rd = renewal_date(start, months); effective = int(fee * 1.05) if foot else fee
        deadline = rd - timedelta(days=notice)
        contracts.append({"id": cid, "supplier": sup, "service": svc, "monthly_fee": fee, "effective_fee_sep": effective, "start": start.isoformat(), "term_months": months,
                          "auto_renew": auto, "notice_days": notice, "renewal_date": rd.isoformat(), "notice_deadline": deadline.isoformat(),
                          "action_within_30d": (rd - ASOF).days <= 30, "notice_deadline_passed": deadline < ASOF, "billed_sep": billed, "fee_mismatch": billed != effective, "fee_change_note": foot})
    fees = {c["supplier"]: c["effective_fee_sep"] for c in contracts}
    result = {}
    for variant, folder in (("base", src), ("A", OUT / 'trainer' / 'variantA')):
        d = load(folder)
        rec = reconcile(d)
        explained, unexplained = outflows(d, payroll_net, insurance, fees)
        dep = sum(t["amount"] for t in d["bank"] if t["type"] == "입금"); wd = sum(t["amount"] for t in d["bank"] if t["type"] == "출금")
        csv_closing = d["bank"][-1]["balance"]
        balance_check = {"opening": d["summary"]["opening_balance"], "csv_closing": csv_closing, "summary_closing": d["summary"]["closing_balance"],
                         "csv_deposit_count": sum(1 for t in d["bank"] if t["type"] == "입금"), "summary_deposit_count": d["summary"]["deposit_count"],
                         "internal_ok": d["summary"]["opening_balance"] + dep - wd == csv_closing, "matches_summary": csv_closing == d["summary"]["closing_balance"] and sum(1 for t in d["bank"] if t["type"] == "입금") == d["summary"]["deposit_count"]}
        sep_rev = sum(r["amount"] for r in d["invoices"] if r["issued"].startswith("2026-09")); sep_pur = sum(p["amount"] for p in d["purchases"] if p["date"].startswith("2026-09"))
        perf = {"revenue": sep_rev, "revenue_target": d["targets"]["revenue_target"], "revenue_hit": sep_rev >= d["targets"]["revenue_target"], "purchases": sep_pur,
                "gross_margin": round((sep_rev - sep_pur) / sep_rev, 4), "gross_margin_target": d["targets"]["gross_margin_target"]}
        def forecast(min_cash, drop_contract_from=None):
            inflow = {"2026-10": 0, "2026-11": 0, "2026-12": 0}
            for r in rec["open_invoices"]:
                m = r["due"][:7]
                m = "2026-10" if m <= "2026-10" else m
                if m in inflow:
                    inflow[m] += r["balance"]
            months, bal, rows = ["2026-10", "2026-11", "2026-12"], csv_closing, []
            for m in months:
                cf = sum(c["effective_fee_sep"] for c in contracts if not (drop_contract_from and c["id"] == drop_contract_from[0] and m >= drop_contract_from[1]))
                out = cf + payroll_net + insurance + sep_pur
                bal = bal + inflow[m] - out
                rows.append({"month": m, "inflow": inflow[m], "outflow": out, "closing": bal, "below_min": bal < min_cash})
            return rows
        result[variant] = {"reconciliation": rec, "explained_count": len(explained), "unexplained": unexplained, "balance_check": balance_check, "performance": perf,
                           "payroll_net": payroll_net, "insurance": insurance, "forecast": forecast(d["targets"]["min_cash_balance"]), "contracts": contracts,
                           "source_complete": variant == "base"}
    result["B"] = {"forecast": None}
    d = load(src)
    # 변형 B: 최소 잔고 6천만, K05 를 11월부터 해지
    base_fc = result["base"]
    rec = base_fc["reconciliation"]
    def fc_B():
        inflow = {"2026-10": 0, "2026-11": 0, "2026-12": 0}
        for r in rec["open_invoices"]:
            m = r["due"][:7]; m = "2026-10" if m <= "2026-10" else m
            if m in inflow:
                inflow[m] += r["balance"]
        bal, rows = base_fc["balance_check"]["csv_closing"], []
        for m in ["2026-10", "2026-11", "2026-12"]:
            cf = sum(c["effective_fee_sep"] for c in contracts if not (c["id"] == "K05" and m >= "2026-11"))
            out = cf + payroll_net + insurance + base_fc["performance"]["purchases"]
            bal = bal + inflow[m] - out
            rows.append({"month": m, "inflow": inflow[m], "outflow": out, "closing": bal, "below_min": bal < 60_000_000})
        return rows
    result["B"] = {"forecast": fc_B(), "min_cash": 60_000_000, "dropped": "K05 from 2026-11"}
    (OUT / 'oracle' / 'expected.json').write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    b = result["base"]
    print(json.dumps({"aging": b["reconciliation"]["aging"], "open_total": b["reconciliation"]["open_total"], "top": b["reconciliation"]["top_clients"][:3],
                      "unmatched": len(b["reconciliation"]["unmatched_deposits"]), "advances": b["reconciliation"]["advances"], "unexplained": len(b["unexplained"]),
                      "balance": b["balance_check"], "perf": b["performance"], "forecast": b["forecast"],
                      "contracts_flags": [(c["id"], c["action_within_30d"], c["notice_deadline_passed"], c["fee_mismatch"]) for c in b["contracts"]],
                      "A_balance": result["A"]["balance_check"]["matches_summary"], "B_forecast": result["B"]["forecast"]}, ensure_ascii=False, default=str)[:3000])


if __name__ == '__main__':
    {"generate": generate, "oracle": oracle}[sys.argv[1]]()
