"""어휘 개념중복 주간 감사 — 해마 코퍼스의 교차-액션 최근접(실증 신호).

압축 상설 기관 (5)의 셋째 신호(docs/VOCAB_DEDUP_HANDOFF.md):
  자백(desc 면책)·구조(op 닮음)는 build --check 의 compression_warnings 가 커밋마다 보고,
  *실증*(같은 의도가 서로 다른 액션에 붙어 있음)은 코퍼스를 읽어야 해서 여기 산다 —
  **빌드는 코퍼스를 안 읽는다** 원칙(코퍼스는 런타임 데이터, 빌드는 저술물만).

무엇을 보나: ibl_examples 임베딩에서 서로 다른 액션 간 코사인 ≥ 0.95 인 최근접쌍.
그 의미는 "병합하라"가 아니라 **"코퍼스 오라벨/동음이의 후보"** — 설계축(sense/limbs)과
동음이의(board/bulletin)는 병합 금지 대상이므로(진단 정정 2·3), 처방은 언제나
①오라벨이면 code 수정 ②애매 intent 면 문맥화 ③진짜 같은 개념이면 그때 병합 검토.

비용: 주간 카덴스(run_maintenance_bundle 합류, 자기 페이싱). LLM 0 — 벡터는 이미 있다.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

try:
    from logging_utils import get_logger
    logger = get_logger(__name__)
except Exception:  # pragma: no cover - 독립 실행 폴백
    import logging
    logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent
_STATE_PATH = _ROOT / "data" / ".ibl_overlap_audit_state.json"
_FLAGS_PATH = _ROOT / "data" / "ibl_overlap_flags.json"

CADENCE_HOURS = 168        # 주 1회 (description_drift 와 같은 카덴스)
COS_THRESHOLD = 0.95       # 2026-08-05 감사 기준 — "게시판 목록 보여줘" 쌍이 0.990 이었다
_MAX_FLAGS = 40            # 보고 상한 (그 이상이면 개별쌍이 아니라 구조 문제)


def _should_run(force: bool) -> bool:
    if force:
        return True
    try:
        state = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        last = datetime.fromisoformat(state["last_run"])
        return datetime.now() - last >= timedelta(hours=CADENCE_HOURS)
    except Exception:
        return True


def _action_of(code: str) -> str:
    m = re.search(r"\[(\w+):(\w+)\]", code or "")
    return f"{m.group(1)}:{m.group(2)}" if m else "?"


def _measure_overlaps() -> List[Dict]:
    """코퍼스 임베딩에서 교차-액션 최근접쌍(cos ≥ COS_THRESHOLD)을 액션쌍 단위로 집계."""
    import numpy as np
    from ibl_usage_db import IBLUsageDB

    db = IBLUsageDB()
    conn = db._get_vec_connection()   # ★_get_connection 은 vec 미로드 일반 연결 — vec0 조인은 이쪽
    if conn is None:
        raise RuntimeError("sqlite-vec 연결 불가 (미설치?)")
    try:
        rows = conn.execute(
            "SELECT e.id, e.intent, e.ibl_code, v.embedding "
            "FROM ibl_examples e JOIN ibl_examples_vec v ON v.rowid = e.id"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return []

    intents = [r[1] or "" for r in rows]
    acts = [_action_of(r[2]) for r in rows]
    mat = np.vstack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    sim = mat @ mat.T
    np.fill_diagonal(sim, -1.0)

    pairs: Dict[tuple, Dict] = {}
    for i in range(len(rows)):
        j = int(sim[i].argmax())
        score = float(sim[i][j])
        if score < COS_THRESHOLD or acts[i] == acts[j] or acts[i] == "?" or acts[j] == "?":
            continue
        key = tuple(sorted([acts[i], acts[j]]))
        cur = pairs.get(key)
        if cur is None:
            pairs[key] = {
                "actions": list(key), "count": 1, "max_cos": round(score, 4),
                "example": [intents[i][:60], intents[j][:60]],
            }
        else:
            cur["count"] += 1
            if score > cur["max_cos"]:
                cur["max_cos"] = round(score, 4)
                cur["example"] = [intents[i][:60], intents[j][:60]]
    return sorted(pairs.values(), key=lambda p: -p["max_cos"])[:_MAX_FLAGS]


def run_vocab_overlap_check(force: bool = False) -> Dict:
    """주간 카덴스로 코퍼스 개념중복을 감사하고 self_checks 형식 1건을 반환.

    run_maintenance_bundle(self-check 사이클)에 합류한다. 6h마다 호출돼도 주 1회만 실제 실행.
    플래그는 data/ibl_overlap_flags.json + self_checks(__ibl_health__:vocab_overlap)에 남는다.
    """
    if not _should_run(force):
        return {"skipped": "cadence"}

    started = datetime.now()
    flags: List[Dict] = []
    error = None
    try:
        flags = _measure_overlaps()
    except Exception as e:
        # ★측정 실패도 실패다 — 못 본 것을 '중복 0'으로 보고하면 이 감사는 눈이 먼 것.
        error = f"측정 실패: {e}"
        logger.warning(f"[VocabOverlap] {error}")

    try:
        _STATE_PATH.write_text(json.dumps({
            "last_run": started.isoformat(),
            "flag_count": len(flags),
            "error": error,
        }, ensure_ascii=False), encoding="utf-8")
        _FLAGS_PATH.write_text(json.dumps({
            "measured_at": started.isoformat(),
            "threshold": COS_THRESHOLD,
            "flags": flags,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[VocabOverlap] 상태 저장 실패 (무시): {e}")

    if flags:
        head = "; ".join(f"{f['actions'][0]}↔{f['actions'][1]}({f['max_cos']})" for f in flags[:5])
        logger.warning(f"[VocabOverlap] 개념중복 후보 {len(flags)}쌍 — {head} ({_FLAGS_PATH.name} 참조)")
    elif not error:
        logger.info(f"[VocabOverlap] 교차-액션 최근접 ≥{COS_THRESHOLD} 없음 — 코퍼스 경계 깨끗")

    return {
        "node": "__ibl_health__",
        "action": "vocab_overlap",
        "success": not flags and not error,
        "response_ms": int((datetime.now() - started).total_seconds() * 1000),
        "data_quality": ("ok" if not flags and not error
                         else "vocab_overlap" if flags else "audit_incomplete"),
        "error_message": (f"{len(flags)}쌍 개념중복 후보 — ibl_overlap_flags.json" if flags else error),
        "flags": flags,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(_ROOT / "backend"))
    import boot_paths  # noqa: F401 — 층 디렉토리 등재
    r = run_vocab_overlap_check(force=True)
    print(json.dumps(r, ensure_ascii=False, indent=2))
