"""
재무 기록 도구 핸들러 — [self:finance] (health-record 대칭)
소비(지출·수입 거래) + 소유(자산·부채 스냅샷), 다중 주체(owner — 개인/회사).
"""
import os
import sys
import json
import re
import shutil
from datetime import datetime

_package_dir = os.path.dirname(os.path.abspath(__file__))
if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)

import finance_storage as storage   # ★패키지 서브모듈은 고유 이름 (sys.modules 충돌 방지)
import finance_sync                 # 결제 알림 수거기 (구 spending 패키지 흡수, 2026-08-14)


# 통화 규율: returns:items 액션 — 맨 문자열 반환 금지 (health 선례).
def _err(msg: str) -> str:
    return json.dumps({"success": False, "error": msg}, ensure_ascii=False)


def _ok(msg: str, items: list = None) -> str:
    out = {"success": True, "message": msg}
    if items is not None:
        out["items"] = items
    return json.dumps(out, ensure_ascii=False)


# ── 공용 정규화 지도 (함수 안 중복 정의 금지 — health 선례) ──
_KO_TX_MAP = {'지출': 'expense', '소비': 'expense', 'expense': 'expense',
              '수입': 'income', '소득': 'income', 'income': 'income'}
_KO_HOLD_MAP = {'자산': 'asset', '소유': 'asset', 'asset': 'asset',
                '부채': 'liability', '빚': 'liability', '대출': 'liability', 'liability': 'liability'}
_VALID_QUERY_TYPES = {'summary', 'transactions', 'holdings', 'search', 'owners'}
_KO_QUERY_TYPE_MAP = {
    '요약': 'summary', '전체': 'summary',
    '거래': 'transactions', '지출': 'transactions', '소비': 'transactions',
    '수입': 'transactions', '내역': 'transactions',
    '자산': 'holdings', '소유': 'holdings', '부채': 'holdings', '보유': 'holdings',
    '검색': 'search',
    '주체': 'owners', '주체목록': 'owners', '목록': 'owners',
}
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')
_HOLD_KIND_KO = {'asset': '자산', 'liability': '부채'}
_TX_KO = {'expense': '지출', 'income': '수입'}


def _won(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v or '')
    if n == int(n):
        return f"{int(n):,}원"
    return f"{n:,.0f}원"


def _to_number(v):
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip().replace(',', '').replace('원', '').replace('₩', '')
        # "3200만원"/"1.2억" 같은 한국식 단위
        m = re.match(r'^([\d.]+)\s*(억|만|천만)?$', s)
        if m:
            try:
                n = float(m.group(1))
            except ValueError:
                return v
            mult = {'억': 100_000_000, '천만': 10_000_000, '만': 10_000}.get(m.group(2), 1)
            n *= mult
            return int(n) if float(n).is_integer() else n
    return v


def execute(tool_input: dict, context) -> str:
    tool_name = context.tool_name
    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.get("op") or "").strip()
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            return _err(f"알 수 없는 op '{op}'. (save|query|delete|ingest)")
        return fn(tool_input)
    return _err(f"알 수 없는 도구: {tool_name}")


# ═══════════ save ═══════════

def save_finance_info(input_data: dict) -> str:
    """평탄형 저장 — kind(지출/수입/자산/부채) + 필드. 거래=amount 필수, 소유=name 필수."""
    kind_raw = str(input_data.get('kind') or input_data.get('info_type') or '').strip()
    owner = input_data.get('owner') or input_data.get('person')
    note = input_data.get('note')
    date = str(input_data.get('date') or input_data.get('occurred_at') or '').strip()
    date = date if _DATE_RE.match(date) else None

    tx_type = _KO_TX_MAP.get(kind_raw)
    hold_kind = _KO_HOLD_MAP.get(kind_raw)

    # kind 누락 시 추론: amount 있으면 지출, name+value 있으면 자산
    if not tx_type and not hold_kind:
        if input_data.get('amount') is not None:
            tx_type = 'expense'
        elif input_data.get('name'):
            hold_kind = 'asset'
        else:
            return _err("저장 실패: kind 를 지정하세요 (지출|수입|자산|부채). "
                        '예: {op: save, kind: "지출", amount: 12000, category: "식비", counterparty: "김밥천국"}')

    try:
        if tx_type:
            amount = _to_number(input_data.get('amount'))
            if not isinstance(amount, (int, float)) or amount <= 0:
                return _err("저장 실패: amount(금액, 원)가 비어 있거나 숫자가 아닙니다.")
            rid = storage.save_transaction(
                tx_type=tx_type, amount=float(amount),
                category=input_data.get('category'),
                counterparty=input_data.get('counterparty') or input_data.get('merchant'),
                occurred_at=date, note=note, owner=owner)
            who = f"[{owner}] " if owner and owner != "나" else ""
            desc = " ".join(x for x in [input_data.get('category') or '',
                                        input_data.get('counterparty') or input_data.get('merchant') or ''] if x)
            return _ok(f"✓ {who}{_TX_KO[tx_type]} 기록 저장됨 (#{rid}): {_won(amount)}"
                       + (f" — {desc}" if desc else ""))
        else:
            name = str(input_data.get('name') or '').strip()
            if not name:
                return _err("저장 실패: name(자산/부채 이름)을 지정하세요. "
                            '예: {op: save, kind: "자산", name: "신한은행 예금", value: 32000000}')
            value = _to_number(input_data.get('value') if input_data.get('value') is not None
                               else input_data.get('amount'))
            if value is not None and not isinstance(value, (int, float)):
                return _err(f"저장 실패: value '{value}' 를 숫자로 읽지 못했습니다.")
            rid = storage.save_holding(
                kind=hold_kind, name=name,
                value=float(value) if value is not None else None,
                asset_type=input_data.get('asset_type') or input_data.get('category'),
                as_of=date, note=note, owner=owner)
            who = f"[{owner}] " if owner and owner != "나" else ""
            return _ok(f"✓ {who}{_HOLD_KIND_KO[hold_kind]} 기록 저장됨 (#{rid}): {name}"
                       + (f" {_won(value)}" if value is not None else ""))
    except Exception as e:
        return _err(f"저장 실패: {str(e)}")


# ═══════════ sync (구 [self:spend]{op:"sync"} 흡수) ═══════════

def sync_finance_from_phone(input_data: dict) -> str:
    """폰(USB) 결제 앱 알림 수거 → 재무 원장 거래로 병합 (ext_id dedup — 재수거 안전)."""
    owner = input_data.get('owner') or input_data.get('person')
    try:
        rows, skipped_non_payment, source = finance_sync.collect_from_phone()
    except RuntimeError as e:
        return _err(str(e))
    new_rows = storage.merge_synced_rows(rows, owner=owner)
    unparsed = sum(1 for r in new_rows if not r.get('parsed'))
    charges = sum(1 for r in rows if r.get('type') == 'charge')
    msg = f"결제 알림 {len(rows)}건 확인, 새 내역 {len(new_rows)}건 수거"
    if unparsed:
        msg += f" (미분류 {unparsed}건 — 원문 보존됨)"
    if charges:
        msg += f" (충전 {charges}건은 이체라 원장 제외)"
    if not rows:
        msg = "폰에 결제 알림이 없습니다."
    elif new_rows and source == "capture":
        msg += " — 포획소에 남아 있으니 폰 알림은 지우셔도 됩니다."
    elif new_rows:
        msg += " — 수거된 알림은 이제 지우셔도 됩니다."
    # ★출처를 숨기지 않는다: dumpsys 경로는 활성 알림만 보므로 72시간 지난 결제를
    # 원리적으로 못 가져온다. 그 상태로 "없습니다"만 말하면 유실을 침묵으로 덮는 셈.
    if source == "dumpsys":
        msg += (" ⚠️ 폰 포획소가 꺼져 있어 화면에 살아 있는 알림만 봤습니다"
                " — 설정 > 알림 > 알림 접근에서 IndieBiz 를 켜면 72시간 만료분도 남습니다.")
    collected = [{
        "title": f"{'↩️ ' if r.get('type') == 'cancel' else ''}{r.get('merchant') or r.get('title') or '(미분류)'}"
                 f" · {_won(r.get('amount')) if r.get('amount') else '금액 미상'}",
        "meta": f"{r.get('source')} · "
                + datetime.fromtimestamp((r.get('ts') or 0) / 1000).strftime('%m/%d %H:%M'),
        "summary": (r.get('body') or r.get('title') or '')[:120],
        "url": "",
    } for r in new_rows[:20]]
    return json.dumps({"success": True, "message": msg, "fetched": len(rows),
                       "new": len(new_rows), "unparsed": unparsed,
                       "items": collected}, ensure_ascii=False)


# ═══════════ query ═══════════

def _tx_to_table(txs: list):
    if not txs:
        return None
    columns = ["날짜", "구분", "분류", "거래처", "금액(원)"]
    rows = [[t.get('occurred_at') or '', _TX_KO.get(t['tx_type'], t['tx_type']),
             t.get('category') or '', t.get('counterparty') or '',
             t['amount'] if float(t['amount']) != int(t['amount']) else int(t['amount'])]
            for t in txs]
    return {"columns": columns, "rows": rows}


def _tx_points(txs: list):
    """일자별 지출 합계 → sparkline points (시간 오름차순)."""
    by_date = {}
    for t in txs:
        if t['tx_type'] == 'expense' and t.get('occurred_at'):
            by_date[t['occurred_at']] = by_date.get(t['occurred_at'], 0) + t['amount']
    return [{"date": d, "value": int(v)} for d, v in sorted(by_date.items())]


def _tx_items(txs: list):
    return [{
        "title": f"{t.get('counterparty') or t.get('category') or _TX_KO.get(t['tx_type'], '')} · {_won(t['amount'])}",
        "meta": f"{_TX_KO.get(t['tx_type'], '')} · {t.get('occurred_at') or ''}"
                + (f" · {t.get('category')}" if t.get('category') and t.get('counterparty') else ""),
        "summary": t.get('note') or '',
        "url": "",
    } for t in txs]


def _hold_items(holds: list):
    return [{
        "title": h['name'],
        "meta": f"{_HOLD_KIND_KO.get(h['kind'], h['kind'])}"
                + (f" · {h.get('asset_type')}" if h.get('asset_type') else "")
                + f" · {h.get('as_of') or ''}",
        "summary": _won(h['value']) if h.get('value') is not None else '',
        "url": "",
    } for h in holds]


def _summary_to_blocks(s: dict) -> list:
    blocks = []

    def _section(title, items):
        if items:
            blocks.append({"type": "heading", "level": 3, "text": title})
            blocks.append({"type": "list", "items": items})

    _section(f"💸 {s['month']} 거래", [
        f"지출 {_won(s['expense'])} · 수입 {_won(s['income'])} · 순액 {_won(s['net'])} ({s['tx_count']}건)"])
    _section("📊 지출 상위 분류", [f"{c}: {_won(v)}" for c, v in s['top_categories']])
    _section("🏦 소유 (이름별 최신)", [
        f"{h['name']}: {_won(h['value']) if h.get('value') is not None else '평가액 미기록'}"
        f" ({_HOLD_KIND_KO.get(h['kind'], '')})" for h in s['holdings'][:12]])
    if s['holdings']:
        _section("∑ 순자산", [
            f"자산 {_won(s['asset_total'])} − 부채 {_won(s['liability_total'])} = {_won(s['net_worth'])}"])
    return blocks


def get_finance_context(input_data: dict) -> str:
    query_type = str(input_data.get('query_type') or input_data.get('category') or 'summary').strip()
    owner = input_data.get('owner') or input_data.get('person')
    keyword = input_data.get('keyword')
    month = input_data.get('month')
    days = input_data.get('days')
    who = f"[{owner}] " if owner and owner != "나" else ""

    tx_filter = None
    if query_type in ('지출', '소비'):
        tx_filter = 'expense'
    elif query_type in ('수입', '소득'):
        tx_filter = 'income'
    # '자산' 조회=소유 전체(자산+부채 — 순자산이 정직하려면 부채가 보여야 한다), '부채'만 필터.
    hold_filter = 'liability' if query_type == '부채' else None

    if query_type not in _VALID_QUERY_TYPES:
        mapped = _KO_QUERY_TYPE_MAP.get(query_type)
        if mapped:
            query_type = mapped
        else:
            keyword = keyword or query_type
            query_type = 'search'

    try:
        if query_type == 'owners':
            owners = storage.list_owners()
            if not owners:
                return _ok("등록된 주체가 없습니다.", items=[])
            lines = ["👥 재무 주체 목록:", ""] + [
                f"  • {o['name']}" + (f" - {o['note']}" if o.get('note') else "") for o in owners]
            records = [{"title": o['name'], "meta": "", "summary": o.get('note') or "", "url": ""}
                       for o in owners]
            return json.dumps({"text": "\n".join(lines), "items": records}, ensure_ascii=False)

        elif query_type == 'summary':
            s = storage.get_summary(owner=owner, month=month)
            lines = [f"💰 {who}재무 요약 ({s['month']})", "",
                     f"  지출 {_won(s['expense'])} · 수입 {_won(s['income'])} · 순액 {_won(s['net'])} ({s['tx_count']}건)"]
            if s['top_categories']:
                lines.append("  지출 상위: " + ", ".join(f"{c} {_won(v)}" for c, v in s['top_categories'][:3]))
            if s['holdings']:
                lines.append(f"  순자산: 자산 {_won(s['asset_total'])} − 부채 {_won(s['liability_total'])} = {_won(s['net_worth'])}")
            if s['tx_count'] == 0 and not s['holdings']:
                lines = [f"{who}기록된 재무 정보가 없습니다."]
            top = [{"merchant": m['merchant'], "count": m['count'],
                    "amount_label": _won(m['amount'])} for m in s.get('top_merchants', [])]
            return json.dumps({"text": "\n".join(lines), "blocks": _summary_to_blocks(s),
                               "expense_label": _won(s['expense']), "income_label": _won(s['income']),
                               "net_label": _won(s['net']),
                               "asset_label": _won(s['asset_total']),
                               "liability_label": _won(s['liability_total']),
                               "networth_label": _won(s['net_worth']),
                               "hana_label": _won(s.get('by_source', {}).get('하나카드', 0)),
                               "cjpay_label": _won(s.get('by_source', {}).get('청주페이', 0)),
                               "last_sync": s.get('last_sync', ''),
                               "items": top,
                               "month": s['month']}, ensure_ascii=False)

        elif query_type == 'transactions':
            txs = storage.get_transactions(owner=owner, month=month,
                                           days=int(days) if days else (None if month else 31),
                                           tx_type=tx_filter or input_data.get('tx_type'),
                                           keyword=keyword,
                                           source=finance_sync.norm_source(str(input_data.get('source') or '')) or None,
                                           limit=int(input_data.get('limit') or 200))
            last_sync = storage.last_sync_label()
            sync_prompt = [{"hint": "폰을 USB 로 연결한 뒤 누르세요. 수거 후엔 폰 알림을 지워도 됩니다."}]
            if not txs:
                empty = _ok(f"{who}거래 기록이 없습니다. 카드 결제는 폰을 USB 로 연결하고 수거하세요.", items=[])
                e = json.loads(empty)
                e.update({"last_sync": last_sync, "total_label": "0원", "count": 0,
                          "sync_prompt": sync_prompt})
                return json.dumps(e, ensure_ascii=False)
            label = _TX_KO.get(tx_filter, '거래')
            total = sum(t['amount'] for t in txs if t['tx_type'] == 'expense') if tx_filter != 'income' \
                else sum(t['amount'] for t in txs)
            lines = [f"💸 {who}{label} 기록 ({len(txs)}건)", ""] + [
                f"  (#{t['id']}) {t.get('occurred_at')}: {_TX_KO.get(t['tx_type'])} {_won(t['amount'])}"
                + (f" {t.get('counterparty') or t.get('category') or ''}")
                for t in txs[:20]]
            table = _tx_to_table(txs)
            payload = {"text": "\n".join(lines), "count": len(txs), "items": _tx_items(txs),
                       "total": total, "total_label": _won(total),
                       "last_sync": last_sync, "sync_prompt": sync_prompt}
            if table:
                payload["table"] = table
                payload["blocks"] = [{"type": "table", "columns": table["columns"], "rows": table["rows"]}]
                payload["points"] = _tx_points(txs)
            return json.dumps(payload, ensure_ascii=False)

        elif query_type == 'holdings':
            holds = storage.get_holdings(owner=owner, kind=hold_filter)
            if not holds:
                return _ok(f"{who}소유(자산·부채) 기록이 없습니다.", items=[])
            asset_total = sum(h['value'] or 0 for h in holds if h['kind'] == 'asset')
            liab_total = sum(h['value'] or 0 for h in holds if h['kind'] == 'liability')
            lines = [f"🏦 {who}소유 현황 ({len(holds)}건, 이름별 최신)", ""] + [
                f"  (#{h['id']}) {h['name']}: {_won(h['value']) if h.get('value') is not None else '-'}"
                f" ({_HOLD_KIND_KO.get(h['kind'])}, {h.get('as_of')})" for h in holds]
            lines.append(f"  ∑ 자산 {_won(asset_total)} − 부채 {_won(liab_total)} = {_won(asset_total - liab_total)}")
            return json.dumps({"text": "\n".join(lines), "items": _hold_items(holds),
                               "asset_label": _won(asset_total), "liability_label": _won(liab_total),
                               "networth_label": _won(asset_total - liab_total),
                               "count": len(holds)}, ensure_ascii=False)

        elif query_type == 'search':
            if not keyword:
                return _err("검색 키워드를 입력해주세요.")
            res = storage.search_records(keyword, owner=owner)
            items = _tx_items(res['transactions']) + _hold_items(res['holdings'])
            total = len(items)
            if not total:
                return _ok(f"{who}'{keyword}' 검색 결과가 없습니다.", items=[])
            text = f"🔍 {who}'{keyword}' 검색 결과 ({total}건)"
            return json.dumps({"text": text, "items": items}, ensure_ascii=False)

        else:
            return _err(f"알 수 없는 조회 유형: {query_type}")
    except Exception as e:
        return _err(f"조회 실패: {str(e)}")


# ═══════════ delete ═══════════

def delete_finance_record(input_data: dict) -> str:
    _RT = {'transaction': 'transaction', '거래': 'transaction', '지출': 'transaction',
           '수입': 'transaction', 'transactions': 'transaction',
           'holding': 'holding', '자산': 'holding', '부채': 'holding',
           '소유': 'holding', 'holdings': 'holding'}
    record_type = _RT.get(str(input_data.get('record_type') or input_data.get('kind') or '').strip())
    raw_id = input_data.get('record_id', input_data.get('id'))
    owner = input_data.get('owner') or input_data.get('person')
    if not record_type:
        return _err("삭제 실패: record_type 을 지정하세요 (transaction|holding). "
                    "예: {op: delete, record_type: transaction, record_id: 5}")
    if raw_id in (None, ''):
        return _err("삭제 실패: record_id(조회 출력의 #번호)를 지정하세요.")
    try:
        record_id = int(raw_id)
    except (TypeError, ValueError):
        return _err(f"삭제 실패: record_id '{raw_id}' 가 정수가 아닙니다.")
    try:
        ok = storage.soft_delete_record(record_type, record_id, owner=owner)
    except Exception as e:
        return _err(f"삭제 실패: {str(e)}")
    if not ok:
        return _err(f"삭제할 기록을 찾지 못했습니다: {record_type} #{record_id}")
    ko = {'transaction': '거래', 'holding': '소유'}[record_type]
    return _ok(f"🗑 {ko} 기록 #{record_id} 삭제됨")


# ═══════════ ingest (공용 엔진 둘째 소비자) ═══════════

def ingest_finance_info(input_data: dict) -> str:
    """다형 입력(텍스트/이미지·영수증/PDF/엑셀 가계부)을 AI로 구조화해 일괄 저장."""
    file_path = (input_data.get('file') or input_data.get('path') or '').strip()
    free_text = (input_data.get('text') or input_data.get('content') or '').strip()
    owner = input_data.get('owner') or input_data.get('person')

    try:
        import ingest_engine
    except ImportError as e:
        return _err(f"ingest_engine 임포트 불가(백엔드 밖 실행?): {e}")

    source = ingest_engine.extract_source(path=file_path or None, text=free_text or None)
    if not source.get('ok'):
        return _err(source.get('error') or '원문 추출 실패')

    today = datetime.now().strftime('%Y-%m-%d')
    schema = (
        f"오늘 날짜: {today} (상대 날짜는 이것 기준 환산)\n"
        "출력 스키마 — 배열의 각 원소는 다음 중 하나:\n"
        '- 거래: {"kind":"expense|income","amount":금액(원,숫자),"category":"식비/교통 등 분류",'
        '"counterparty":"가맹점/거래처","date":"YYYY-MM-DD","note":"짧은 메모"}\n'
        '- 소유: {"kind":"asset|liability","name":"자산/부채 이름(은행·계좌·부동산 등)",'
        '"value":평가액(원,숫자),"asset_type":"cash|account|securities|realestate|vehicle|loan|other",'
        '"date":"평가 기준일"}\n'
        "영수증이면 합계 금액 1건의 expense 로(품목은 note 에 요약). "
        "가계부 표면 행마다 거래 1건씩. 금액은 원 단위 숫자만(콤마·통화기호 제거)."
    )
    records, err = ingest_engine.extract_records(source, schema, domain_label="재무기록")
    if err:
        return _err(f"추출 실패: {err}")
    if not records:
        return _ok(f"{source.get('label', '입력')}: 저장할 재무 기록을 찾지 못했습니다.", items=[])

    saved_items, skipped = [], []
    for r in records:
        kind_raw = str(r.get('kind') or '').strip().lower()
        tx_type = _KO_TX_MAP.get(kind_raw)
        hold_kind = _KO_HOLD_MAP.get(kind_raw)
        date = str(r.get('date') or '').strip()
        date = date if _DATE_RE.match(date) else None
        if tx_type:
            amount = _to_number(r.get('amount'))
            if not isinstance(amount, (int, float)) or amount <= 0:
                skipped.append(f"{_TX_KO[tx_type]}: 금액 없음 — 지어내지 않고 건너뜀")
                continue
            rid = storage.save_transaction(tx_type=tx_type, amount=float(amount),
                                           category=r.get('category'),
                                           counterparty=r.get('counterparty'),
                                           occurred_at=date, note=r.get('note'), owner=owner)
            saved_items.append({"title": f"{r.get('counterparty') or r.get('category') or _TX_KO[tx_type]} · {_won(amount)}",
                                "meta": f"{_TX_KO[tx_type]} · {date or today} (#{rid})",
                                "summary": r.get('note') or '', "url": ""})
        elif hold_kind:
            name = str(r.get('name') or '').strip()
            value = _to_number(r.get('value'))
            if not name:
                skipped.append(f"{_HOLD_KIND_KO[hold_kind]}: 이름 없음 — 건너뜀")
                continue
            if value is not None and not isinstance(value, (int, float)):
                value = None
            rid = storage.save_holding(kind=hold_kind, name=name,
                                       value=float(value) if value is not None else None,
                                       asset_type=r.get('asset_type'), as_of=date, owner=owner)
            saved_items.append({"title": name,
                                "meta": f"{_HOLD_KIND_KO[hold_kind]} · {date or today} (#{rid})",
                                "summary": _won(value) if value is not None else '', "url": ""})
        else:
            skipped.append(f"kind 불명: {str(r)[:80]}")

    # 원본 보존 — 영수증 사진/PDF 는 files/ 에 사본
    if file_path and (source.get('kind') == 'image' or file_path.lower().endswith('.pdf')) and saved_items:
        try:
            os.makedirs(storage.FILES_DIR, exist_ok=True)
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy2(file_path, os.path.join(
                storage.FILES_DIR, f"{stamp}_{os.path.basename(file_path)}"))
        except OSError:
            pass  # 원본 보존 실패는 적재를 되돌릴 일이 아님

    head = f"✓ {source.get('label', '입력')}에서 {len(saved_items)}건 저장"
    if skipped:
        head += f", {len(skipped)}건 건너뜀"
    lines = [head] + [f"  • {it['title']}" for it in saved_items]
    if skipped:
        lines += ["  건너뜀:"] + [f"  ⚠ {s}" for s in skipped[:5]]
    return json.dumps({"success": True, "message": head, "text": "\n".join(lines),
                       "items": saved_items, "saved": len(saved_items),
                       "skipped": len(skipped)}, ensure_ascii=False)


# --check 가 이 dict 키로 src.ops.values 와 정확 비교 (_OP_DISPATCHERS 표준 패턴).
_OP_DISPATCHERS = {
    "finance_op": {"save": save_finance_info, "query": get_finance_context,
                   "delete": delete_finance_record, "ingest": ingest_finance_info,
                   "sync": sync_finance_from_phone},
}
