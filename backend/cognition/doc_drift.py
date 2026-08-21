"""doc_drift.py — 문서 드리프트 주간 감사 (2026-08-21 신설)

## 왜 있나 — 파생이 못 덮는 산문의 부패
빌드의 문서 파생(scripts/iblbuild_docs.py)은 마커 구간의 *수치*를 재기입하지만,
산문 속 주장은 못 고친다. 실증: `run_static_ibl_check` 는 2026-06-27 은퇴했는데
7개 문서가 3개월째 그 함수를 정본 배관으로 가르치고 있었다(2026-08-21 발견) —
data_ownership 이 잡은 my_profile.txt 선언 부패와 같은 부류. 이 감사는 그 부류를
주간으로 깃발한다. **보고만, 고치지 않음**(산문 수정은 사람/AI 의 판단).

## 무엇을 보나 (결정론, LLM 0)
1) 복합 수치 주장 — "N노드 M 액션"·"N nodes, M actions" ↔ 레지스트리 실측
2) 죽은 참조 — 백틱 `모듈.py`(실존)·`식별자()`(코드에 부재)
3) 날짜 모순 — 프론트매터 last_updated 보다 꼬리 "*마지막/최종 업데이트*" 가 최신

## 규율
- 역사 서술은 침범하지 않는다: 꼬리 changelog 줄(`*마지막/최종 업데이트`)·화살표(→)·
  "N에서 M" 이행문·은퇴/폐기 표기 줄은 건너뜀 — "그때의 기록"은 보존 대상이다.
- 마커 파생 구간·코드 펜스는 마스킹(기계 소유·예시는 주장 아님).
- ★측정 실패도 실패다 — 못 본 문서를 '깨끗함'으로 보고하지 않는다(unchecked 분리).
"""
import json
import logging
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent
_STATE_PATH = _ROOT / "data" / ".doc_drift_state.json"
_FLAGS_PATH = _ROOT / "data" / "doc_drift_flags.json"

CADENCE_HOURS = 168     # 주 1회 (data_ownership·vocab_overlap 과 같은 카덴스)
_MAX_FLAGS = 80         # 보고 상한 — 그 이상이면 개별 문장이 아니라 구조 문제

# 감사 대상 (README 2종 + system_docs 산문 전부)
def _target_docs() -> List[Path]:
    docs = [_ROOT / "README.md", _ROOT / "README.ko.md"]
    sd = _ROOT / "data" / "system_docs"
    if sd.is_dir():
        docs += sorted(sd.glob("*.md"))
    return [d for d in docs if d.is_file()]


# ── 실측 (레지스트리) ────────────────────────────────────────────────────────

def _registry_facts() -> Dict:
    import yaml
    data = yaml.safe_load((_ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    nodes = data.get("nodes") or {}
    per = {n: len(b.get("actions") or {}) for n, b in nodes.items() if isinstance(b, dict)}
    tools_d = _ROOT / "data" / "packages" / "installed" / "tools"
    exts_d = _ROOT / "data" / "packages" / "installed" / "extensions"
    count = lambda d: len([p for p in d.iterdir() if p.is_dir() and not p.name.startswith("__")]) if d.is_dir() else 0
    return {"node_count": len(per), "total": sum(per.values()),
            "tools_n": count(tools_d), "exts_n": count(exts_d)}


# ── 마스킹·역사 판별 ─────────────────────────────────────────────────────────

_MARKER_RE = re.compile(r"<!--\s*[A-Z_0-9]+(?::\d+)?:START\s*-->.*?<!--\s*[A-Z_0-9]+(?::\d+)?:END\s*-->", re.DOTALL)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _mask(text: str) -> str:
    """마커 파생 구간·코드 펜스를 줄 구조 보존한 채 비운다(줄 번호 유지)."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    return _FENCE_RE.sub(blank, _MARKER_RE.sub(blank, text))


def _is_historical(line: str) -> bool:
    s = line.strip()
    if (s.startswith("*마지막 업데이트") or s.startswith("*최종 업데이트")
            or s.startswith("*최근 변경")):
        return True  # 꼬리 changelog — 그때의 기록 (최근 변경=2026-08-21 다이어트 후 규약)
    if "→" in s:
        return True  # 이행 서술 (163→144 등)
    if re.search(r"\d+\s*개?\s*(?:에서|to)\s+\d+", s):
        return True
    if re.search(r"은퇴|폐기|삭제됨|retired", s):
        return True
    if re.search(r"이전\s*\(20\d\d", s):
        return True  # "이전(2026-…)" 역사 문단
    return False


# ── 검사 1: 복합 수치 주장 ───────────────────────────────────────────────────

_COMPOUND_PATTERNS = [
    # "6노드 149 액션" / "6개 노드 149 액션" / "6개 노드, 149개 조합 가능한 액션"
    re.compile(r"(\d+)\s*개?\s*노드[,\s·]*(\d+)\s*개?\s*(?:조합 가능한\s*)?액션"),
    # "6 nodes, 149 composable actions"
    re.compile(r"(\d+)\s+nodes?,\s*(\d+)\s+(?:composable\s+)?actions"),
]


def _check_stats_claims(rel: str, masked: str, facts: Dict) -> List[Dict]:
    flags = []
    for i, line in enumerate(masked.splitlines(), 1):
        if _is_historical(line):
            continue
        for pat in _COMPOUND_PATTERNS:
            for m in pat.finditer(line):
                n, t = int(m.group(1)), int(m.group(2))
                if n != facts["node_count"] or t != facts["total"]:
                    flags.append({
                        "kind": "stats_claim", "doc": rel, "line": i,
                        "claim": f"{n}노드 {t}액션",
                        "actual": f"{facts['node_count']}노드 {facts['total']}액션",
                        "hint": "실측과 다른 현재형 주장 — 수정하거나 파생 마커로 감쌀 것",
                    })
    return flags


# ── 검사 2: 죽은 참조 ────────────────────────────────────────────────────────

_IDENT_CALL_RE = re.compile(r"^(?:[a-z_][a-z0-9_]*\.)?([a-z_][a-z0-9_]{5,})\(\)$")
_IDENT_ATTR_RE = re.compile(r"^[a-z_][a-z0-9_]*\.([a-z_][a-z0-9_]{5,})$")


def _tracked_py_files() -> List[Path]:
    try:
        # --others: 방금 만든 미추적 모듈도 실존으로 인정 (커밋 전 문서가 오탐되지 않게)
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py"],
            cwd=_ROOT, capture_output=True, text=True, timeout=20)
        if out.returncode == 0:
            return [_ROOT / ln for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        pass
    return [p for p in _ROOT.glob("backend/**/*.py")] + [p for p in _ROOT.glob("scripts/*.py")]


def _check_dead_refs(doc_flags: List[Dict], per_doc_tokens: Dict[str, List[tuple]]) -> None:
    """전 문서의 후보 식별자를 모아 코드 전체를 1회 스트리밍 대조."""
    py_files = _tracked_py_files()
    basenames = {p.name for p in py_files}
    # 파일 참조는 즉시 판정
    pending: Dict[str, List[tuple]] = {}
    for rel, tokens in per_doc_tokens.items():
        for line_no, token in tokens:
            if token.endswith(".py"):
                name = token.rsplit("/", 1)[-1]
                if "/" in token:
                    # 슬래시 축약 관용구 허용: `launcher_surface_remote/phone.py` 는
                    # 경로가 아니라 모듈 나열(remote·phone) — 첫 조각이 실존 모듈이면 통과.
                    first = token.split("/", 1)[0]
                    ok = ((_ROOT / token).is_file() or name in basenames
                          or f"{first}.py" in basenames)
                else:
                    ok = name in basenames
                if not ok:
                    doc_flags.append({"kind": "dead_ref", "doc": rel, "line": line_no,
                                      "claim": token, "hint": "참조된 .py 가 저장소에 없음"})
            else:
                pending.setdefault(token, []).append((rel, line_no))
    if not pending:
        return
    remaining = set(pending)
    for p in py_files:
        if not remaining:
            break
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        remaining = {t for t in remaining if t not in content}
    for token in sorted(remaining):
        for rel, line_no in pending[token]:
            doc_flags.append({"kind": "dead_ref", "doc": rel, "line": line_no,
                              "claim": f"{token}()",
                              "hint": "참조된 식별자가 코드 어디에도 없음 — 은퇴 표기 또는 현행 배관으로 교체"})


def _collect_ident_tokens(masked: str) -> List[tuple]:
    tokens = []
    for i, line in enumerate(masked.splitlines(), 1):
        if _is_historical(line):
            continue
        for raw in re.findall(r"`([^`\n]{2,80})`", line):
            raw = raw.strip()
            if raw.endswith(".py") and re.fullmatch(r"[A-Za-z0-9_./-]+", raw):
                tokens.append((i, raw))
                continue
            m = _IDENT_CALL_RE.fullmatch(raw) or _IDENT_ATTR_RE.fullmatch(raw)
            if m:
                tokens.append((i, m.group(1)))
    return tokens


# ── 검사 3: 날짜 모순 ────────────────────────────────────────────────────────

def _check_dates(rel: str, text: str) -> List[Dict]:
    fm = re.search(r"^last_updated:\s*(\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
    if not fm:
        return []
    tails = (re.findall(r"\*(?:마지막|최종) 업데이트:\s*(\d{4}-\d{2}-\d{2})", text)
             + re.findall(r"\*최근 변경\((\d{4}-\d{2}-\d{2})\)", text))
    if not tails:
        return []
    newest_tail = max(tails)
    if newest_tail > fm.group(1):
        return [{"kind": "date_mismatch", "doc": rel, "line": 0,
                 "claim": f"frontmatter {fm.group(1)} < 꼬리 {newest_tail}",
                 "hint": "본문은 갱신됐는데 frontmatter last_updated 를 잊음"}]
    return []


# ── 진입점 ───────────────────────────────────────────────────────────────────

def _should_run(force: bool = False) -> bool:
    if force:
        return True
    try:
        st = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        last = st.get("last_run")
        if not last:
            return True
        return datetime.now() - datetime.fromisoformat(last) >= timedelta(hours=CADENCE_HOURS)
    except Exception:
        return True


def measure() -> Dict:
    """순수 측정 — 카덴스·상태 무관. {flags, unchecked, docs}."""
    facts = _registry_facts()
    flags: List[Dict] = []
    unchecked: List[str] = []
    per_doc_tokens: Dict[str, List[tuple]] = {}
    docs = _target_docs()
    for fp in docs:
        rel = str(fp.relative_to(_ROOT))
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception as e:
            unchecked.append(f"{rel}({e.__class__.__name__})")
            continue
        masked = _mask(text)
        flags.extend(_check_stats_claims(rel, masked, facts))
        flags.extend(_check_dates(rel, text))
        per_doc_tokens[rel] = _collect_ident_tokens(masked)
    _check_dead_refs(flags, per_doc_tokens)
    if len(flags) > _MAX_FLAGS:
        flags = flags[:_MAX_FLAGS]
    return {"flags": flags, "unchecked": unchecked,
            "docs": [str(d.relative_to(_ROOT)) for d in docs], "facts": facts}


def run_doc_drift_check(force: bool = False) -> Dict:
    """주간 카덴스로 문서 산문을 감사하고 self_checks 형식 1건을 반환.

    run_maintenance_bundle 합류. 깃발은 data/doc_drift_flags.json 에 —
    **보고만, 고치지 않음**(실집행=사람/AI 의 판단).
    """
    if not _should_run(force):
        return {"skipped": "cadence"}
    started = datetime.now()
    flags, unchecked, error = [], [], None
    try:
        r = measure()
        flags, unchecked = r["flags"], r["unchecked"]
    except Exception as e:
        # ★측정 실패도 실패다 — 못 본 것을 '깃발 0'으로 보고하면 이 감사는 눈이 먼 것.
        error = f"측정 실패: {e}"
        logger.warning(f"[DocDrift] {error}")
    try:
        _STATE_PATH.write_text(json.dumps({
            "last_run": started.isoformat(), "flag_count": len(flags),
            "unchecked": unchecked, "error": error,
        }, ensure_ascii=False), encoding="utf-8")
        _FLAGS_PATH.write_text(json.dumps({
            "measured_at": started.isoformat(), "flags": flags, "unchecked": unchecked,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[DocDrift] 상태 저장 실패 (무시): {e}")
    if flags:
        logger.warning(f"[DocDrift] 문서 드리프트 {len(flags)}건 — doc_drift_flags.json")
    else:
        logger.info("[DocDrift] 문서 드리프트 깃발 0")
    return {
        "node": "__static__",
        "action": "doc_drift",
        "success": not flags and not error,
        "response_ms": int((datetime.now() - started).total_seconds() * 1000),
        "data_quality": ("ok" if not flags and not error
                         else "drift" if flags else "audit_incomplete"),
        "error_message": (f"문서 드리프트 {len(flags)}건 — doc_drift_flags.json" if flags else error),
        "flags": flags, "unchecked": unchecked,
    }
