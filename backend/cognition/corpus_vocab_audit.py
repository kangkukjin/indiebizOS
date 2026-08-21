"""corpus_vocab_audit.py — 라이브 코퍼스 어휘 생존 감사 (2026-08-22).

`data/ibl_usage.db` 의 용례가 **아직 존재하는 어휘**만 가르치는지, 그리고 전부 파싱되는지
주 1회 확인한다. 커밋 게이트(`build_ibl_nodes.py --check` 의 "코퍼스 어휘 생존")는
git 이 추적하는 `data/training/*.json` 만 본다 — 라이브 DB 는 증류로 계속 자라고
gitignore 라 그 게이트 밖이다. 여기가 그 자리다.

왜 필요한가(2026-08-22 실측): 어휘를 은퇴시킬 때 라이브 DB 는 이관 스크립트로 따라왔지만
학습 파일은 부분적으로만 따라와 은퇴 어휘 20여 종 208항목을 3개월간 안고 있었다. 같은
일이 DB 쪽에서 일어나면 — 증류가 옛 형태를 다시 앉히거나, 은퇴 이관이 한 곳을 빠뜨리면 —
회상이 존재하지 않는 액션을 가르치고, 그 문장은 실행 시점에야 죽는다.
파싱 불가도 같은 부류다(실측 1건: 은퇴한 `run_command(...)` 셸 호출 형태가 남아 있었다).

비용: 파서 왕복 수천 회(무LLM, 수 초). 주간 카덴스(run_maintenance_bundle 합류).
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

try:                                   # 층 모듈 — 평면 import (boot_paths 는 진입점이 이미 얹었다)
    from logging_utils import get_logger
    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent.parent.parent
_DB_PATH = BASE / "data" / "ibl_usage.db"
_NODES_PATH = BASE / "data" / "ibl_nodes.yaml"
_STATE_PATH = BASE / "data" / "corpus_vocab_audit_state.json"

CADENCE_HOURS = 168        # 주 1회 — 커밋 게이트가 학습 파일을 매 커밋 보는 것과 역할 분담
_MAX_REPORT = 12           # 원인 어휘는 소수라 앞부분이면 충분


def _walk_leaves(obj: Any, out: List[dict]):
    if isinstance(obj, dict):
        if "_node" in obj and "action" in obj:
            out.append(obj)
        for v in obj.values():
            _walk_leaves(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_leaves(v, out)


def audit_corpus_vocab() -> Dict:
    """라이브 코퍼스 전수 감사. 반환: {total, dead, unparsable, flags}."""
    import sqlite3
    import yaml
    from ibl_parser import parse

    nodes = (yaml.safe_load(_NODES_PATH.read_text(encoding="utf-8")) or {}).get("nodes", {})
    conn = sqlite3.connect(str(_DB_PATH))
    rows = list(conn.execute("SELECT id, intent, ibl_code FROM ibl_examples"))
    conn.close()

    flags: List[Dict] = []
    dead = unparsable = 0
    for rid, intent, code in rows:
        try:
            parsed = parse(code or "")
        except Exception as e:
            unparsable += 1
            flags.append({"id": rid, "kind": "unparsable",
                          "intent": str(intent)[:60], "detail": str(e)[:80]})
            continue
        leaves: List[dict] = []
        _walk_leaves(parsed, leaves)
        for st in leaves:
            n, a = st.get("_node"), st.get("action")
            if n not in nodes or a not in (nodes.get(n, {}).get("actions") or {}):
                dead += 1
                flags.append({"id": rid, "kind": "dead_vocab", "vocab": f"{n}:{a}",
                              "intent": str(intent)[:60]})
    return {"total": len(rows), "dead": dead, "unparsable": unparsable, "flags": flags}


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


def _save_state(result: Dict):
    try:
        _STATE_PATH.write_text(json.dumps({
            "last_run": datetime.now().isoformat(),
            "total": result.get("total", 0),
            "dead": result.get("dead", 0),
            "unparsable": result.get("unparsable", 0),
            "flags": result.get("flags", [])[:60],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[CorpusVocab] 상태 저장 실패 (무시): {e}")


def run_corpus_vocab_audit(force: bool = False) -> Dict:
    """주간 카덴스 게이트. run_maintenance_bundle 에서 호출된다."""
    if not _should_run(force):
        return {"skipped": "cadence"}

    result = audit_corpus_vocab()
    _save_state(result)

    bad = result["dead"] + result["unparsable"]
    if bad:
        head = "; ".join(
            f.get("vocab") or f"#{f['id']} 파싱불가" for f in result["flags"][:_MAX_REPORT])
        logger.warning(
            f"[CorpusVocab] 라이브 코퍼스 {result['total']}건 중 죽은 어휘 {result['dead']} / "
            f"파싱 불가 {result['unparsable']} — {head} ({_STATE_PATH.name} 참조)")
    else:
        logger.info(f"[CorpusVocab] 라이브 코퍼스 {result['total']}건 전수 감사 — 죽은 어휘·파싱 불가 0")

    return {
        "name": "corpus_vocab",
        "ok": bad == 0,
        "detail": (f"용례 {result['total']}건 · 죽은 어휘 {result['dead']} · "
                   f"파싱 불가 {result['unparsable']}"),
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import boot_paths  # noqa: F401 — 단독 실행 시에만 층 경로를 얹는다
    r = audit_corpus_vocab()
    print(f"라이브 코퍼스 {r['total']}건 — 죽은 어휘 {r['dead']} · 파싱 불가 {r['unparsable']}")
    for f in r["flags"][:20]:
        print(f"  ✗ #{f['id']} [{f['kind']}] {f.get('vocab', '')} {f['intent']}")
    sys.exit(1 if (r["dead"] or r["unparsable"]) else 0)
