"""finance_sync — 결제 앱 알림 수거기 (구 spending 패키지에서 이식, 2026-08-14 합병).

결제 앱(하나카드·청주페이)의 승인 푸시 알림을, 폰을 USB 로 연결했을 때
`adb dumpsys notification` 으로 수거해 **재무 원장(finance_records.db)의 거래**로 병합.

원리(사용자 운용 규약): 폰에서 결제 알림을 **지우지 않고 모아두면** 활성 알림에
제목·본문이 남아 dumpsys 로 읽힌다 — 수거 후에 지우는 것이 안전한 순서.
한계(정직 신고): 재부팅·수거 전 삭제·앱당 상한(~24)으로 놓친 결제는 이 경로로 복구
불가(월간 명세서 대사로 메꿈). 파싱 실패 알림은 원문 보존 + parsed=0 (침묵 실패 금지).
이 모듈은 수거·파싱만 — 원장 기록은 handler/finance_storage 몫 (층 분리).
"""
import re
import time
import shutil
import hashlib
import subprocess
from pathlib import Path

# 수거 대상 결제 앱 (pkg → 표시 이름). 새 카드 앱이 생기면 여기에 한 줄.
PAY_PKGS = {
    "com.hanaskcard.paycla": "하나카드",
    "gov.cheongju.cjpay": "청주페이",
}
SOURCE_ALIASES = {
    "hana": "하나카드", "하나": "하나카드", "하나카드": "하나카드",
    "cjpay": "청주페이", "청주": "청주페이", "청주페이": "청주페이",
}

_RE_AMOUNT = re.compile(r"([0-9][0-9,]*)\s*원")
_PAY_KEYWORDS = ("승인", "결제", "사용", "취소", "출금", "환불", "충전")

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


_RE_HDR = re.compile(r"NotificationRecord\(0x[0-9a-f]+: pkg=(\S+) .*?key=([^\s:]+):")
_STR_FIELDS = ("android.title", "android.text", "android.bigText", "android.subText")


def _extract_records(dump: str) -> list:
    """dumpsys 텍스트 → 결제 앱 활성 알림 [{pkg,key,ts,title,text,big}].
    아카이브 행은 텍스트가 없어 애초에 매칭 안 됨 — NotificationRecord(활성)만."""
    recs, cur = [], None
    pending_field = None
    for line in dump.splitlines():
        m = _RE_HDR.search(line)
        if m:
            if cur:
                recs.append(cur)
            pkg = m.group(1)
            cur = {"pkg": pkg, "key": m.group(2), "ts": 0} if pkg in PAY_PKGS else None
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


# ── 결제 문구 파싱 (실측 문구가 쌓이면 여기만 다듬는다 — 원문은 note 로 보존) ──

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
    if not _RE_AMOUNT.search(text) and not any(k in text for k in _PAY_KEYWORDS):
        return {}  # 결제 무관 알림(혜택·공지)
    parsed = _parse_payment(title, body)
    rid = hashlib.sha1(
        f"{rec['pkg']}|{rec['key']}|{rec['ts']}|{title}|{body}".encode()).hexdigest()[:20]
    return {
        "ext_id": rid, "pkg": rec["pkg"], "source": PAY_PKGS[rec["pkg"]],
        "merchant": parsed["merchant"], "amount": parsed["amount"],
        "type": parsed["type"], "ts": rec["ts"] or int(time.time() * 1000),
        "title": title, "body": body,
        "parsed": 1 if (parsed["amount"] and parsed["merchant"]) else 0,
    }


def collect_from_phone() -> tuple:
    """폰(USB) 활성 알림 수거 → (결제 행 목록, 결제무관 스킵 수). RuntimeError=정직 거부."""
    dump = _adb_dump_notifications()
    recs = _extract_records(dump)
    rows = [r for r in (_record_to_row(rec) for rec in recs) if r]
    return rows, len(recs) - len(rows)


def norm_source(v: str) -> str:
    return SOURCE_ALIASES.get((v or "").strip().lower(), (v or "").strip())
