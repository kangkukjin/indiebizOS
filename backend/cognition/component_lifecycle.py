"""component_lifecycle.py — 구성요소 수준의 죽음 (세포 사멸, 2026-09-02)

## 왜 있나

세대 교체가 없는 한 개체(indiebizOS)는 게놈이 정리될 기회가 없다. 그래서 죽음을
**구성요소 수준**으로 들여온다 — 가이드·워크플로우·스크립트·낱말이 생존 신호 없이
쌓이면 사람이 손으로 다이어트해야 했다(2026-08-17 81KB · 09-02 가이드 셋 67→21·62→30·
79→34KB). 죽음의 **집행기**(retired_contracts·코퍼스 이관·좀비 청소)는 있었고
**신호와 방아쇠**가 없었다. 여기가 그 자리다. 정본: docs/COMPONENT_APOPTOSIS_HANDOFF.md.

## 원리 (생물학 → 규율)

- **기본값 반전**: 생존 신호가 없으면 죽는다(지금까지는 삭제 신호가 없으면 남았다).
- **영양 지지(trophic support)**: 뉴런은 표적이 영양인자를 주는 동안 산다. 항목은
  ⓐ 쓸모 있게 실행/주입됐거나 ⓑ **살아 있는 상위 구조가 참조**하면 산다. ⓑ 가
  vocab_crystallization 이 두려워한 오살("사용 0 은 신호가 아니다 — 계절·유지보수 어휘")의
  답이다: 유지보수 어휘는 가이드·프롬프트·트리거가 참조하므로 산다. **참조도 실행도 없는
  것만 고아**다. 후보끼리의 상호 참조는 지지가 아니다(고아 섬).
- **계수 ≠ 쓸모**: 실행 신호 = success=1 ∧ source='usage' ∧ channel≠self_check ∧
  ¬(shape='items' ∧ n_items=0). sense:search_local 은 계수 19 에 결과 0 이었다(2026-08-15).
- **신생 유예**: 처음 관측된 날부터 grace_days 는 무조건 산다.
- **단계적 죽음**: alive → candidate(보이는 표식) → retired. candidate 는 숨김이 아니다 —
  어휘를 AI 시야에서 빼는 단계는 두지 않는다(노드 스코핑 기각 판정). candidate 중 신호가
  오면 alive 로 복귀하고 **부활이 기록**된다(계절성의 학습 = 정책 재조정 근거).
- **결정권 = 가역성**(사용자 승인 2026-09-02): git 이 추적하는 층(가이드·워크플로우·
  스크립트)은 기계가 retired 까지 집행하고 커밋 라벨로 사후 검토한다(되살리기=파일 이동
  한 번). **어휘 은퇴는 항상 판정 큐** — 낱말을 지우는 것은 언어 개정이다. 기계는 방아쇠와
  증거(참조 0·쓸모 실행 0·마지막 사용)만 실어 준다.

## 하지 않는 것

자동 승격 없음(결정화 판단=사용자) · 어휘 숨김 없음 · LLM 이 생사를 판단하지 않음
(생사=구조+신호, LLM 은 guide_downscale 의 압축 작업만) · system_docs 산문·커스텀 React
계기·해마 코퍼스는 대상 밖(각자 다른 장치) · 문서(system_docs)는 참조 지지로 세지 않음
(문서는 몸을 기술하지 실행하지 않는다 — 가이드·프롬프트·트리거는 실행자의 입력이라 센다).

카덴스: 일일(무LLM). run_maintenance_bundle 이 부른다. 산출: data/lifecycle_flags.json ·
data/lifecycle_state.json · self_checks(__telemetry__:component_lifecycle) · 전이 시 알림 1건.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data"
POLICY_PATH = DATA / "lifecycle_policy.yaml"
STATE_PATH = DATA / "lifecycle_state.json"
FLAGS_PATH = DATA / "lifecycle_flags.json"
VERDICTS_PATH = BASE / "outputs" / "imagination_training" / "PENDING_VERDICTS.md"
GUIDES_DIR = DATA / "guides"
GUIDE_INDEX_PATH = DATA / "guide_db.json"
WORKFLOWS_DIR = DATA / "workflows"
SCRIPTS_DIR = DATA / "scripts"
SCRIPTS_STATE_PATH = DATA / "scripts.json"
NODES_PATH = DATA / "ibl_nodes.yaml"
PULSE_DB_PATH = DATA / "world_pulse.db"
GUIDE_USAGE_DB_PATH = DATA / "guide_usage.db"
USAGE_DB_PATH = DATA / "ibl_usage.db"
TRIGGERS_PATH = DATA / "event_triggers.json"
CALENDAR_PATH = DATA / "calendar_events.json"
PROMPT_DIRS = (DATA / "common_prompts", DATA / "system_ai_prompts")
RETIRED_DIRNAME = "_retired"

DEFAULT_POLICY = {
    "grace_days": 30,
    "candidate_after_days": 60,
    "retire_after_days": 90,
    "cadence_hours": 24,
    "guide_budget_bytes": 36000,
    "downscale_per_run": 2,
    "section_unused_min_turns": 3,
}

ACTION_RE = re.compile(r"\[([a-z_][a-z0-9_-]*):([a-z_][a-z0-9_-]*)\]")
SCRIPT_ID_RE = re.compile(r"\[self:script\]\s*\{[^}]*?\bid\s*:\s*[\"']([^\"']+)[\"']")
WORKFLOW_ID_RE = re.compile(r"\bworkflow_id\s*:\s*[\"']([^\"']+)[\"']")
GUIDE_MARK_RE = re.compile(r"^<!-- lifecycle: candidate since (\d{4}-\d{2}-\d{2})[^\n]*-->\n?", re.M)

# 결정권 표 — 가역(git 추적) 층은 기계 집행, 어휘는 판정 큐.
RETIRE_BY_MACHINE = {"guide", "workflow", "script"}
RETIRE_BY_VERDICT = {"action"}

# 시험이 끼워 넣는 커밋 함수 자리 — 라이브에선 _commit_via_body.
COMMIT_FN = None


# ---------------------------------------------------------------- 정책·상태

def load_policy() -> Dict:
    pol = dict(DEFAULT_POLICY)
    try:
        import yaml
        raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}
        for k, v in raw.items():
            if k in pol and isinstance(v, (int, float)):
                pol[k] = int(v)
    except Exception:
        pass
    return pol


def _load_state() -> Dict:
    try:
        st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(st, dict):
            st.setdefault("first_seen", {})
            st.setdefault("candidates", {})
            st.setdefault("revivals", [])
            st.setdefault("retired", [])
            st.setdefault("verdict_queued", {})
            return st
    except Exception:
        pass
    return {"first_seen": {}, "candidates": {}, "revivals": [], "retired": [],
            "verdict_queued": {}, "last_run": None}


def _save_state(st: Dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[Lifecycle] 상태 저장 실패 (무시): {e}")


def _days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


# ---------------------------------------------------------------- 인벤토리

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_yaml(path: Path):
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def collect_inventory() -> Dict[str, Dict]:
    """죽을 수 있는 것들의 목록 {key: meta}. key = kind:name."""
    inv: Dict[str, Dict] = {}
    nodes = _load_yaml(NODES_PATH) or {}
    nodes = nodes.get("nodes", nodes) if isinstance(nodes, dict) else {}
    for n, v in nodes.items():
        if not isinstance(v, dict):
            continue
        for a, cfg in (v.get("actions") or {}).items():
            inv[f"action:{n}:{a}"] = {"kind": "action", "node": n, "action": a,
                                      "name": f"[{n}:{a}]"}
    if GUIDES_DIR.is_dir():
        for p in sorted(GUIDES_DIR.glob("*.md")):
            inv[f"guide:{p.name}"] = {"kind": "guide", "name": p.name, "path": p}
    if WORKFLOWS_DIR.is_dir():
        for p in sorted(WORKFLOWS_DIR.glob("*.yaml")):
            inv[f"workflow:{p.stem}"] = {"kind": "workflow", "name": p.stem, "path": p}
    reg = _load_yaml(SCRIPTS_DIR / "registry.yaml")
    if isinstance(reg, dict):
        for sid, ent in reg.items():
            if isinstance(ent, dict):
                inv[f"script:{sid}"] = {"kind": "script", "name": sid,
                                        "path": SCRIPTS_DIR / str(ent.get("file") or f"{sid}.py")}
    return inv


def _refs_in_text(text: str, inv: Dict[str, Dict]) -> Set[str]:
    """텍스트가 참조하는 인벤토리 key 집합 — 액션·스크립트 id·워크플로우 id·가이드 파일명."""
    out: Set[str] = set()
    if not text:
        return out
    for n, a in ACTION_RE.findall(text):
        k = f"action:{n}:{a}"
        if k in inv:
            out.add(k)
    for sid in SCRIPT_ID_RE.findall(text):
        k = f"script:{sid}"
        if k in inv:
            out.add(k)
    for wid in WORKFLOW_ID_RE.findall(text):
        k = f"workflow:{wid}"
        if k in inv:
            out.add(k)
    for k, m in inv.items():
        if m["kind"] == "guide" and m["name"] in text:
            out.add(k)
    return out


def collect_references(inv: Dict[str, Dict]) -> Dict[str, Set[str]]:
    """{피참조 key: {참조자 key}}. 참조자 = 인벤토리 항목(가이드·워크플로우) 또는 의사 참조자
    (vocab:·prompt:·trigger:·calendar:·corpus: — 항상 살아 있는 상위 구조)."""
    refs: Dict[str, Set[str]] = {k: set() for k in inv}

    def _add(target: str, referrer: str):
        if target in refs and target != referrer:
            refs[target].add(referrer)

    # 가이드 → (액션·스크립트·워크플로우·다른 가이드)
    for k, m in inv.items():
        if m["kind"] in ("guide", "workflow"):
            text = _read(m["path"])
            for t in _refs_in_text(text, inv):
                _add(t, k)

    # 어휘 카탈로그의 guides: 목록 → 가이드 (낱말이 교재를 지목한다)
    nodes = _load_yaml(NODES_PATH) or {}
    nodes = nodes.get("nodes", nodes) if isinstance(nodes, dict) else {}
    for n, v in nodes.items():
        if not isinstance(v, dict):
            continue
        for g in (v.get("guides") or []):
            _add(f"guide:{Path(str(g)).name}", f"vocab:{n}")
        for a, cfg in (v.get("actions") or {}).items():
            if isinstance(cfg, dict):
                # 다른 몸에서만 도는 낱말(runs_on: phone_only)의 실행은 이 몸의 action_health 에
                # 안 남는다 — 관측 불능을 '무신호'로 읽으면 오살이다. 그 몸이 지지자다.
                if str(cfg.get("runs_on") or "") == "phone_only":
                    _add(f"action:{n}:{a}", "body:phone")
                for g in (cfg.get("guides") or []):
                    _add(f"guide:{Path(str(g)).name}", f"vocab:{n}:{a}")
                # app: 블록·desc 가 스크립트/워크플로우를 지목하는 경우
                for t in _refs_in_text(json.dumps(cfg, ensure_ascii=False, default=str), inv):
                    if t != f"action:{n}:{a}":
                        _add(t, f"vocab:{n}:{a}")

    # 프롬프트 저술물 → 액션 등 (실행자의 입력이므로 지지)
    for d in PROMPT_DIRS:
        if d.is_dir():
            for p in d.rglob("*.md"):
                for t in _refs_in_text(_read(p), inv):
                    _add(t, f"prompt:{p.name}")

    # 트리거(켜진 것만) → 파이프라인 텍스트
    trig = None
    try:
        trig = json.loads(_read(TRIGGERS_PATH) or "{}")
    except Exception:
        trig = None
    for t in ((trig or {}).get("triggers") or []):
        if isinstance(t, dict) and t.get("enabled", True):
            for x in _refs_in_text(json.dumps(t, ensure_ascii=False), inv):
                _add(x, f"trigger:{t.get('id') or t.get('name')}")

    # 일정(켜진 것만)
    cal = None
    try:
        cal = json.loads(_read(CALENDAR_PATH) or "{}")
    except Exception:
        cal = None
    for e in ((cal or {}).get("events") or []):
        if isinstance(e, dict) and e.get("enabled", True):
            for x in _refs_in_text(json.dumps(e, ensure_ascii=False), inv):
                _add(x, f"calendar:{e.get('id')}")

    # 해마 — 경험에서 증류된 용례만(synthetic 시딩은 실사용이 아니다) → 액션
    try:
        if USAGE_DB_PATH.exists():
            conn = sqlite3.connect(str(USAGE_DB_PATH), timeout=5)
            rows = conn.execute(
                "SELECT ibl_code FROM ibl_examples WHERE source != 'synthetic'").fetchall()
            conn.close()
            for (code,) in rows:
                for n, a in ACTION_RE.findall(code or ""):
                    _add(f"action:{n}:{a}", "corpus:experience")
    except Exception:
        pass
    return refs


# ---------------------------------------------------------------- 실행 신호

_NO_COLUMN = object()   # 구 스키마(컬럼 없음)와 '행 없음'을 가른다 — 폴백은 앞의 경우에만


def _one(conn, sql: str, args: tuple):
    try:
        r = conn.execute(sql, args).fetchone()
        return r[0] if r and r[0] else None
    except sqlite3.OperationalError:
        return _NO_COLUMN


def last_signal(meta: Dict) -> Optional[str]:
    """항목의 마지막 '쓸모 있는' 실행/주입 날짜(ISO date) — 없으면 None."""
    kind = meta["kind"]
    try:
        if kind == "action":
            if not PULSE_DB_PATH.exists():
                return None
            conn = sqlite3.connect(str(PULSE_DB_PATH), timeout=5)
            base = ("SELECT MAX(timestamp) FROM action_health WHERE node=? AND action=? "
                    "AND success=1 AND source='usage' AND (channel IS NULL OR channel != 'self_check')")
            ts = _one(conn, base + " AND NOT (shape='items' AND n_items=0)",
                      (meta["node"], meta["action"]))
            if ts is _NO_COLUMN:
                # n_items 컬럼이 없는 구 스키마 — 빈 items 판별 없이 폴백
                ts = _one(conn, base, (meta["node"], meta["action"]))
            conn.close()
            return ts[:10] if isinstance(ts, str) else None
        if kind == "guide":
            if not GUIDE_USAGE_DB_PATH.exists():
                return None
            conn = sqlite3.connect(str(GUIDE_USAGE_DB_PATH), timeout=5)
            ts = _one(conn, "SELECT MAX(used_on) FROM guide_use WHERE guide=? AND origin='agent'",
                      (meta["name"],))
            conn.close()
            return ts[:10] if isinstance(ts, str) else None
        if kind == "workflow":
            if not PULSE_DB_PATH.exists():
                return None
            conn = sqlite3.connect(str(PULSE_DB_PATH), timeout=5)
            ts = _one(conn, "SELECT MAX(timestamp) FROM workflow_run WHERE workflow_id=? "
                            "AND success=1 AND source='usage'", (meta["name"],))
            conn.close()
            return ts[:10] if isinstance(ts, str) else None
        if kind == "script":
            st = json.loads(_read(SCRIPTS_STATE_PATH) or "{}")
            lr = ((st.get(meta["name"]) or {}).get("last_run") or {})
            if lr.get("ok") and lr.get("at"):
                return str(lr["at"])[:10]
            return None
    except Exception:
        return None
    return None


# ---------------------------------------------------------------- 표식 (보이는 candidate)

def _mark_guide(path: Path, since: str, evidence: str) -> None:
    text = _read(path)
    text = GUIDE_MARK_RE.sub("", text, count=1)
    mark = (f"<!-- lifecycle: candidate since {since} — {evidence}. "
            f"쓰이면(주입·참조) 자동 복귀, {load_policy()['retire_after_days']}일 더 무신호면 "
            f"_retired/ 로 이동(되살리기=파일 이동 한 번) -->\n")
    path.write_text(mark + text, encoding="utf-8")


def _unmark_guide(path: Path) -> None:
    text = _read(path)
    new = GUIDE_MARK_RE.sub("", text, count=1)
    if new != text:
        path.write_text(new, encoding="utf-8")


def _set_yaml_key(path: Path, key: str, value, script_id: Optional[str] = None) -> None:
    """워크플로우 yaml(문서 루트) 또는 스크립트 registry.yaml(항목) 에 lifecycle 필드를 넣거나 뺀다."""
    import yaml
    data = _load_yaml(path)
    if not isinstance(data, dict):
        return
    target = data
    if script_id is not None:
        target = data.get(script_id)
        if not isinstance(target, dict):
            return
    if value is None:
        if key not in target:
            return
        target.pop(key, None)
    else:
        target[key] = value
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
                    encoding="utf-8")


def _mark(meta: Dict, since: str, evidence: str) -> None:
    kind = meta["kind"]
    if kind == "guide":
        _mark_guide(meta["path"], since, evidence)
    elif kind == "workflow":
        _set_yaml_key(meta["path"], "lifecycle", {"candidate_since": since, "evidence": evidence})
    elif kind == "script":
        _set_yaml_key(SCRIPTS_DIR / "registry.yaml", "lifecycle",
                      {"candidate_since": since, "evidence": evidence}, script_id=meta["name"])
    # action: 상태·깃발 파일에만(카탈로그는 빌드 산출물 — 직접 편집 금지)


def _unmark(meta: Dict) -> None:
    kind = meta["kind"]
    if kind == "guide":
        _unmark_guide(meta["path"])
    elif kind == "workflow":
        _set_yaml_key(meta["path"], "lifecycle", None)
    elif kind == "script":
        _set_yaml_key(SCRIPTS_DIR / "registry.yaml", "lifecycle", None, script_id=meta["name"])


# ---------------------------------------------------------------- 은퇴 집행 (가역 층)

def _retired_dir(base: Path) -> Path:
    d = base / RETIRED_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _retire_guide(meta: Dict) -> List[str]:
    """가이드 → data/guides/_retired/ + guide_db.json 항목 제거. 반환 = 커밋할 경로들."""
    src: Path = meta["path"]
    dst = _retired_dir(GUIDES_DIR) / src.name
    _unmark_guide(src)
    shutil.move(str(src), str(dst))
    changed = [str(src.relative_to(BASE)), str(dst.relative_to(BASE))]
    try:
        db = json.loads(_read(GUIDE_INDEX_PATH) or "{}")
        before = len(db.get("guides", []))
        db["guides"] = [g for g in db.get("guides", [])
                        if Path(str(g.get("file") or "")).name != src.name]
        if len(db["guides"]) != before:
            GUIDE_INDEX_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
            changed.append(str(GUIDE_INDEX_PATH.relative_to(BASE)))
    except Exception as e:
        logger.warning(f"[Lifecycle] guide_db 항목 제거 실패 (무시): {e}")
    return changed


def _retire_workflow(meta: Dict) -> List[str]:
    src: Path = meta["path"]
    _set_yaml_key(src, "lifecycle", None)
    dst = _retired_dir(WORKFLOWS_DIR) / src.name
    shutil.move(str(src), str(dst))
    return [str(src.relative_to(BASE)), str(dst.relative_to(BASE))]


def _retire_script(meta: Dict) -> List[str]:
    """스크립트 .py → _retired/ + registry 항목을 _retired/registry.yaml 로 이관(되살리기용)."""
    import yaml
    reg_path = SCRIPTS_DIR / "registry.yaml"
    reg = _load_yaml(reg_path) or {}
    ent = reg.pop(meta["name"], None)
    changed: List[str] = []
    if ent is not None:
        if isinstance(ent, dict):
            ent.pop("lifecycle", None)
        reg_path.write_text(yaml.safe_dump(reg, allow_unicode=True, sort_keys=False, width=100),
                            encoding="utf-8")
        changed.append(str(reg_path.relative_to(BASE)))
        rdir = _retired_dir(SCRIPTS_DIR)
        rreg_path = rdir / "registry.yaml"
        rreg = _load_yaml(rreg_path) or {}
        rreg[meta["name"]] = ent
        rreg_path.write_text(yaml.safe_dump(rreg, allow_unicode=True, sort_keys=False, width=100),
                             encoding="utf-8")
        changed.append(str(rreg_path.relative_to(BASE)))
    src: Path = meta["path"]
    if src.exists():
        dst = _retired_dir(SCRIPTS_DIR) / src.name
        shutil.move(str(src), str(dst))
        changed += [str(src.relative_to(BASE)), str(dst.relative_to(BASE))]
    return changed


def _commit_via_body(paths: List[str], message: str) -> bool:
    """[self:body]{op:commit} 로 각인 — 임시 인덱스·pathspec·원격 무지·저자=클론 config.
    git 이 없는 몸(설치본)이나 저자 미설정이면 False 를 돌려주고 변경은 작업트리에 남는다(가역)."""
    try:
        from ibl_engine import execute_ibl
        r = execute_ibl({"node": "self", "action": "body",
                         "params": {"op": "commit", "paths": paths, "message": message}},
                        str(BASE), agent_id="__lifecycle__")
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except Exception:
                return False
        return bool(isinstance(r, dict) and r.get("success"))
    except Exception as e:
        logger.warning(f"[Lifecycle] 각인 실패 (변경은 작업트리에 남음): {e}")
        return False


def _commit(paths: List[str], message: str) -> bool:
    fn = COMMIT_FN or _commit_via_body
    return fn(paths, message)


# ---------------------------------------------------------------- 판정 큐 (비가역 층·어휘)

def queue_verdict(key: str, text: str) -> bool:
    """PENDING_VERDICTS.md '미결' 절에 한 줄 적립. key 가 이미 있으면(미결·완료 어느 쪽이든) 중복 안 함.
    상상훈련 마라톤이 같은 큐를 읽어 미결 ≥5 면 사용자를 부른다 — '보고만' 이 영구 방치로 새는 것을 막는다."""
    try:
        path = VERDICTS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        cur = _read(path)
        if not cur:
            cur = ("# 판정 큐 — 사용자에게 미루는 결정\n\n## 미결\n\n(없음)\n\n"
                   "## 판정 완료 (사용자가 옮김)\n")
        if f"`{key}`" in cur:
            return False
        line = f"- [ ] {date.today().isoformat()} lifecycle — {text} (`{key}`)\n"
        head, sep, rest = cur.partition("## 미결")
        if not sep:
            cur = cur.rstrip("\n") + "\n\n## 미결\n\n" + line
        else:
            body, sep2, tail = rest.partition("\n## ")
            body = body.replace("(없음)\n", "").rstrip("\n") + "\n" + line + "\n"
            cur = head + sep + body + (sep2 + tail if sep2 else "")
        path.write_text(cur, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"[Lifecycle] 판정 큐 적립 실패 (무시): {e}")
        return False


# ---------------------------------------------------------------- 전이

def compute_transitions(today: Optional[str] = None, apply: bool = True) -> Dict:
    """전 인벤토리의 상태를 계산하고(apply=True 면 표식·은퇴·큐까지 집행) 요약을 돌려준다."""
    pol = load_policy()
    today = today or date.today().isoformat()
    st = _load_state()
    inv = collect_inventory()
    refs = collect_references(inv)

    # 살아 있는 참조자 = 인벤토리 중 (이전 상태에서) candidate 가 아닌 것 + 의사 참조자 전부
    prev_candidates = set(st["candidates"].keys())

    def _supported(key: str) -> Tuple[bool, List[str]]:
        live = [r for r in refs.get(key, ()) if (":" in r and r.split(":")[0] not in
                ("action", "guide", "workflow", "script")) or r not in prev_candidates]
        return bool(live), sorted(live)[:5]

    out = {"today": today, "total": len(inv), "alive": 0, "grace": 0, "candidates": [],
           "revived": [], "retired": [], "verdicts": [], "errors": []}
    changed_paths: List[str] = []
    commit_notes: List[str] = []

    # 사라진 항목(사람이 지웠거나 은퇴됨)의 상태 정리
    for k in list(st["candidates"].keys()):
        if k not in inv:
            st["candidates"].pop(k, None)

    for key, meta in inv.items():
        first = st["first_seen"].setdefault(key, today)
        sig = last_signal(meta)
        supported, by = _supported(key)
        signal_recent = bool(sig) and _days_between(sig, today) <= pol["candidate_after_days"]
        in_grace = _days_between(first, today) < pol["grace_days"]
        cand = st["candidates"].get(key)

        if supported or signal_recent or in_grace:
            if cand:
                # 부활 — 계절성의 학습. 왜 살았는지(참조·신호)를 남긴다.
                st["candidates"].pop(key, None)
                rec = {"key": key, "candidate_since": cand.get("since"), "revived_on": today,
                       "days": _days_between(cand.get("since", today), today),
                       "by": ("reference:" + ",".join(by)) if supported else f"signal:{sig}"}
                st["revivals"].append(rec)
                out["revived"].append(rec)
                if apply:
                    try:
                        _unmark(meta)
                        if meta.get("path"):
                            changed_paths.append(str(meta["path"].relative_to(BASE)))
                    except Exception as e:
                        out["errors"].append(f"{key}: 표식 해제 실패 {e}")
            if in_grace and not (supported or signal_recent):
                out["grace"] += 1
            else:
                out["alive"] += 1
            continue

        # 지지 없음 · 신호 없음 · 유예 지남
        evidence = (f"참조 0 · 쓸모 실행 {('마지막 ' + sig) if sig else '0'} · "
                    f"첫 관측 {first}")
        if not cand:
            st["candidates"][key] = {"since": today, "evidence": evidence, "kind": meta["kind"]}
            out["candidates"].append({"key": key, "since": today, "evidence": evidence, "new": True})
            if apply:
                try:
                    _mark(meta, today, evidence)
                    if meta.get("path"):
                        changed_paths.append(str(meta["path"].relative_to(BASE)))
                    if meta["kind"] == "script":
                        changed_paths.append(str((SCRIPTS_DIR / "registry.yaml").relative_to(BASE)))
                except Exception as e:
                    out["errors"].append(f"{key}: 표식 실패 {e}")
            continue

        out["candidates"].append({"key": key, "since": cand["since"], "evidence": cand.get("evidence"),
                                  "new": False})
        if _days_between(cand["since"], today) < pol["retire_after_days"]:
            continue

        # retire
        if meta["kind"] in RETIRE_BY_VERDICT:
            if apply and key not in st["verdict_queued"]:
                text = (f"어휘 {meta['name']} 은퇴? — candidate {cand['since']} 이후 "
                        f"{_days_between(cand['since'], today)}일 무신호 · {cand.get('evidence')}. "
                        f"판정=은퇴면 retired_contracts.yaml 한 줄 + 코퍼스 이관(있는 절차)")
                if queue_verdict(key, text):
                    st["verdict_queued"][key] = today
                    out["verdicts"].append(key)
            continue
        if not apply:
            out["retired"].append({"key": key, "dry": True})
            continue
        try:
            if meta["kind"] == "guide":
                paths = _retire_guide(meta)
            elif meta["kind"] == "workflow":
                paths = _retire_workflow(meta)
            else:
                paths = _retire_script(meta)
            st["candidates"].pop(key, None)
            rec = {"key": key, "retired_on": today, "candidate_since": cand["since"],
                   "evidence": cand.get("evidence"), "paths": paths}
            st["retired"].append(rec)
            out["retired"].append(rec)
            changed_paths += paths
            commit_notes.append(f"{meta['kind']} {meta['name']}")
        except Exception as e:
            out["errors"].append(f"{key}: 은퇴 집행 실패 {e}")

    st["last_run"] = datetime.now().isoformat()
    _save_state(st)

    if apply and changed_paths:
        uniq = list(dict.fromkeys(changed_paths))
        if commit_notes:
            msg = (f"apoptosis: 은퇴 {len(commit_notes)}건 — {', '.join(commit_notes[:6])}"
                   f"{' …' if len(commit_notes) > 6 else ''} (component_lifecycle, 되살리기=파일 이동)")
        else:
            msg = (f"lifecycle: candidate 표식 {len(uniq)}경로 (component_lifecycle — "
                   f"무참조·무신호 {pol['candidate_after_days']}일, 숨김 아님)")
        out["committed"] = _commit(uniq, msg)
        out["commit_paths"] = uniq
    return out


# ---------------------------------------------------------------- 번들 진입점

def _should_run(force: bool, hours: int) -> bool:
    if force:
        return True
    try:
        st = _load_state()
        last = st.get("last_run")
        if last and datetime.now() - datetime.fromisoformat(last) < timedelta(hours=hours):
            return False
    except Exception:
        pass
    return True


def run_lifecycle_check(force: bool = False) -> Dict:
    """일일 카덴스로 전이를 계산·집행하고 self_checks 형식 1건을 돌려준다(run_maintenance_bundle 합류)."""
    pol = load_policy()
    if not _should_run(force, pol["cadence_hours"]):
        return {"skipped": "cadence"}
    started = datetime.now()
    error = None
    res: Dict = {}
    try:
        res = compute_transitions(apply=True)
    except Exception as e:
        error = f"측정 실패: {e}"
        logger.warning(f"[Lifecycle] {error}")

    new_c = [c for c in res.get("candidates", []) if c.get("new")]
    notes = []
    if new_c:
        notes.append(f"candidate 진입 {len(new_c)}: " + ", ".join(c["key"] for c in new_c[:6]))
    if res.get("revived"):
        notes.append(f"부활 {len(res['revived'])}")
    if res.get("retired"):
        notes.append(f"은퇴 {len(res['retired'])}: " + ", ".join(r["key"] for r in res["retired"][:6]))
    if res.get("verdicts"):
        notes.append(f"판정 큐 적립 {len(res['verdicts'])}")
    if res.get("errors"):
        notes.append(f"오류 {len(res['errors'])}")
    try:
        FLAGS_PATH.write_text(json.dumps({"measured_at": started.isoformat(), "error": error,
                                          **{k: v for k, v in res.items()}},
                                         ensure_ascii=False, indent=1, default=str),
                              encoding="utf-8")
    except Exception as e:
        logger.warning(f"[Lifecycle] 깃발 저장 실패 (무시): {e}")
    if notes and not error:
        logger.info(f"[Lifecycle] {' · '.join(notes)}")
        try:
            from notification_manager import get_notification_manager
            get_notification_manager().create(
                "구성요소 생명주기", " · ".join(notes) + " — data/lifecycle_flags.json",
                type="info", source="lifecycle")
        except Exception:
            pass
    return {
        "node": "__telemetry__",
        "action": "component_lifecycle",
        "success": error is None and not res.get("errors"),
        "response_ms": int((datetime.now() - started).total_seconds() * 1000),
        "data_quality": "audit_incomplete" if error else ("ok" if not res.get("errors") else "partial"),
        "error_message": error or (" / ".join(res.get("errors", [])[:3]) or None),
        **{k: res.get(k) for k in ("total", "alive", "grace", "candidates", "revived", "retired",
                                   "verdicts", "committed")},
    }


def run_lifecycle_bundle(save_self_check=None) -> Dict:
    """유지보수 번들의 한 입구 — 생명주기(일일)와 가이드 하향 정규화(주간)를 개별 격리로 돈다.
    호출부(world_pulse_health)가 항목마다 자라지 않게(1500줄 규칙, fixture_sweeps 선례)."""
    out: Dict = {}
    from guide_downscale import run_guide_downscale
    for key, fn, label in (("lifecycle", run_lifecycle_check, "생명주기"),
                           ("guide_downscale", run_guide_downscale, "가이드 하향 정규화")):
        try:
            r = fn()
            out[key] = r
            if r.get("node") and save_self_check:
                try:
                    save_self_check(r)
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001 — 하나의 죽음이 나머지를 끌고 가지 않는다
            logger.warning(f"[Maintenance] {label} 실패 (무시): {e}")
    return out
