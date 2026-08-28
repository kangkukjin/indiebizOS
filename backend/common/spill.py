"""spill.py — 파이프 통화의 스필(외부화)과 참조 해소 (2026-08-22, 프로그램급 IBL M5 / 설계 §2.5-3·2.6).

크기는 문장이 모르는 런타임 사실이라 엔진만 안다. 통화가 임계를 넘으면 엔진이 파일로 내리고
파이프에는 **참조**만 흘린다 — 그리고 **신고**한다(침묵 클램프 금지).

참조 봉투 모양(= `[self:write]{spill:true}` 와 같은 규약):
    {"items": [], "ref": {"path", "kind", "count", "bytes", "expires_at"}, "_spilled": true}

소비자(변환자 `_get_items`·each 입력·$items 바인딩·write 싱크)는 `resolve_ref` 한 줄로 투명하게
읽는다. 디렉토리 `data/spill/` 은 소유 선언상 **cache** 계급 — 문장을 다시 돌리면 재생산되는
파생물이라 기계 삭제가 맞다(2026-08-22 판정): 쓸 때마다 24h 지난 파일을 기회주의적으로 거둔다.
"""
import json
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

SPILL_TTL_S = 24 * 3600
AUTO_SPILL_THRESHOLD = 200_000          # 문자 — 이 위는 모델 컨텍스트로 돌려 보낼 크기가 아니다
# 봉투 **표시 사본**의 가지당 상한 — providers 절단(액션당 MAX_TOOL_RESULT_LENGTH=16,000,
# 3벌 동일)과 동율. 병렬 가지 원형이 이 위면 표시 사본을 스필 참조+preview 로 바꾼다
# (2026-08-29: 구조-무지 머리·꼬리 절단이 첫 큰 가지 뒤의 가지를 통째로 증발시키던 자리).
ENVELOPE_KEEP_MAX = 16_000


def _root() -> str:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "data", "spill")


def spill_dir() -> str:
    d = _root()
    os.makedirs(d, exist_ok=True)
    return d


def gc(max_age_s: int = SPILL_TTL_S) -> int:
    """TTL 지난 스필 파일 삭제 — 삭제 수 반환. 실패는 조용히(캐시 청소가 본 작업을 깨면 안 된다)."""
    n = 0
    try:
        d = _root()
        if not os.path.isdir(d):
            return 0
        now = time.time()
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if os.path.isfile(p) and now - os.path.getmtime(p) > max_age_s:
                    os.remove(p)
                    n += 1
            except OSError:
                pass
    except Exception:
        pass
    return n


def make_ref(path: str, kind: str, count: Optional[int], nbytes: int) -> Dict[str, Any]:
    return {"path": path, "kind": kind, "count": count, "bytes": nbytes,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + SPILL_TTL_S))}


def spill_write(payload: str, tag: str = "step") -> Dict[str, Any]:
    """통화(문자열)를 스필 파일로 내리고 참조 봉투(dict)를 돌려준다."""
    gc()
    d = spill_dir()
    name = f"{time.strftime('%Y%m%d_%H%M%S')}_{tag}_{uuid.uuid4().hex[:6]}.json"
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(payload)
    kind, count = "text", None
    s = payload.lstrip()
    if s[:1] in "{[":
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict) and isinstance(obj.get("items"), list):
                kind, count = "items", len(obj["items"])
            elif isinstance(obj, list):
                kind, count = "list", len(obj)
            else:
                kind = "json"
        except Exception:
            pass
    return {"items": [], "ref": make_ref(path, kind, count, len(payload)), "_spilled": True}


def is_ref(obj: Any) -> bool:
    return (isinstance(obj, dict) and isinstance(obj.get("ref"), dict)
            and isinstance(obj["ref"].get("path"), str)
            and (obj.get("_spilled") or obj.get("spilled")))


def read_ref(ref: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """(본문, 오류문). 만료·부재는 정직한 오류."""
    path = ref.get("path")
    if not path or not os.path.isfile(path):
        return None, (f"스필 참조가 가리키는 파일이 없습니다: {path} — 스필은 {SPILL_TTL_S // 3600}h 뒤 "
                      "삭제됩니다(캐시). 문장을 다시 실행하세요.")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(), None
    except OSError as e:
        return None, f"스필 참조 읽기 실패: {e}"


def resolve_ref(obj: Any) -> Tuple[Any, Optional[str]]:
    """참조 봉투면 본문(파싱 시도)으로, 아니면 그대로. (값, 오류문)."""
    if not is_ref(obj):
        return obj, None
    body, err = read_ref(obj["ref"])
    if err:
        return obj, err
    s = body.lstrip()
    if s[:1] in "{[":
        try:
            return json.loads(body), None
        except Exception:
            pass
    return body, None


def resolve_ref_str(raw: Any) -> Tuple[Any, Optional[str]]:
    """문자열 봉투(JSON)도 받는 해소판 — 파이프 이음매(_prev_result)는 문자열이다."""
    if isinstance(raw, str):
        s = raw.lstrip()
        if s.startswith("{") and '"ref"' in s[:400]:
            try:
                obj = json.loads(raw)
            except Exception:
                return raw, None
            if is_ref(obj):
                return resolve_ref(obj)
        return raw, None
    return resolve_ref(raw)


# ── 표면 티켓 — 표면 대기가 끊겨도 실행 결과 봉투는 잃지 않는다 (F51-1, 2026-08-27) ──
# 실측 사고: 2분 10초짜리 긴 문장이 **실행을 완주해 파일까지 만들었는데**, MCP 표면
# (mcp_server.execute_ibl)의 HTTP 대기 120초가 먼저 끊겨 {"error": "timed out"} 만 남고
# 최종 봉투(정직 표지 포함)가 증발했다. 실행이 산 채로 결과만 잃는 것은 조합 표현력의
# 실질적 상한이었다. 수리 = 표면이 티켓을 실어 보내면 백엔드가 최종 봉투를 여기(cache
# 계급, 24h gc 동승)에 남기고, 표면은 타임아웃 시 정직한 봉투("실행은 계속 돈다,
# recover 로 회수")를 돌려준다. 회수는 유한 대기의 반복이라 어떤 길이의 실행도 덮는다.
import re as _re

_TICKET_RX = _re.compile(r"^[0-9a-f]{8,32}$")   # 네트워크에서 온 값이 파일명이 된다 — hex 만


def valid_ticket(ticket) -> bool:
    return isinstance(ticket, str) and bool(_TICKET_RX.fullmatch(ticket))


def _ticket_path(ticket: str) -> str:
    return os.path.join(spill_dir(), f"ticket_{ticket}.json")


def ticket_begin(ticket: str) -> bool:
    """실행 시작 표식 — running 상태를 남긴다(끝 표식과 같은 파일을 덮어쓴다)."""
    if not valid_ticket(ticket):
        return False
    gc()
    with open(_ticket_path(ticket), "w", encoding="utf-8") as f:
        json.dump({"status": "running",
                   "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, f, ensure_ascii=False)
    return True


def ticket_progress(ticket: str, progress: dict) -> bool:
    """running 기록에 진행 상태를 덧쓴다 — 결말(done)은 절대 덮지 않는다 (2026-08-29 ⑨).

    실측 배경: 120초 표면 대기를 넘긴 216초 실행을 recover 로 물었더니 `status:
    "running"` 뿐이라 3회 헛폴링 — 어디까지 왔는지 없는 대기는 눈 감은 대기다.
    엔진의 최외곽 파이프라인이 step 경계마다 이 함수를 부른다. 진행 신고는
    best-effort 다: 실패해도 조용히(진행 표식이 본 실행을 깨면 안 된다)."""
    if not valid_ticket(ticket):
        return False
    path = _ticket_path(ticket)
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        if rec.get("status") != "running":
            return False
        rec["progress"] = dict(progress)
        rec["progress"]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def ticket_finish(ticket: str, envelope) -> bool:
    """최종 봉투 보관 — 성공이든 실패든 **결말**을 남긴다(모름과 실패는 다른 사건)."""
    if not valid_ticket(ticket):
        return False
    with open(_ticket_path(ticket), "w", encoding="utf-8") as f:
        json.dump({"status": "done",
                   "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "envelope": envelope}, f, ensure_ascii=False, default=str)
    return True


def ticket_recover(ticket: str) -> dict:
    """티켓의 현재 상태 — 3상태를 뭉개지 않는다(B28-1: '못 봤다'와 '없다'는 다른 사건).

    done    → 보관된 원 봉투(+회수 표식)
    running → 아직 도는 중(started_at 동봉) — 잠시 후 같은 recover 로 다시
    unknown → 기록 없음: 24h 만료 **또는** 티켓 미탑재 실행 — 어느 쪽인지 여기선 모른다
    """
    if not valid_ticket(ticket):
        return {"success": False, "status": "invalid",
                "error": "ticket 형식이 아닙니다 — hex 8~32자."}
    try:
        with open(_ticket_path(ticket), encoding="utf-8") as f:
            rec = json.load(f)
    except FileNotFoundError:
        return {"success": False, "status": "unknown",
                "error": (f"티켓 {ticket} 의 기록이 없습니다 — 보관 만료({SPILL_TTL_S // 3600}h)"
                          "였거나, 티켓 없이 시작된 실행입니다. 어느 쪽인지는 판정 불능입니다.")}
    except Exception as e:
        return {"success": False, "status": "unreadable",
                "error": f"티켓 기록을 읽지 못했습니다: {e}"}
    if rec.get("status") == "running":
        out = {"success": True, "status": "running",
               "started_at": rec.get("started_at"),
               "note": "실행이 아직 돌고 있습니다 — 잠시 후 같은 recover 로 다시 물으세요."}
        prog = rec.get("progress")
        if isinstance(prog, dict):
            # 진행 동봉(2026-08-29 ⑨) — 헛폴링 방지: 어느 step 이 언제부터 돌고 있는지.
            out["progress"] = prog
            if prog.get("step") and prog.get("of"):
                out["note"] = (f"실행이 아직 돌고 있습니다 — step {prog['step']}/{prog['of']}"
                               f" {prog.get('action') or ''} 진행 중(마지막 갱신 "
                               f"{prog.get('updated_at')}). 잠시 후 같은 recover 로 다시 물으세요.")
        return out
    env = rec.get("envelope")
    if isinstance(env, dict):
        env.setdefault("_recovered_from_ticket", ticket)
        return env
    return {"success": True, "status": "done", "result": env,
            "_recovered_from_ticket": ticket}
