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
import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "forage_memory.db")

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
    UNIQUE(body, locus, kind)
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
    conn = sqlite3.connect(os.path.abspath(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # 마이그레이션: 기존 DB 에 territory 컬럼 없으면 추가
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(forage_map)")}
    if "territory" not in cols:
        conn.execute("ALTER TABLE forage_map ADD COLUMN territory INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    return conn


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
    prov = dict(provenance or {})
    prov.setdefault("formed_at", _now())
    conf = _clamp_conf(confidence, 0.7)
    mtime = _locus_mtime(locus)
    now = _now()
    promoted = False
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, confidence, provenance, territory FROM forage_map WHERE body=? AND locus=? AND kind=?",
            (body, locus, kind)).fetchone()
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
        return {"success": True, "action": action, "id": entry_id, "table": "forage_map",
                "promoted_territory": promoted}
    finally:
        conn.close()


def note_owner(*, facet: str, value: str, prior_class: str = "semantic",
               confidence: float = 0.6, provenance: Optional[Dict[str, Any]] = None,
               surface_flag: bool = False) -> Dict[str, Any]:
    """owner_model 한 항목 upsert (키=facet+value). 재note 시 강화."""
    if facet not in _OWNER_FACETS:
        return {"success": False, "error": f"facet 은 {_OWNER_FACETS} 중 하나여야 합니다 (받음: {facet})"}
    if prior_class not in _PRIOR_CLASSES:
        prior_class = "semantic"
    prov = dict(provenance or {})
    prov.setdefault("formed_at", _now())
    conf = _clamp_conf(confidence, 0.6)
    now = _now()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, confidence, provenance FROM owner_model WHERE facet=? AND value=?",
            (facet, value)).fetchone()
        if row:
            merged = _merge_provenance(row["provenance"], prov)
            new_conf = max(conf, float(row["confidence"] or 0))
            conn.execute(
                "UPDATE owner_model SET prior_class=?, confidence=?, provenance=?, "
                "last_seen=?, surface_flag=? WHERE id=?",
                (prior_class, new_conf, merged, now, 1 if surface_flag else 0, row["id"]))
            entry_id = row["id"]
            action = "reinforced"
        else:
            cur = conn.execute(
                "INSERT INTO owner_model (facet, value, prior_class, confidence, provenance, "
                "last_seen, surface_flag) VALUES (?,?,?,?,?,?,?)",
                (facet, value, prior_class, conf,
                 json.dumps(prov, ensure_ascii=False), now, 1 if surface_flag else 0))
            entry_id = cur.lastrowid
            action = "noted"
        conn.commit()
        return {"success": True, "action": action, "id": entry_id, "table": "owner_model"}
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


def recall(*, body: Optional[str] = None, query: Optional[str] = None,
           limit: int = 20, filter_owner: bool = True) -> Dict[str, Any]:
    """포식 회상 — 몸별 지도(body 일치, query 필터) + 주인모델.

    filter_owner=False 면 owner_model 을 query 로 거르지 않고 *전부* 반환 — 주인모델은
    '냄새(scent)'라 상시 노출이 능동 포식을 촉발한다(FORAGER_MULTIBODY_DESIGN §주입).
    map(상세)은 큼·위치-특정이라 항상 query 필터.

    territory(거친 영토 앵커, territory=1)는 query 면제로 상시 노출 — '내 영토가 무엇으로 이뤄졌나'.
    go/skip(파나 건너뛰나)은 저장하지 않고 *지금 의도에 맞춰 런타임 파생*. 단 _TERRITORY_CAP 으로
    상한을 둬 프롬프트가 무한정 늘지 않게 한다(상위 confidence 만 노출). 'dead' 는 장소 속성이
    아니라 (장소×의도) 관계이므로 영토 정체만 띄우고 배제는 AI 가 판단한다.
    """
    terms = [t.lower() for t in (query or "").split() if len(t) >= 2]
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
    territory_items: List[Dict[str, Any]] = []
    for r in map_rows:
        if not r["territory"]:
            continue
        if terms and (_match(r["claim"], terms) or _match(r["locus"], terms)):
            continue  # 질의 지명 → territory 냄새 생략, map 상세로 넘김
        d = dict(r)
        d["freshness"] = _stale_of(r["locus"], r["locus_mtime"])
        d["short"] = _short(r["claim"])
        territory_items.append(d)
        if len(territory_items) >= _TERRITORY_CAP:
            break  # 하드 상한 — 무한정 증가 차단

    # map(상세, query 필터) — territory 냄새로 이미 뜬 항목만 제외(지명된 영토는 상세로 포함)
    terr_ids = {t["id"] for t in territory_items}
    map_items: List[Dict[str, Any]] = []
    for r in map_rows:
        if r["id"] in terr_ids:
            continue
        if terms and not (_match(r["claim"], terms) or _match(r["locus"], terms)):
            continue
        d = dict(r)
        d["freshness"] = _stale_of(r["locus"], r["locus_mtime"])
        map_items.append(d)
        if len(map_items) >= limit:
            break
    owner_items: List[Dict[str, Any]] = []
    for r in owner_rows:
        if filter_owner and terms and not (_match(r["value"], terms) or _match(r["facet"], terms)):
            continue
        owner_items.append(dict(r))
        if len(owner_items) >= limit:
            break
    return {"success": True, "map": map_items, "owner": owner_items,
            "territory": territory_items,
            "map_count": len(map_items), "owner_count": len(owner_items),
            "territory_count": len(territory_items)}


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
               limit: int = 12, filter_owner: bool = True) -> str:
    """<forage_memory> XML — 인지 파이프라인 주입용(해마 <execution_memory> 짝).

    filter_owner=False 면 owner(주인모델)를 query 무관 상시 노출 — 냄새(scent)로 능동 포식 촉발.
    map 이 없고 owner 만 있으면(=냄새만) 짧은 note 로 비용 절약.
    """
    res = recall(body=body, query=query, limit=limit, filter_owner=filter_owner)
    if not res["map"] and not res["owner"] and not res.get("territory"):
        return ""
    if res["map"]:
        note = ('과거 포식에서 누적한 냄새지도입니다. 참고용이며 폐기가능(defeasible) — '
                'prune_reason과 지금 목표가 안 겹치면 그 가지를 재오픈하세요. prior_class=semantic은 '
                'committal하게 prune하지 말 것. freshness=stale/missing이면 디스크가 변했으니 재탐침 판단. '
                'surface=1은 이 라벨이 이질 내용으로 흔들린 표식입니다.')
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
            loc = m["locus"] if m["locus"] != "__substrate__" else "(기질)"
            lines.append(f'    <locus path="{loc}" {attrs}>{m["claim"]}</locus>')
        lines.append('  </map>')
    if res["owner"]:
        lines.append('  <owner>')
        for o in res["owner"]:
            sf = ' surface="1"' if o.get("surface_flag") else ''
            lines.append(f'    <facet name="{o["facet"]}" prior="{o["prior_class"]}" '
                         f'conf="{o["confidence"]:.2f}"{sf}>{o["value"]}</facet>')
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
        cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (int(entry_id),))
        conn.commit()
        return {"success": cur.rowcount > 0, "deleted": cur.rowcount, "table": table}
    finally:
        conn.close()


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
        bodies = [r[0] for r in conn.execute("SELECT DISTINCT body FROM forage_map").fetchall()]
        return {"success": True, "forage_map": m, "owner_model": o, "bodies": bodies}
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
