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

# 결제 앱이 보내는 광고 푸시. 광고는 정의상 가격을 담으므로 "금액 문구"만으로는
# 절대 못 거른다 (실측 2026-08-17: 청주페이 "(광고) …30캡슐=7,900원 특가" 가
# 7,900원 지출로 원장에 적재됨). "(광고)" 는 정보통신망법상 의무 표기라 신호가 강하다.
_PROMO_RE = re.compile(r"\(\s*광고\s*\)|\[\s*광고\s*\]|^광고\s|수신\s*거부|무료거부")

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
        # ★ts = mCreationTimeMs 가 정본. 이것이 StatusBarNotification.postTime 과 같은 값이라
        # 폰 포획소가 적는 posted_at 과 일치하고, 두 수거 경로가 같은 결제에 같은 ext_id 를 준다.
        # (2026-08-17 실기 실측: 같은 알림에서 postTime=mCreationTimeMs=…373, 반면 `when=`
        #  은 …275 로 98ms 다른 별개 필드[앱이 정한 표시 시각]다. when 을 쓰면 중복 적재된다.)
        if s.startswith("mCreationTimeMs="):
            mm = re.match(r"mCreationTimeMs=(\d+)", s)
            if mm:
                cur["ts"] = int(mm.group(1))
            continue
        if s.startswith("when=") and not cur.get("ts"):
            mm = re.match(r"when=(\d+)", s)   # mCreationTimeMs 없는 기기 폴백
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
    if _PROMO_RE.search(text):
        return {}  # 광고 푸시 — 가격이 들어 있어도 결제가 아니다
    # ★AND 게이트: 금액과 결제 동사가 **둘 다** 있어야 결제 후보.
    # 옛 OR 게이트는 주석이 "혜택·공지를 거른다"였는데 금액만으로 통과시켜,
    # 거르려던 바로 그 부류(광고)를 가장 확실하게 통과시켰다.
    # 실패 방향은 의도적으로 비대칭 — 못 거두면 명세서 대사로 메꿀 수 있지만,
    # 원장에 들어간 거짓 지출은 사용자가 눈으로 찾아 지워야 한다.
    if not (_RE_AMOUNT.search(text) and any(k in text for k in _PAY_KEYWORDS)):
        return {}  # 결제 무관 알림(혜택·공지)
    parsed = _parse_payment(title, body)
    # ★중복 방지 키에 알림 key 를 넣지 않는다 — 폰 포획소엔 그 값이 없다.
    # pkg|ts|제목|본문 만으로 두 수거 경로(포획소·dumpsys)가 같은 결제에 같은 id 를 준다.
    # ★공백 정규화 필수(2026-08-17 실기 실측): dumpsys 는 여러 줄 필드를 줄마다 strip 해
    # 붙이므로 같은 알림인데도 포획소 원문과 공백이 달라져 id 가 갈렸다. 저장은 원문 그대로,
    # id 계산만 정규화한다.
    _n = lambda s: re.sub(r"\s+", " ", s or "").strip()
    rid = hashlib.sha1(
        f"{rec['pkg']}|{rec['ts']}|{_n(title)}|{_n(body)}".encode()).hexdigest()[:20]
    return {
        "ext_id": rid, "pkg": rec["pkg"], "source": PAY_PKGS[rec["pkg"]],
        "merchant": parsed["merchant"], "amount": parsed["amount"],
        "type": parsed["type"], "ts": rec["ts"] or int(time.time() * 1000),
        "title": title, "body": body,
        "parsed": 1 if (parsed["amount"] and parsed["merchant"]) else 0,
    }


# ── 폰 포획소 (NotificationCaptureService 가 t=0 에 붙잡아 둔 원문) ──
# 활성 알림(dumpsys)은 72시간 만료·탭 시 소멸로 사라지지만 포획소는 남는다.
CAPTURE_PKG = "com.indiebiz.phoneagent"
CAPTURE_PATH = "files/signals/notifications.jsonl"


def _read_phone_capture():
    """폰 포획소 JSONL → dumpsys 와 같은 모양의 레코드 목록. None = 포획소 없음."""
    adb = _adb()
    r = subprocess.run([adb, "shell", "run-as", CAPTURE_PKG, "cat", CAPTURE_PATH],
                       capture_output=True, timeout=30)
    out = r.stdout.decode("utf-8", "ignore")
    if r.returncode != 0 or "No such file" in out or not out.strip():
        return None  # 서비스가 아직 안 켜졌거나 포획분이 없다 — 호출자가 dumpsys 로 폴백
    recs = []
    import json as _json
    for line in out.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            d = _json.loads(line)
        except ValueError:
            continue  # 깨진 줄은 건너뛴다(원문 보존이 목적이라 조용히 버리지 않고 넘어감)
        if not isinstance(d, dict):
            continue  # 유효한 JSON 이지만 객체가 아닌 줄(문자열·숫자)
        if d.get("type", "notification") != "notification":
            continue
        pkg = d.get("pkg") or ""
        if pkg not in PAY_PKGS:
            continue  # 포획소는 화이트리스트지만 방어적으로 한 번 더
        recs.append({
            "pkg": pkg, "key": "", "ts": int(d.get("posted_at") or 0),
            "android.title": d.get("title") or "",
            "android.bigText": d.get("text") or d.get("body") or "",
        })
    return recs


def collect_from_phone() -> tuple:
    """폰(USB) 결제 알림 수거 → (결제 행 목록, 결제무관 스킵 수, 출처 라벨).

    포획소 우선 — 활성 알림만 읽던 옛 경로는 72시간 만료분을 원리적으로 못 가져온다.
    포획소가 없으면(서비스 미허용) dumpsys 로 폴백하되 출처를 정직하게 알린다.
    RuntimeError=정직 거부."""
    adb = _adb()
    st = subprocess.run([adb, "get-state"], capture_output=True, timeout=10)
    if b"device" not in st.stdout:
        raise RuntimeError("폰이 USB 로 연결되어 있지 않습니다 — 연결 후 다시 눌러 주세요")

    recs, source = _read_phone_capture(), "capture"
    if recs is None:
        recs, source = _extract_records(_adb_dump_notifications()), "dumpsys"
    rows = [r for r in (_record_to_row(rec) for rec in recs) if r]
    return rows, len(recs) - len(rows), source


def norm_source(v: str) -> str:
    return SOURCE_ALIASES.get((v or "").strip().lower(), (v or "").strip())
