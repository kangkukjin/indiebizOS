"""forage_memory.py — 개인-forager 지속 기억 (2층 냄새지도).

설계: docs/FORAGER_MEMORY_SCHEMA.md.

forager(=AI)가 디스크·웹·코드를 *포식*하며 배운 것을 세션 너머로 누적한다.
이건 forager 루프가 아니라 forager가 결여한 *지속 기억*이다(루프는 인지층 AI).

  forage_map   — 몸별 지도(이 디스크/볼륨 전속): 폴더 정체·관습·죽은 가지·기질.
  owner_model  — 몸독립 주인모델(모든 몸 공유): 정체·분야·소속·내용신호·어휘매핑.

해마([[execution-memory-architecture]])의 *공간판* — 증류(경험 누적)·정리(위생)·
lazy freshness(감쇠 곡선 대신 mtime 노출, 판단은 AI). 안전판 4(defeasible+prune_reason /
prior_class 게이팅 / surface 카운터패스 / provenance)를 스키마가 강제한다.

★맥 자아 전용(주관적 기억은 자아별 사적 — memory_architecture "다중 자아"). 폰은 A3 후속.
"""
from __future__ import annotations

import os
import re
import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from logging_utils import mask_secrets  # 영속 관문 마스킹(에피소드 로그와 같은 원칙)

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data", "forage_memory.db")

# 형성 시점 mtime 과 현재 mtime 차이가 이보다 크면 stale(디스크 변경). 초.
_STALE_TOL = 2.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS forage_map (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    body         TEXT NOT NULL,              -- "mac" | "disk:<uuid>" | "phone"
    locus        TEXT NOT NULL,              -- 절대경로 | "__substrate__"
    kind         TEXT NOT NULL,              -- identity|convention|dead_branch|substrate
    claim        TEXT NOT NULL,
    prior_class  TEXT NOT NULL DEFAULT 'structural',  -- structural|semantic
    confidence   REAL NOT NULL DEFAULT 0.7,
    provenance   TEXT,                        -- JSON {forage_id,query,observed[],formed_at,reinforced_by[]}
    prune_reason TEXT,                        -- defeasible: "~이유로 아마 죽음"
    generalizes  INTEGER NOT NULL DEFAULT 0,  -- convention 이 새 가지에도 적용되나
    last_seen    TEXT,
    locus_mtime  REAL NOT NULL DEFAULT 0,     -- 형성 시점 locus mtime (부패 무효화용)
    surface_flag INTEGER NOT NULL DEFAULT 0,  -- 이 라벨을 의심하라(이질 내용 발견)
    territory    INTEGER NOT NULL DEFAULT 0,  -- 거친 영토 앵커(상시-on, 열거가능 공간만). go/skip 은 런타임 파생
    UNIQUE(body, locus, kind, claim)   -- 2026-09-03: 한 자리에 같은 종류의 단언 여럿(정본=문서 절의 줄들). 옛 키 (body,locus,kind) 는 _migrate_unique_key 가 옮긴다
);
CREATE TABLE IF NOT EXISTS owner_model (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    facet        TEXT NOT NULL,               -- identity|domain|affiliation|signal|lexicon|habit
    value        TEXT NOT NULL,
    prior_class  TEXT NOT NULL DEFAULT 'semantic',
    confidence   REAL NOT NULL DEFAULT 0.6,
    provenance   TEXT,
    last_seen    TEXT,
    surface_flag INTEGER NOT NULL DEFAULT 0,
    scent        INTEGER NOT NULL DEFAULT 0,  -- 상시-on 냄새로 결정화됐나(빈도 게이트). 0=임시(질의 필터)
    UNIQUE(facet, value)
);
CREATE TABLE IF NOT EXISTS forage_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_MAP_KINDS = ("identity", "convention", "dead_branch", "substrate")
_OWNER_FACETS = ("identity", "domain", "affiliation", "signal", "lexicon", "habit")
_PRIOR_CLASSES = ("structural", "semantic")

# 상시-on 영토 지도의 하드 상한 — 프롬프트가 무한정 늘지 않도록.
# 영토 앵커가 이보다 많이 쌓여도 confidence 상위 N 개만 냄새로 노출(나머지는 query 필터로 강등).
_TERRITORY_CAP = 10
_TERRITORY_CLAIM_MAX = 64  # 영토 한 줄 claim 길이 상한(거친 윤곽만)
# 자동승격: identity 가 reinforced_by 로 이만큼 재확인되면(=여러 번 되돌아온 가지) territory 로 결정화.
# '빈도가 결정화한다'(자율주행→수동→앱)와 같은 모티프 — 자기-바운딩(대부분 가지는 1회뿐). cap 이 2차 백스톱.
_TERRITORY_PROMOTE_AT = 2

# owner(주인모델)도 같은 빈도 게이트를 쓴다 — territory 와 대칭.
# 왜: owner 는 query 면제 *상시* 노출(냄새)이라, 단 1회 포식에서 LLM 이 추론한 일반화가
# 그대로 모든 프롬프트에 영구 주입된다. 한 번 물어본 주제가 "습관"이 되고, 질문 *대상*이
# 주인의 "소속"이 되는 오염이 실제로 쌓였다(에피소드 881 진단 — 전 66건이 obs=1이었음).
# → 서로 다른 포식에서 재확인된 것만 냄새로 결정화. 임시(scent=0)도 *지워지지 않고*
#   map 처럼 query 필터로 회상된다(잃는 정보 0, 상시 비용만 뺀다).
_OWNER_SCENT_PROMOTE_AT = 2
_OWNER_SCENT_CAP = 8  # 결정화된 냄새의 하드 상한(프롬프트 무한증식 차단, _TERRITORY_CAP 대응)


def _territory_eligible(kind: str, locus: str) -> bool:
    """영토 승격 자격 — 정체(identity)이고 *구체 경로*(열거가능 공간)일 때만.
    웹 추상 locus·__substrate__·관습은 영토가 아니다(territory=장소 정체 전용 → 웹 자동 배제)."""
    return kind == "identity" and bool(locus) and (locus.startswith("/") or locus.startswith("~"))


def _short(text: str, n: int = _TERRITORY_CLAIM_MAX) -> str:
    """거친 영토용 짧은 형태 — 첫 문장 또는 n 자에서 자름."""
    t = (text or "").strip().replace("\n", " ")
    for sep in (". ", ". ", " — ", " · "):
        i = t.find(sep)
        if 0 < i <= n:
            return t[:i]
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(os.path.abspath(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # 마이그레이션: 기존 DB 에 territory 컬럼 없으면 추가
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(forage_map)")}
    if "territory" not in cols:
        conn.execute("ALTER TABLE forage_map ADD COLUMN territory INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    # 마이그레이션: owner_model.scent — 기존 행은 *지우지 않고* provenance 의 실제 관측 수로 판정.
    #   재확인된 적 없는(obs=1) 항목은 임시로 강등되어 질의 필터로만 회상된다.
    ocols = {r["name"] for r in conn.execute("PRAGMA table_info(owner_model)")}
    if "scent" not in ocols:
        conn.execute("ALTER TABLE owner_model ADD COLUMN scent INTEGER NOT NULL DEFAULT 0")
        promoted = 0
        for r in conn.execute("SELECT id, provenance FROM owner_model").fetchall():
            if _distinct_observations(r["provenance"]) >= _OWNER_SCENT_PROMOTE_AT:
                conn.execute("UPDATE owner_model SET scent=1 WHERE id=?", (r["id"],))
                promoted += 1
        conn.commit()
        print(f"[포식기억] owner_model.scent 마이그레이션: 결정화 {promoted}건, 나머지는 임시(질의 필터)")
    _migrate_unique_key(conn)
    return conn


def _migrate_unique_key(conn: sqlite3.Connection) -> None:
    """(body,locus,kind) 유일 키 → (body,locus,kind,claim). 문서 정본(2026-09-03)은 한 자리에 같은 종류의 줄 여럿을 허용한다.
    SQLite 는 제약을 못 바꾸므로 표를 다시 만든다(멱등: 옛 제약이 있을 때만)."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='forage_map'").fetchone()
    if not row or "UNIQUE(body, locus, kind, claim)" in (row[0] or ""):
        return
    cols = "id, body, locus, kind, claim, prior_class, confidence, provenance, prune_reason, generalizes, last_seen, locus_mtime, surface_flag, territory"
    conn.executescript(f"""
        BEGIN;
        CREATE TABLE forage_map_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL, locus TEXT NOT NULL, kind TEXT NOT NULL, claim TEXT NOT NULL,
            prior_class TEXT NOT NULL DEFAULT 'structural', confidence REAL NOT NULL DEFAULT 0.7, provenance TEXT, prune_reason TEXT,
            generalizes INTEGER NOT NULL DEFAULT 0, last_seen TEXT, locus_mtime REAL NOT NULL DEFAULT 0,
            surface_flag INTEGER NOT NULL DEFAULT 0, territory INTEGER NOT NULL DEFAULT 0,
            UNIQUE(body, locus, kind, claim));
        INSERT INTO forage_map_new ({cols}) SELECT {cols} FROM forage_map;
        DROP TABLE forage_map;
        ALTER TABLE forage_map_new RENAME TO forage_map;
        COMMIT;
    """)
    print("[포식기억] forage_map 유일 키 이관: (body,locus,kind) → (body,locus,kind,claim)")


def _locus_mtime(locus: str) -> float:
    """locus 의 현재 mtime. 경로 아니거나 부재면 0."""
    if not locus or locus.startswith("__"):
        return 0.0
    try:
        return os.stat(os.path.expanduser(locus)).st_mtime
    except OSError:
        return 0.0


def _clamp_conf(v: Any, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, f))


def _distinct_observations(provenance: Any) -> int:
    """provenance 에 기록된 *서로 다른* 관측 수(query 기준).

    같은 포식에서 같은 값을 두 번 적어도 1회로 센다 — '빈도'는 서로 다른 포식이어야 의미가 있다.
    """
    try:
        p = json.loads(provenance) if isinstance(provenance, str) else (provenance or {})
    except (ValueError, TypeError):
        p = {}
    if not isinstance(p, dict):
        return 1
    seen = set()
    q0 = str(p.get("query") or "").strip()
    if q0:
        seen.add(q0)
    for stamp in (p.get("reinforced_by") or []):
        if isinstance(stamp, dict):
            q = str(stamp.get("query") or "").strip()
            if q:
                seen.add(q)
    return max(1, len(seen))


def _merge_provenance(old_json: Optional[str], new_prov: Optional[Dict[str, Any]]) -> str:
    """기존 provenance 에 새 관측을 reinforced_by 로 누적(복리 루프)."""
    try:
        base = json.loads(old_json) if old_json else {}
    except (ValueError, TypeError):
        base = {}
    if not isinstance(base, dict):
        base = {}
    if new_prov:
        rb = base.setdefault("reinforced_by", [])
        if isinstance(rb, list):
            stamp = {k: new_prov.get(k) for k in ("forage_id", "query", "formed_at") if new_prov.get(k)}
            if stamp:
                rb.append(stamp)
        # 첫 형성 메타가 비어 있으면 새 것으로 채움
        for k in ("forage_id", "query", "observed", "formed_at"):
            if k not in base and new_prov.get(k) is not None:
                base[k] = new_prov[k]
    return json.dumps(base, ensure_ascii=False)


# ---------------------------------------------------------------------------
# note — 지도/주인모델에 단언 누적 (증류·수동 주입 공통 경로)
# ---------------------------------------------------------------------------
def note_map(*, body: str, locus: str, kind: str, claim: str,
             prior_class: str = "structural", confidence: float = 0.7,
             provenance: Optional[Dict[str, Any]] = None,
             prune_reason: Optional[str] = None, generalizes: bool = False,
             surface_flag: bool = False, territory: bool = False) -> Dict[str, Any]:
    """forage_map 한 항목 upsert (키=body+locus+kind). 재note 시 강화(reinforce).

    territory=True 면 거친 영토 앵커로 표식 — 상시-on 냄새지도에 노출(열거가능 공간의 최상위 가지).
    """
    if kind not in _MAP_KINDS:
        return {"success": False, "error": f"kind 는 {_MAP_KINDS} 중 하나여야 합니다 (받음: {kind})"}
    if prior_class not in _PRIOR_CLASSES:
        prior_class = "structural"
    claim = mask_secrets(claim)
    if prune_reason:
        prune_reason = mask_secrets(prune_reason)
    prov = dict(provenance or {})
    if prov.get("query"):
        prov["query"] = mask_secrets(prov["query"])
    prov.setdefault("formed_at", _now())
    conf = _clamp_conf(confidence, 0.7)
    mtime = _locus_mtime(locus)
    now = _now()
    promoted = False
    conn = _connect()
    try:
        # 재확인(reinforce)은 같은 문장일 때만 — 같은 종류의 다른 문장은 새 줄(정본=문서 절, 2026-09-03)
        row = conn.execute(
            "SELECT id, confidence, provenance, territory FROM forage_map WHERE body=? AND locus=? AND kind=? AND claim=?",
            (body, locus, kind, claim)).fetchone()
        if row:
            merged = _merge_provenance(row["provenance"], prov)
            new_conf = max(conf, float(row["confidence"] or 0))  # 재확인은 확신 상향
            # territory 는 한번 켜지면 유지(재note 가 False 라도 끄지 않음 — 끄기는 consolidation/forget 몫)
            terr = 1 if (territory or row["territory"]) else 0
            if not terr and _territory_eligible(kind, locus):
                # 빈도 게이트: 여러 번 되돌아온 가지 = 영토로 결정화 (cap 이 상한 보호)
                try:
                    rb = json.loads(merged).get("reinforced_by") or []
                except (ValueError, TypeError):
                    rb = []
                if len(rb) >= _TERRITORY_PROMOTE_AT:
                    terr = 1
                    promoted = True
            conn.execute(
                "UPDATE forage_map SET claim=?, prior_class=?, confidence=?, provenance=?, "
                "prune_reason=?, generalizes=?, last_seen=?, locus_mtime=?, surface_flag=?, territory=? WHERE id=?",
                (claim, prior_class, new_conf, merged, prune_reason,
                 1 if generalizes else 0, now, mtime,
                 1 if surface_flag else 0, terr, row["id"]))
            entry_id = row["id"]
            action = "reinforced"
        else:
            cur = conn.execute(
                "INSERT INTO forage_map (body, locus, kind, claim, prior_class, confidence, "
                "provenance, prune_reason, generalizes, last_seen, locus_mtime, surface_flag, territory) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (body, locus, kind, claim, prior_class, conf,
                 json.dumps(prov, ensure_ascii=False), prune_reason,
                 1 if generalizes else 0, now, mtime, 1 if surface_flag else 0,
                 1 if territory else 0))
            entry_id = cur.lastrowid
            action = "noted"
        conn.commit()
    finally:
        conn.close()
    _doc_refresh(body, locus, own_node=bool(territory))   # 정본=문서: 절 재렌더. 영토 앵커면 그 폴더 자기 노드에 문서
    return {"success": True, "action": action, "id": entry_id, "table": "forage_map",
            "promoted_territory": promoted}


def note_owner(*, facet: str, value: str, prior_class: str = "semantic",
               confidence: float = 0.6, provenance: Optional[Dict[str, Any]] = None,
               surface_flag: bool = False) -> Dict[str, Any]:
    """owner_model 한 항목 upsert (키=facet+value). 재note 시 강화."""
    if facet not in _OWNER_FACETS:
        return {"success": False, "error": f"facet 은 {_OWNER_FACETS} 중 하나여야 합니다 (받음: {facet})"}
    if prior_class not in _PRIOR_CLASSES:
        prior_class = "semantic"
    value = mask_secrets(value)  # upsert 키이기도 하므로 SELECT 이전에 마스킹
    prov = dict(provenance or {})
    if prov.get("query"):
        prov["query"] = mask_secrets(prov["query"])
    prov.setdefault("formed_at", _now())
    conf = _clamp_conf(confidence, 0.6)
    now = _now()
    conn = _connect()
    promoted = False
    try:
        row = conn.execute(
            "SELECT id, confidence, provenance, scent FROM owner_model WHERE facet=? AND value=?",
            (facet, value)).fetchone()
        if row:
            merged = _merge_provenance(row["provenance"], prov)
            new_conf = max(conf, float(row["confidence"] or 0))
            # 빈도 게이트: 서로 다른 포식에서 재확인됐으면 상시-on 냄새로 결정화(territory 와 대칭).
            scent = 1 if row["scent"] else 0
            if not scent and _distinct_observations(merged) >= _OWNER_SCENT_PROMOTE_AT:
                scent = 1
                promoted = True
            conn.execute(
                "UPDATE owner_model SET prior_class=?, confidence=?, provenance=?, "
                "last_seen=?, surface_flag=?, scent=? WHERE id=?",
                (prior_class, new_conf, merged, now, 1 if surface_flag else 0, scent, row["id"]))
            entry_id = row["id"]
            action = "reinforced"
        else:
            # 첫 관측은 항상 임시(scent=0) — 1회 추론이 모든 프롬프트에 영구 주입되지 않게.
            cur = conn.execute(
                "INSERT INTO owner_model (facet, value, prior_class, confidence, provenance, "
                "last_seen, surface_flag, scent) VALUES (?,?,?,?,?,?,?,0)",
                (facet, value, prior_class, conf,
                 json.dumps(prov, ensure_ascii=False), now, 1 if surface_flag else 0))
            entry_id = cur.lastrowid
            action = "noted"
        conn.commit()
        return {"success": True, "action": action, "id": entry_id, "table": "owner_model",
                "promoted_scent": promoted}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# recall — 포식 시작 시 회상 (lazy 부패 체크 동반)
# ---------------------------------------------------------------------------
def _match(text: str, terms: List[str]) -> bool:
    if not terms:
        return True
    t = (text or "").lower()
    return any(term in t for term in terms)


# ---------------------------------------------------------------------------
# 위치 기반 회상 도우미 (2026-09-03, FOLDER_SURVEY_HANDOFF §3) — 낱말 일치 → 위치 위계
# ---------------------------------------------------------------------------
_HANGUL_CH = re.compile(r"[가-힣]")
_CHILD_CAP = 6     # 초점 폴더의 자식 골격 한 줄 상한
_FOCUS_CAP = 3     # 초점으로 삼는 상위 일치 위치 수


def _spaceless(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


# 질의 기능어 — 내용이 아니라 문형(vj-ok: 코드 소유 어휘, 세계의 명사 아님). 단언에 흔히 섞여 잡음이 됐다(실측: "있어"·"어디").
_QUERY_STOP = frozenset((
    "있어", "있나", "있나요", "있는", "있을까", "있지", "없어", "없나", "어디", "어디에", "어디야", "뭐", "뭐가", "뭐야",
    "뭔가", "무엇", "어떤", "어떻게", "어때", "해줘", "해봐", "줘", "좀", "중에", "중에서", "그거", "이거", "그것", "이것",
    "볼까", "찾아", "찾아줘", "찾아봐", "알려줘", "보여줘", "골라줘", "추천", "관련", "대해", "대한", "그리고", "또는",
    "the", "and", "for", "with", "what", "where", "which", "show", "find", "list",
))


def _query_terms(query: Optional[str]):
    """(낱말 목록, 이어붙인 구절 집합).

    구절 = 띄어 쓴 *짧은 한글 토막*(1~2글자) 2~3개를 붙인 것(3글자 이상) — '미 시청 작품'→'미시청작품'.
    띄어쓰기만 다른 같은 낱말을 잇되, 임의 2-gram 겹침(실측 잡음: "이하·하드")은 세지 않는다.
    기능어(_QUERY_STOP)는 낱말·구절 둘 다에서 뺀다."""
    raw = [t for t in (query or "").split() if t]
    kept = [t for t in raw if t.lower().rstrip("?!.,") not in _QUERY_STOP]
    terms = [t.lower() for t in kept if len(t) >= 2]
    short = [t if (len(t) <= 2 and all(_HANGUL_CH.match(c) for c in t)) else None for t in kept]
    phrases = set()
    for i in range(len(short)):
        for w in (2, 3):
            win = short[i:i + w]
            if len(win) == w and all(win):
                ph = "".join(win)
                if len(ph) >= 3:
                    phrases.add(ph)
    return terms, phrases


def _score(text: str, terms: List[str], grams) -> int:
    """일치 점수: 낱말 통째 일치 3점씩(영문은 단어 경계) + 이어붙인 구절 일치 3점씩."""
    if not terms and not grams:
        return 0
    t = (text or "").lower()
    sc = 0
    for term in terms:
        if term.isascii():
            # 영문·숫자 낱말은 단어 경계 — "sf" 가 "transform" 안에서 걸리던 잡음(실측)
            if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", t):
                sc += 3
        elif term in t:
            sc += 3
    if grams:
        st = _spaceless(text)
        sc += 3 * sum(1 for ph in grams if ph in st)  # 구절은 낱말과 같은 무게
    return sc


def _norm_locus(locus: str) -> str:
    loc = (locus or "").rstrip("/")
    return loc[:-2] if loc.endswith("/*") else loc


def _is_path(locus: str) -> bool:
    return bool(locus) and (locus.startswith("/") or locus.startswith("~"))


def _depth(locus: str) -> int:
    return _norm_locus(locus).count("/") if _is_path(locus) else 0


def _is_ancestor(a: str, b: str) -> bool:
    """a 가 b 의 진(strict) 조상 경로인가."""
    a, b = _norm_locus(a), _norm_locus(b)
    return _is_path(a) and _is_path(b) and b.startswith(a + "/")


def _is_child(parent: str, child: str) -> bool:
    return _is_ancestor(parent, child) and _depth(child) == _depth(parent) + 1


def _doc_refresh(body: str, locus: str, own_node: bool = False) -> None:
    try:
        import forage_doc
        forage_doc.refresh_doc_for(body, locus, own_node=own_node)
    except Exception as e:  # 문서 실패가 기억 쓰기를 막지 않는다
        print(f"[포식기억] 문서 재렌더 실패(무시): {e}")


def _doc_lazy_sync(locus: str, body: Optional[str]) -> None:
    try:
        import forage_doc
        forage_doc.lazy_sync(locus, body)
    except Exception as e:
        print(f"[포식기억] 문서 동기화 실패(무시): {e}")


def _stale_of(locus: str, stored_mtime: float) -> str:
    """lazy 부패 판정 — 삭제하지 않고 노출만(판단은 AI). '' | 'stale' | 'missing'.

    freshness(mtime 부패)는 *파일시스템* 개념 — 절대경로 locus(디스크·코드)에만 적용.
    웹 map(예: "arXiv", "NYU Scholars")·추상 locus 는 부패 없음(빈 문자열).
    """
    if not locus or not (locus.startswith("/") or locus.startswith("~")):
        return ""
    p = os.path.expanduser(locus)
    if not os.path.exists(p):
        return "missing"
    try:
        cur = os.stat(p).st_mtime
    except OSError:
        return "missing"
    if stored_mtime and abs(cur - stored_mtime) > _STALE_TOL:
        return "stale"
    return ""


def _fair_by_body(rows: List) -> List:
    """body=None 전 공간 회상의 몸별 라운드로빈 — 부피 큰 한 몸이 limit 을 독점하지
    않게 한다(2026-08-29 실측: code:indiebizOS 166건이 mac 78건을 압도해 '파일' 질의
    상위 20 중 mac 3건만 생존 — 90% 유실). 몸 순서는 최고 신뢰도 항목의 등장 순,
    몸 안 순서는 원래 정렬(confidence DESC, last_seen DESC) 유지. 단일 몸이면 무변."""
    groups: Dict[str, List] = {}
    for r in rows:
        groups.setdefault(r["body"], []).append(r)
    if len(groups) <= 1:
        return list(rows)
    out: List = []
    active = list(groups.values())
    while active:
        nxt = []
        for q in active:
            out.append(q.pop(0))
            if q:
                nxt.append(q)
        active = nxt
    return out


def recall(*, body: Optional[str] = None, query: Optional[str] = None,
           limit: int = 20, filter_owner: bool = True, locus: Optional[str] = None) -> Dict[str, Any]:
    """포식 회상 — 몸별 지도(body 일치, query 필터) + 주인모델.

    body=None 이면 전 공간(모든 몸) — 주입 경로(cognitive_recall)와 같은 축이다.
    이때 map/territory 는 몸별 공정 인터리브(_fair_by_body)로 채워, 항목 수가 많은
    몸이 limit 을 독점하지 않는다(두 축 분리: 하드웨어 감지=게이트, 회상=전 공간 —
    FORAGER_MULTIBODY_DESIGN §1).

    filter_owner=False 면 owner_model 을 query 로 거르지 않고 *전부* 반환 — 주인모델은
    '냄새(scent)'라 상시 노출이 능동 포식을 촉발한다(FORAGER_MULTIBODY_DESIGN §주입).
    map(상세)은 큼·위치-특정이라 항상 query 필터.

    territory(거친 영토 앵커, territory=1)는 query 면제로 상시 노출 — '내 영토가 무엇으로 이뤄졌나'.
    go/skip(파나 건너뛰나)은 저장하지 않고 *지금 의도에 맞춰 런타임 파생*. 단 _TERRITORY_CAP 으로
    상한을 둬 프롬프트가 무한정 늘지 않게 한다(상위 confidence 만 노출). 'dead' 는 장소 속성이
    아니라 (장소×의도) 관계이므로 영토 정체만 띄우고 배제는 AI 가 판단한다.
    """
    terms, grams = _query_terms(query)
    loc = _norm_locus(os.path.expanduser(locus)) if locus else None
    if loc:
        _doc_lazy_sync(loc, body)   # 정본=문서: 사람·AI 가 문서를 고쳤으면 색인이 따라온다(stat 한 번)
        try:
            import forage_doc
            forage_doc.reconcile_lazy(loc, body)   # 실제 폴더가 사라졌으면 이사/삭제 대조(시간당 1회)
        except Exception as e:
            print(f"[포식기억] 대조 실패(무시): {e}")

    def _hit(r) -> int:
        """행 일치 점수 — claim + locus *끝 이름*(전체 경로가 아니라: 루트 이름이 후손 전부를 잡지 않게)."""
        base = os.path.basename(_norm_locus(r["locus"])) if _is_path(r["locus"]) else (r["locus"] or "")
        return _score(r["claim"], terms, grams) + _score(base, terms, grams)

    conn = _connect()
    try:
        if body:
            map_rows = conn.execute(
                "SELECT * FROM forage_map WHERE body=? ORDER BY confidence DESC, last_seen DESC",
                (body,)).fetchall()
        else:
            map_rows = conn.execute(
                "SELECT * FROM forage_map ORDER BY confidence DESC, last_seen DESC").fetchall()
        owner_rows = conn.execute(
            "SELECT * FROM owner_model ORDER BY confidence DESC, last_seen DESC").fetchall()
    finally:
        conn.close()

    # 영토(상시-on, query 면제, 상한) — '내가 가진 것'의 거친 윤곽.
    # 단 질의가 그 영토를 *지명*하면 짧은 냄새 대신 아래 map 에서 상세로 보여준다.
    terr_cands = [r for r in map_rows if r["territory"] and not _hit(r)]
    if not body:
        terr_cands = _fair_by_body(terr_cands)  # 질의 지명 → territory 냄새 생략, map 상세로 넘김
    territory_items: List[Dict[str, Any]] = []
    for r in terr_cands[:_TERRITORY_CAP]:  # 하드 상한 — 무한정 증가 차단
        d = dict(r)
        d["freshness"] = _stale_of(r["locus"], r["locus_mtime"])
        d["short"] = _short(r["claim"])
        territory_items.append(d)

    # map(상세) — 위치 기반 조립(§3): 일치(match) → 초점 위치의 자기 단언(own) → 조상 상속(inherit)
    # → 자식 골격(child, 한 줄). territory 냄새로 이미 뜬 항목만 제외(지명된 영토는 상세로 포함).
    if loc:
        # 폴더 지명(locus) — 그 자리 통째: 냄새(territory·owner)는 끄고 그 폴더 자체가 own 으로 온다.
        # 어휘가 기억의 입구(2026-09-03): 자동 주입이 없으므로 AI 가 폴더를 지명해 묻는 기본 경로.
        territory_items = []
        map_items = _assemble_by_locus(map_rows, _hit, limit, fair=False,
                                       no_query=not (terms or grams), focus_override=[loc])
        owner_items_locus: List[Dict[str, Any]] = []
        doc_path = None
        try:
            import forage_doc
            chain = forage_doc._covering_docs(loc, body)   # 자기 노드 → 조상 (몸을 모르면 디스크 몸들)
            # 같은 깊이면 mac 우선, 더 깊은 뿌리 우선
            best = None
            for p in chain:
                depth = len([x for x in forage_doc._norm(forage_doc.root_of_doc(p)).split("/") if x])
                score = depth * 2 + (1 if os.sep + "mac" + os.sep in p else 0)
                if best is None or score > best[0]:
                    best = (score, p)
            doc_path = best[1] if best else None
            docs_below = []
            if doc_path:
                try:
                    _b = forage_doc._read_marker(doc_path)
                    if _b:
                        docs_below = [os.path.relpath(x, forage_doc.DOC_DIR) for x in forage_doc.docs_below(_b[0], _b[1])]
                except Exception:
                    docs_below = []
        except Exception:
            doc_path = None
        root_missing = False
        try:
            if doc_path:
                _mk = forage_doc._read_marker(doc_path)
                _r = forage_doc._norm(_mk[1]) if _mk else ""
                root_missing = bool(_r and forage_doc._is_path(_r) and forage_doc._mounted(_r) and not os.path.isdir(os.path.expanduser(_r)))
        except Exception:
            root_missing = False
        return {"success": True, "map": map_items, "owner": owner_items_locus,
                "territory": territory_items, "locus": loc, "doc": doc_path, "docs_below": docs_below,
                "root_missing": root_missing,
                "map_count": len(map_items), "owner_count": 0, "territory_count": 0}
    terr_ids = {t["id"] for t in territory_items}
    pool = [r for r in map_rows if r["id"] not in terr_ids]
    map_items = _assemble_by_locus(pool, _hit, limit, fair=not body,
                                   no_query=not (terms or grams))
    # owner — 냄새 모드(filter_owner=False)에서도 *결정화된 것만* 상시 노출.
    #   임시(scent=0, 1회 관측)는 map 처럼 query 가 지명할 때만 나온다 → 정보는 남고 상시 비용만 사라짐.
    owner_items: List[Dict[str, Any]] = []
    scent_shown = 0
    for r in owner_rows:
        matched = (not terms) or _match(r["value"], terms) or _match(r["facet"], terms)
        if filter_owner:
            if not matched:
                continue
        else:
            if not r["scent"]:
                if not (terms and matched):
                    continue          # 임시 항목 — 질의가 지명하지 않으면 침묵
            elif scent_shown >= _OWNER_SCENT_CAP:
                continue              # 결정화 냄새 상한 초과
            else:
                scent_shown += 1
        d = dict(r)
        d["provisional"] = 0 if r["scent"] else 1
        owner_items.append(d)
        if len(owner_items) >= limit:
            break
    return {"success": True, "map": map_items, "owner": owner_items,
            "territory": territory_items,
            "map_count": len(map_items), "owner_count": len(owner_items),
            "territory_count": len(territory_items)}


def _assemble_by_locus(pool: List, hit, limit: int, *, fair: bool, no_query: bool,
                       focus_override: Optional[List[str]] = None):
    """위치 기반 조립. 반환 map_items.

    - match: 질의에 맞는 행(점수 순, 같은 점수면 더 구체적 위치·높은 confidence 먼저) — 전문(全文).
    - own: 상위 일치 위치(초점, 최대 _FOCUS_CAP)의 나머지 단언 — 그 폴더의 전체 프로필.
    - inherit: 초점의 조상 중 generalizes=1 관습·기질 — 하위에 그대로 적용되는 것만(가림 규칙의 반대면).
    - child: 초점의 직계 자식 폴더 한 줄씩(short) — 골격. 자세한 건 그 폴더를 지명해 회상.
    무질의(no_query)는 옛 동작(전부, 몸별 공정 인터리브, limit).
    focus_override=[locus]: 폴더 지명 — 초점을 그 폴더로 고정하고 일치(match)는 그 하위 나무 안에서만,
    자식 골격은 limit 까지(골격 상한 _CHILD_CAP 대신) — "그 자리의 기억 통째".
    """
    if no_query and not focus_override:
        rows = _fair_by_body(pool) if fair else pool
        out = []
        for r in rows[:limit]:
            d = dict(r); d["via"] = "all"; d["freshness"] = _stale_of(r["locus"], r["locus_mtime"]); out.append(d)
        return out
    if focus_override:
        L0 = focus_override[0]
        pool_q = [r for r in pool if _norm_locus(r["locus"]) == L0 or _is_ancestor(L0, r["locus"])]
    else:
        pool_q = pool
    scored = [] if no_query else [(hit(r), r) for r in pool_q]
    matched = sorted([(sc, r) for sc, r in scored if sc > 0],
                     key=lambda x: (-x[0], -_depth(x[1]["locus"]), -x[1]["confidence"]))
    by_locus: Dict[str, List] = {}
    for r in pool:
        by_locus.setdefault(_norm_locus(r["locus"]), []).append(r)
    included: Dict[int, Dict[str, Any]] = {}
    order: List[Dict[str, Any]] = []

    def add(r, via: str, score: int = 0, short: bool = False):
        if r["id"] in included:
            return
        d = dict(r)
        d["via"], d["score"] = via, score
        d["freshness"] = _stale_of(r["locus"], r["locus_mtime"])
        if short:
            d["short"] = _short(r["claim"])
        included[r["id"]] = d
        order.append(d)

    for sc, r in matched:
        add(r, "match", sc)
    focus: List[str] = list(focus_override or [])
    child_cap = limit if focus_override else _CHILD_CAP
    for _sc, r in matched:
        L = _norm_locus(r["locus"])
        if _is_path(L) and L not in focus:
            focus.append(L)
        if len(focus) >= _FOCUS_CAP:
            break
    for L in focus:
        for r in by_locus.get(L, []):
            add(r, "own")
        for P, rows in by_locus.items():
            if _is_ancestor(P, L):
                for r in rows:
                    if r["generalizes"] or r["kind"] == "substrate":
                        add(r, "inherit")
        kids = [(C, rows) for C, rows in by_locus.items() if _is_child(L, C)]
        kids.sort(key=lambda x: -max(r["confidence"] for r in x[1]))
        for C, rows in kids[:child_cap]:
            r = next((x for x in rows if x["kind"] == "identity"), rows[0])
            add(r, "child", short=True)
    return order[:limit]


def territory_loci(body: Optional[str] = None) -> List[str]:
    """territory=1 앵커의 locus 목록(중복 제거, confidence 순) — 집중 관심 폴더 *자동 제안*용.

    focus_map 이 사용자 선언 기본값에 더해 '자주 되돌아온 루트'(territory 승격)를 합쳐
    골격 범위에 넣는다(FORAGER_MULTIBODY_DESIGN territory↔focus). body=None 이면 전 공간.
    """
    conn = _connect()
    try:
        if body:
            rows = conn.execute(
                "SELECT locus FROM forage_map WHERE territory=1 AND body=? "
                "ORDER BY confidence DESC, last_seen DESC", (body,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT locus FROM forage_map WHERE territory=1 "
                "ORDER BY confidence DESC, last_seen DESC").fetchall()
    finally:
        conn.close()
    seen, out = set(), []
    for r in rows:
        loc = r["locus"]
        if loc and loc not in seen:
            seen.add(loc)
            out.append(loc)
    return out


def recall_xml(*, body: Optional[str] = None, query: Optional[str] = None,
               limit: int = 12, filter_owner: bool = True, locus: Optional[str] = None) -> str:
    """<forage_memory> XML — 인지 파이프라인 주입용(해마 <execution_memory> 짝).

    filter_owner=False 면 owner(주인모델)를 query 무관 상시 노출 — 냄새(scent)로 능동 포식 촉발.
    map 이 없고 owner 만 있으면(=냄새만) 짧은 note 로 비용 절약.
    """
    res = recall(body=body, query=query, limit=limit, filter_owner=filter_owner, locus=locus)
    if not res["map"] and not res["owner"] and not res.get("territory"):
        return ""
    if res["map"]:
        note = ('과거 포식에서 누적한 냄새지도입니다. 참고용이며 폐기가능(defeasible) — '
                'prune_reason과 지금 목표가 안 겹치면 그 가지를 재오픈하세요. prior_class=semantic은 '
                'committal하게 prune하지 말 것. freshness=stale/missing이면 디스크가 변했으니 재탐침 판단. '
                'surface=1은 이 라벨이 이질 내용으로 흔들린 표식입니다. '
                'via=match 질의 일치 · own 그 폴더의 나머지 단언 · inherit 상위 폴더에서 물려받은 관습·기질 · '
                'child 하위 폴더 한 줄 골격(자세한 건 그 폴더를 지명해 recall).')
    else:
        note = ('주인(나)에 대해 과거 포식에서 배운 모델입니다. 이 주제로 *내 디스크/코드/웹에 자료가 '
                '있을* 가능성을 떠올리는 단서 — 필요하면 포식(검색)을 시작하세요.')
    lines = [f'<forage_memory note="{note}">']
    if res.get("territory"):
        tnote = ('내 영토(열거가능 공간)의 거친 윤곽 — 무엇이 어디 있나. 지금 의도와 *맞는* 가지를 '
                 '먼저 파고, *안 맞는* 가지는 건너뛰세요(go/skip은 의도에 맞춰 직접 판단 — '
                 '같은 가지도 의도가 다르면 타겟이 됩니다). 어느 영토와도 안 맞으면 내 것엔 없으니 웹/밖으로.')
        lines.append(f'  <territory note="{tnote}">')
        for t in res["territory"]:
            fr = f' freshness="{t["freshness"]}"' if t.get("freshness") else ''
            loc = t["locus"] if t["locus"] != "__substrate__" else "(기질)"
            lines.append(f'    <branch path="{loc}" conf="{t["confidence"]:.2f}"{fr}>{t["short"]}</branch>')
        lines.append('  </territory>')
    if res["map"]:
        lines.append('  <map>')
        for m in res["map"]:
            attrs = (f'kind="{m["kind"]}" prior="{m["prior_class"]}" conf="{m["confidence"]:.2f}"')
            if m.get("freshness"):
                attrs += f' freshness="{m["freshness"]}"'
            if m.get("prune_reason"):
                attrs += f' prune_reason="{m["prune_reason"]}"'
            if m.get("generalizes"):
                attrs += ' generalizes="1"'
            if m.get("surface_flag"):
                attrs += ' surface="1"'
            if m.get("via"):
                attrs += f' via="{m["via"]}"'
            loc = m["locus"] if m["locus"] != "__substrate__" else "(기질)"
            text = m.get("short") if m.get("via") == "child" else m["claim"]
            lines.append(f'    <locus path="{loc}" {attrs}>{text}</locus>')
        lines.append('  </map>')
    if res["owner"]:
        onote = ('provisional="1" 은 *단 한 번의 포식*에서 추론된 미확인 항목입니다 — 참고만 하고 '
                 '주인에 관한 사실로 단정하지 마세요(다른 포식에서 재확인되면 결정화됩니다).')
        lines.append(f'  <owner note="{onote}">')
        for o in res["owner"]:
            sf = ' surface="1"' if o.get("surface_flag") else ''
            pv = ' provisional="1"' if o.get("provisional") else ''
            lines.append(f'    <facet name="{o["facet"]}" prior="{o["prior_class"]}" '
                         f'conf="{o["confidence"]:.2f}"{sf}{pv}>{o["value"]}</facet>')
        lines.append('  </owner>')
    lines.append('</forage_memory>')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# forget / surface — augmentation (사람·surface 패스가 정정)
# ---------------------------------------------------------------------------
def forget(*, entry_id: int, table: str = "forage_map") -> Dict[str, Any]:
    """잘못된/낡은 항목 폐기 (사람이 prune 재오픈·정정)."""
    if table not in ("forage_map", "owner_model"):
        return {"success": False, "error": "table 은 forage_map 또는 owner_model"}
    conn = _connect()
    try:
        where = None
        if table == "forage_map":
            row = conn.execute("SELECT body, locus FROM forage_map WHERE id=?", (int(entry_id),)).fetchone()
            where = (row["body"], row["locus"]) if row else None
        cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (int(entry_id),))
        conn.commit()
    finally:
        conn.close()
    if where:
        _doc_refresh(*where)
    return {"success": cur.rowcount > 0, "deleted": cur.rowcount, "table": table}


def mark_surface(*, entry_id: int, table: str = "forage_map", on: bool = True) -> Dict[str, Any]:
    """surface 카운터-패스 — 이 라벨을 의심하라 표식(이질 내용 발견)."""
    if table not in ("forage_map", "owner_model"):
        return {"success": False, "error": "table 은 forage_map 또는 owner_model"}
    conn = _connect()
    try:
        cur = conn.execute(f"UPDATE {table} SET surface_flag=? WHERE id=?",
                           (1 if on else 0, int(entry_id)))
        conn.commit()
        return {"success": cur.rowcount > 0, "updated": cur.rowcount}
    finally:
        conn.close()


def stats() -> Dict[str, Any]:
    conn = _connect()
    try:
        m = conn.execute("SELECT COUNT(*) FROM forage_map").fetchone()[0]
        o = conn.execute("SELECT COUNT(*) FROM owner_model").fetchone()[0]
        # 결정화된 냄새(상시-on)와 임시(질의 필터)의 비 — 주인모델이 실제로 굳고 있나 관측용
        os_ = conn.execute("SELECT COUNT(*) FROM owner_model WHERE scent=1").fetchone()[0]
        bodies = [r[0] for r in conn.execute("SELECT DISTINCT body FROM forage_map").fetchall()]
        return {"success": True, "forage_map": m, "owner_model": o,
                "owner_scent": os_, "owner_provisional": o - os_, "bodies": bodies}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 정리 패스 기계 헬퍼 (무LLM — 의미 병합 판정은 forage_consolidation 이 위임)
#   심층메모리 정리(memory_consolidation)의 *공간* 짝. 증류(입력)+정리(위생) 대칭.
# ---------------------------------------------------------------------------
def get_meta(key: str) -> Optional[str]:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM forage_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_meta(key: str, value: str) -> None:
    conn = _connect()
    try:
        conn.execute("INSERT INTO forage_meta (key, value) VALUES (?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        conn.commit()
    finally:
        conn.close()


def list_bodies() -> List[str]:
    conn = _connect()
    try:
        return [r[0] for r in conn.execute("SELECT DISTINCT body FROM forage_map").fetchall()]
    finally:
        conn.close()


def merge_candidates(body: str) -> Dict[str, Any]:
    """정리 대상 후보 — surface 표식 항목은 *제외*(반대힘 보호). map=이 몸, owner=전역."""
    conn = _connect()
    try:
        mr = conn.execute(
            "SELECT id, locus, kind, claim, prior_class, confidence FROM forage_map "
            "WHERE body=? AND surface_flag=0 ORDER BY kind, locus", (body,)).fetchall()
        orow = conn.execute(
            "SELECT id, facet, value, prior_class, confidence FROM owner_model "
            "WHERE surface_flag=0 ORDER BY facet").fetchall()
        return {"map": [dict(r) for r in mr], "owner": [dict(r) for r in orow]}
    finally:
        conn.close()


def _union_provenance(conn: sqlite3.Connection, table: str, ids: List[int]) -> str:
    """병합 대상들의 provenance 를 합집합 — reinforced_by 누적·observed 합침(복리 보존)."""
    base: Dict[str, Any] = {"reinforced_by": [], "observed": []}
    q = f"SELECT provenance FROM {table} WHERE id IN ({','.join('?' * len(ids))})"
    for (pj,) in conn.execute(q, ids).fetchall():
        try:
            p = json.loads(pj) if pj else {}
        except (ValueError, TypeError):
            continue
        if not isinstance(p, dict):
            continue
        for k in ("forage_id", "query", "formed_at"):
            if k not in base and p.get(k) is not None:
                base[k] = p[k]
        rb = p.get("reinforced_by")
        if isinstance(rb, list):
            base["reinforced_by"].extend(rb)
        obs = p.get("observed")
        if isinstance(obs, list):
            base["observed"].extend(obs)
    if not base["observed"]:
        base.pop("observed")
    return json.dumps(base, ensure_ascii=False)


# 병합 시 갱신 허용 컬럼 화이트리스트 (SQL injection 가드).
_MERGE_COLS = {
    "forage_map": ("claim", "prior_class", "confidence", "prune_reason"),
    "owner_model": ("value", "prior_class", "confidence"),
}


def merge_entries(*, table: str, keep_id: int, drop_ids: List[int],
                  fields: Dict[str, Any]) -> Dict[str, Any]:
    """근접중복 클러스터 병합 — keep 을 정규 병합본으로 덮고 provenance 합집합, drop 삭제."""
    if table not in _MERGE_COLS:
        return {"success": False, "error": "bad table"}
    drops = [int(d) for d in drop_ids if int(d) != int(keep_id)]
    if not drops:
        return {"success": False, "error": "no drops"}
    cols = [c for c in fields if c in _MERGE_COLS[table]]
    conn = _connect()
    try:
        # surface 표식이 drop 에 섞이면 병합 거부(반대힘 보호)
        marks = conn.execute(
            f"SELECT id FROM {table} WHERE id IN ({','.join('?'*len(drops+[keep_id]))}) "
            f"AND surface_flag=1", drops + [int(keep_id)]).fetchall()
        if marks:
            return {"success": False, "error": "surface 보호 — 병합 거부"}
        prov = _union_provenance(conn, table, drops + [int(keep_id)])
        sets = ", ".join(f"{c}=?" for c in cols) + (", " if cols else "") + "provenance=?, last_seen=?"
        params = [fields[c] for c in cols] + [prov, _now(), int(keep_id)]
        conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", params)
        conn.execute(f"DELETE FROM {table} WHERE id IN ({','.join('?'*len(drops))})", drops)
        # 병합으로 provenance 가 합쳐지면 관측 수도 합쳐진다 — 서로 다른 포식에서 같은 말을 달리
        # 적었던 것이므로 냄새 결정화 조건을 다시 본다(scent ⟺ 관측 2회 이상 불변식 유지).
        if table == "owner_model" and _distinct_observations(prov) >= _OWNER_SCENT_PROMOTE_AT:
            conn.execute("UPDATE owner_model SET scent=1 WHERE id=?", (int(keep_id),))
        conn.commit()
        return {"success": True, "kept": int(keep_id), "dropped": len(drops)}
    finally:
        conn.close()


def prune_cap(*, body: str, cap_map: int = 150, cap_owner: int = 60) -> Dict[str, int]:
    """상한 초과 시 LRU 가지치기 — surface 표식 *보호*, 저확신·오래된 것부터."""
    conn = _connect()
    pruned = {"map": 0, "owner": 0}
    try:
        n = conn.execute("SELECT COUNT(*) FROM forage_map WHERE body=?", (body,)).fetchone()[0]
        if n > cap_map:
            cur = conn.execute(
                "DELETE FROM forage_map WHERE id IN (SELECT id FROM forage_map "
                "WHERE body=? AND surface_flag=0 ORDER BY confidence ASC, last_seen ASC LIMIT ?)",
                (body, n - cap_map))
            pruned["map"] = cur.rowcount
        no = conn.execute("SELECT COUNT(*) FROM owner_model").fetchone()[0]
        if no > cap_owner:
            cur = conn.execute(
                "DELETE FROM owner_model WHERE id IN (SELECT id FROM owner_model "
                "WHERE surface_flag=0 ORDER BY confidence ASC, last_seen ASC LIMIT ?)",
                (no - cap_owner,))
            pruned["owner"] = cur.rowcount
        conn.commit()
        return pruned
    finally:
        conn.close()
