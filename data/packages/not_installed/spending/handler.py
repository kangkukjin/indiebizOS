"""spending/handler.py — 지출내역 ([self:spend]).

결제 앱(하나카드·청주페이)의 승인 푸시 알림을, 폰을 USB 로 연결했을 때
`adb dumpsys notification` 으로 수거해 지출 원장(data/spending.db)에 쌓는다.

원리(사용자 운용 규약): 폰에서 결제 알림을 **지우지 않고 모아두면**, 활성 알림에는
제목·본문 텍스트가 그대로 남아 dumpsys 로 읽힌다. 지운 알림은 텍스트가 사라지므로
(아카이브엔 메타데이터만 남음) 수거(sync) 후에 지우는 것이 안전한 순서다.
상시 리스너·폰 앱 개조 없음 — 맥 쪽 코드만으로 완결(2026-08-12 사용자 설계).

한계(정직 신고): 폰 재부팅·수거 전 삭제·앱당 알림 상한(~24)으로 놓친 결제는
이 경로로는 복구 불가 — 월간 명세서 대사로 메꾼다. 파싱 실패 알림은 버리지 않고
원문 보존 + parsed=0 (미분류)로 남긴다(침묵 실패 금지).
"""

import re
import sys
import json
import time
import shutil
import sqlite3
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

# 프로젝트 루트 = data/packages/installed/tools/spending/handler.py 에서 5단계 위.
_ROOT = Path(__file__).resolve().parents[5]
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

_DB_PATH = _ROOT / "data" / "spending.db"

# 수거 대상 결제 앱 (pkg → 표시 이름). 새 카드 앱이 생기면 여기에 한 줄.
_PAY_PKGS = {
    "com.hanaskcard.paycla": "하나카드",
    "gov.cheongju.cjpay": "청주페이",
}
_SOURCE_ALIASES = {
    "hana": "하나카드", "하나": "하나카드", "하나카드": "하나카드",
    "cjpay": "청주페이", "청주": "청주페이", "청주페이": "청주페이",
}

# 결제 알림 판별: 금액(…원)이 있고, 없으면 키워드라도 있어야 원장에 넣는다.
_RE_AMOUNT = re.compile(r"([0-9][0-9,]*)\s*원")
_PAY_KEYWORDS = ("승인", "결제", "사용", "취소", "출금", "환불", "충전")


# ── 원장(SQLite) ─────────────────────────────────────────────────────────

def _conn():
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS spend (
            id         TEXT PRIMARY KEY,
            source     TEXT,             -- 하나카드/청주페이
            pkg        TEXT,
            merchant   TEXT,             -- 가맹점 (파싱 실패 시 '')
            amount     INTEGER,          -- 원 (양수; 취소도 양수 + type=cancel)
            type       TEXT,             -- approve/cancel/etc
            ts         INTEGER,          -- 알림 도착 ms (결제 시각 근사)
            title      TEXT,             -- 알림 원문 제목 (보존)
            body       TEXT,             -- 알림 원문 본문 (보존)
            parsed     INTEGER,          -- 1=금액·가맹점 파싱 성공, 0=미분류(원문만)
            created_at INTEGER
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spend_ts ON spend(ts)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sync_log (
            at INTEGER, fetched INTEGER, new INTEGER, skipped INTEGER
        )"""
    )
    return conn


def _ok(rows, **extra) -> str:
    return json.dumps(items(rows, **extra), ensure_ascii=False)


def _fail(msg: str) -> str:
    return json.dumps(items([], success=False, message=msg), ensure_ascii=False)


# ── adb ──────────────────────────────────────────────────────────────────

_ADB_CACHE = None


def _adb() -> str:
    """adb 실행 파일 경로 (PATH → 흔한 설치 위치 순)."""
    global _ADB_CACHE
    if _ADB_CACHE:
        return _ADB_CACHE
    found = shutil.which("adb")
    if not found:
        for c in (Path.home() / "Library/Android/sdk/platform-tools/adb",
                  Path("/opt/homebrew/bin/adb"), Path("/usr/local/bin/adb")):
            if c.exists():
                found = str(c)
                break
    if not found:
        raise RuntimeError("adb 를 찾을 수 없습니다 (Android platform-tools 필요)")
    _ADB_CACHE = found
    return found


def _adb_dump_notifications() -> str:
    adb = _adb()
    st = subprocess.run([adb, "get-state"], capture_output=True, timeout=10)
    if b"device" not in st.stdout:
        raise RuntimeError("폰이 USB 로 연결되어 있지 않습니다 — 연결 후 다시 눌러 주세요")
    r = subprocess.run([adb, "shell", "dumpsys", "notification", "--noredact"],
                       capture_output=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"알림 조회 실패: {r.stderr.decode('utf-8', 'ignore')[:200]}")
    return r.stdout.decode("utf-8", "ignore")


# ── dumpsys 파싱 ─────────────────────────────────────────────────────────

_RE_HDR = re.compile(r"NotificationRecord\(0x[0-9a-f]+: pkg=(\S+) .*?key=([^\s:]+):")
_STR_FIELDS = ("android.title", "android.text", "android.bigText", "android.subText")


def _extract_records(dump: str) -> list:
    """dumpsys 텍스트 → 결제 앱 활성 알림 [{pkg,key,ts,title,text,big}].

    아카이브(StatusBarNotification 행)는 텍스트가 없으므로 애초에 매칭 안 됨 —
    NotificationRecord(활성) 블록만 읽는다. 여러 섹션에 중복 등장해도
    id 해시(dedup)가 걸러낸다.
    """
    recs, cur = [], None
    pending_field = None  # (필드명, 누적 리스트) — 여러 줄 String 값
    for line in dump.splitlines():
        m = _RE_HDR.search(line)
        if m:
            if cur:
                recs.append(cur)
            pkg = m.group(1)
            cur = {"pkg": pkg, "key": m.group(2), "ts": 0} if pkg in _PAY_PKGS else None
            pending_field = None
            continue
        if cur is None:
            continue
        s = line.strip()
        if pending_field:
            name, buf = pending_field
            if s.endswith(")"):
                buf.append(s[:-1])
                cur[name] = "\n".join(buf)
                pending_field = None
            else:
                buf.append(s)
            continue
        if s.startswith("mCreationTimeMs="):
            mm = re.match(r"mCreationTimeMs=(\d+)", s)
            if mm:
                cur["ts"] = int(mm.group(1))
            continue
        for field in _STR_FIELDS:
            pref = field + "=String ("
            if s.startswith(pref):
                val = s[len(pref):]
                if val.endswith(")"):
                    cur[field] = val[:-1]
                else:
                    pending_field = (field, [val])
                break
    if cur:
        recs.append(cur)
    return recs


# ── 결제 문구 파싱 ────────────────────────────────────────────────────────
# 실측 문구가 쌓이면 여기만 다듬는다 (원문은 title/body 로 보존되므로 재파싱 가능).

_STRIP_TOKENS = re.compile(
    r"승인|결제\s*완료|결제|일시불|할부\s*\d*개월?|사용|취소|체크카드|신용카드|체크|신용|"
    r"하나카드|하나페이|청주페이|누적\s*[0-9,]*원?|잔액\s*[0-9,]*원?|님|"
    r"\d{2}[/.]\d{2}|\d{2}:\d{2}|[0-9][0-9,]*\s*원")


_MERCHANT_PATTERNS = (
    r"([가-힣A-Za-z0-9()&.\- ]{2,30}?)\s*에서\s*[0-9][0-9,]*\s*원",
    r"\d{2}:\d{2}\s+([가-힣A-Za-z0-9()&.\- ]{2,30}?)\s*(?:승인|결제|$)",
    r"[0-9][0-9,]*\s*원\s*(?:일시불|할부\s*\d*개월?)?\s*([가-힣A-Za-z0-9()&.\- ]{2,30}?)\s*(?:승인|결제|$)",
)


def _clean_merchant(s: str) -> str:
    """추출된 가맹점에서 앱 이름·상투어 껍질 제거."""
    s = re.sub(r"^(하나카드|하나페이|청주페이|결제\s*완료|승인|사용|알림|안내)\s*", "", s.strip())
    s = s.strip(" -·[]()")
    return s if 2 <= len(s) <= 30 else ""


def _merchant_from(text: str) -> str:
    if not text:
        return ""
    for pat in _MERCHANT_PATTERNS:
        mm = re.search(pat, text)
        if mm:
            got = _clean_merchant(mm.group(1))
            if got:
                return got
    return ""


def _parse_payment(title: str, body: str) -> dict:
    """알림 제목·본문 → {amount, merchant, type} (실패 필드는 비움)."""
    text = " ".join(x for x in (title, body) if x)
    out = {"amount": 0, "merchant": "", "type": "approve"}
    m = _RE_AMOUNT.search(text)
    if m:
        try:
            out["amount"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    if "취소" in text or "환불" in text:
        out["type"] = "cancel"
    elif "충전" in text and "결제" not in text:
        out["type"] = "charge"
        return out  # 충전엔 가맹점이 없다
    # 가맹점 추출 — 본문 우선(제목은 보통 앱 라벨), 실패하면 본문 토큰 소거 잔여물.
    out["merchant"] = _merchant_from(body) or _merchant_from(title)
    if not out["merchant"] and body:
        residue = _STRIP_TOKENS.sub(" ", body)
        residue = re.sub(r"\s+", " ", residue)
        out["merchant"] = _clean_merchant(residue)
    return out


def _record_to_row(rec: dict) -> dict:
    title = rec.get("android.title", "") or ""
    body = rec.get("android.bigText") or rec.get("android.text") or ""
    text = " ".join(x for x in (title, body) if x)
    has_amount = bool(_RE_AMOUNT.search(text))
    has_keyword = any(k in text for k in _PAY_KEYWORDS)
    if not has_amount and not has_keyword:
        return {}  # 결제 무관 알림(혜택·공지) — 원장에 안 넣음
    parsed = _parse_payment(title, body)
    rid = hashlib.sha1(
        f"{rec['pkg']}|{rec['key']}|{rec['ts']}|{title}|{body}".encode()).hexdigest()[:20]
    return {
        "id": rid, "pkg": rec["pkg"], "source": _PAY_PKGS[rec["pkg"]],
        "merchant": parsed["merchant"], "amount": parsed["amount"],
        "type": parsed["type"], "ts": rec["ts"] or int(time.time() * 1000),
        "title": title, "body": body,
        "parsed": 1 if (parsed["amount"] and parsed["merchant"]) else 0,
    }


# ── 표시 도우미 ──────────────────────────────────────────────────────────

def _fmt_row(r: dict) -> dict:
    dt = datetime.fromtimestamp(r["ts"] / 1000)
    prefix = "↩️ " if r["type"] == "cancel" else ("🔋 " if r["type"] == "charge" else "")
    title = r["merchant"] or r["title"] or "(미분류)"
    return {
        "id": r["id"],
        "title": f"{prefix}{title}",
        "merchant": r["merchant"],
        "amount": r["amount"],
        "amount_label": f"{r['amount']:,}원" if r["amount"] else "금액 미상",
        "date": dt.strftime("%m/%d %H:%M"),
        "source": r["source"],
        "type": r["type"],
        "summary": r["body"] or r["title"],
        "parsed": r["parsed"],
    }


def _month_range(month: str = "") -> tuple:
    """'YYYY-MM' → (시작ms, 끝ms, 라벨). 비면 이번 달."""
    now = datetime.now()
    if month:
        try:
            start = datetime.strptime(month.strip(), "%Y-%m")
        except ValueError:
            raise RuntimeError(f"month 형식은 YYYY-MM 입니다: {month}")
    else:
        start = datetime(now.year, now.month, 1)
    end = datetime(start.year + 1, 1, 1) if start.month == 12 else datetime(start.year, start.month + 1, 1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000), start.strftime("%Y년 %m월")


def _last_sync(conn) -> str:
    row = conn.execute("SELECT MAX(at) FROM sync_log").fetchone()
    if not row or not row[0]:
        return "아직 없음"
    return datetime.fromtimestamp(row[0]).strftime("%m/%d %H:%M")


def _norm_source(v: str) -> str:
    return _SOURCE_ALIASES.get((v or "").strip().lower(), (v or "").strip())


# ── ops ──────────────────────────────────────────────────────────────────

def _fn_sync(params: dict) -> str:
    """폰(USB) 활성 알림에서 결제 내역 수거 → 원장 병합."""
    try:
        dump = _adb_dump_notifications()
    except RuntimeError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    recs = _extract_records(dump)
    rows = [r for r in (_record_to_row(rec) for rec in recs) if r]
    skipped = len(recs) - len(rows)
    conn = _conn()
    new = []
    for r in rows:
        cur = conn.execute(
            "INSERT OR IGNORE INTO spend (id, source, pkg, merchant, amount, type, ts, title, body, parsed, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["source"], r["pkg"], r["merchant"], r["amount"], r["type"],
             r["ts"], r["title"], r["body"], r["parsed"], int(time.time())))
        if cur.rowcount > 0:
            new.append(r)
    conn.execute("INSERT INTO sync_log (at, fetched, new, skipped) VALUES (?,?,?,?)",
                 (int(time.time()), len(rows), len(new), skipped))
    conn.commit()
    conn.close()
    unparsed = sum(1 for r in new if not r["parsed"])
    msg = f"결제 알림 {len(rows)}건 확인, 새 내역 {len(new)}건 수거"
    if unparsed:
        msg += f" (미분류 {unparsed}건 — 원문 보존됨)"
    if not rows:
        msg = "폰에 결제 알림이 없습니다. 알림을 지우기 전에 수거해야 내역이 남습니다."
    return json.dumps({
        "success": True, "fetched": len(rows), "new": len(new),
        "skipped_non_payment": skipped, "unparsed": unparsed,
        "collected": [_fmt_row(r) for r in new[:20]],
        "message": msg + (" — 수거된 알림은 이제 지우셔도 됩니다." if new else ""),
    }, ensure_ascii=False)


def _fn_list(params: dict) -> str:
    """지출 내역 조회 (기본: 이번 달)."""
    month = str(params.get("month") or "")
    days = params.get("days")
    source = _norm_source(str(params.get("source") or ""))
    query = str(params.get("query") or "").strip()
    limit = int(params.get("limit") or 100)
    conn = _conn()
    where, args = [], []
    if days:
        since = int((datetime.now() - timedelta(days=int(days))).timestamp() * 1000)
        where.append("ts >= ?")
        args.append(since)
        label = f"최근 {int(days)}일"
    else:
        s, e, label = _month_range(month)
        where.append("ts >= ? AND ts < ?")
        args.extend([s, e])
    if source:
        where.append("source = ?")
        args.append(source)
    if query:
        where.append("(merchant LIKE ? OR body LIKE ? OR title LIKE ?)")
        args.extend([f"%{query}%"] * 3)
    sql = "SELECT id, source, pkg, merchant, amount, type, ts, title, body, parsed FROM spend"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts DESC LIMIT ?"
    args.append(limit)
    cols = ["id", "source", "pkg", "merchant", "amount", "type", "ts", "title", "body", "parsed"]
    rows = [dict(zip(cols, r)) for r in conn.execute(sql, args).fetchall()]
    total = sum(r["amount"] for r in rows if r["type"] == "approve") \
        - sum(r["amount"] for r in rows if r["type"] == "cancel")
    last = _last_sync(conn)
    conn.close()
    msg = "" if rows else f"{label} 내역이 없습니다. 폰을 USB 로 연결하고 업데이트를 눌러 주세요."
    return _ok([_fmt_row(r) for r in rows], success=True,
               period=label, count=len(rows), total=total,
               total_label=f"{total:,}원", last_sync=last, message=msg,
               sync_prompt=[{"hint": "폰을 USB 로 연결한 뒤 누르세요. 수거 후엔 폰 알림을 지워도 됩니다."}])


def _fn_summary(params: dict) -> str:
    """월간 통계 — 합계·출처별·상위 가맹점."""
    month = str(params.get("month") or "")
    s, e, label = _month_range(month)
    conn = _conn()
    cols = ["source", "merchant", "amount", "type"]
    rows = [dict(zip(cols, r)) for r in conn.execute(
        "SELECT source, merchant, amount, type FROM spend WHERE ts >= ? AND ts < ?",
        (s, e)).fetchall()]
    last = _last_sync(conn)
    conn.close()
    spend = sum(r["amount"] for r in rows if r["type"] == "approve")
    cancel = sum(r["amount"] for r in rows if r["type"] == "cancel")
    by_source = {}
    merchants = {}
    for r in rows:
        sign = -1 if r["type"] == "cancel" else (0 if r["type"] == "charge" else 1)
        by_source[r["source"]] = by_source.get(r["source"], 0) + sign * r["amount"]
        if r["type"] == "approve":
            key = r["merchant"] or "(미분류)"
            m = merchants.setdefault(key, {"merchant": key, "count": 0, "amount": 0})
            m["count"] += 1
            m["amount"] += r["amount"]
    top = sorted(merchants.values(), key=lambda x: -x["amount"])[:15]
    for t in top:
        t["amount_label"] = f"{t['amount']:,}원"
    net = spend - cancel
    return _ok(top, success=True, period=label, count=len(rows),
               total=net, total_label=f"{net:,}원",
               spend_label=f"{spend:,}원", cancel_label=f"{cancel:,}원",
               hana_label=f"{by_source.get('하나카드', 0):,}원",
               cjpay_label=f"{by_source.get('청주페이', 0):,}원",
               last_sync=last,
               message="" if rows else f"{label} 내역이 없습니다.")


_OP_DISPATCHERS = {
    "spend_op": {
        "sync": _fn_sync,
        "list": _fn_list,
        "summary": _fn_summary,
    },
}
_OP_DEFAULTS = {
    "spend_op": "list",
}


def execute(tool_input: dict, context) -> str:
    """지출내역 도구 실행 (ToolContext 시그니처)."""
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = tool_input.get("op") or _OP_DEFAULTS.get(tool_name)
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if not fn:
                return json.dumps({"success": False, "error": f"알 수 없는 op: {op}"}, ensure_ascii=False)
            return fn(tool_input)
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"오류: {e}"}, ensure_ascii=False)
