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
from hashlib import sha256
from datetime import datetime
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

COS_THRESHOLD = 0.95       # 2026-08-05 감사 기준 — "게시판 목록 보여줘" 쌍이 0.990 이었다
_MAX_FLAGS = 40            # 보고 상한 (그 이상이면 개별쌍이 아니라 구조 문제)


def _action_of(code: str) -> str:
    m = re.search(r"\[(\w+):(\w+)\]", code or "")
    return f"{m.group(1)}:{m.group(2)}" if m else "?"


def _load_corpus():
    """지문과 검사가 같은 스냅샷을 쓴다. 임베딩 누락은 깨끗한 코퍼스가 아니다."""
    from ibl_usage_db import IBLUsageDB

    db = IBLUsageDB()
    conn = db._get_vec_connection()   # ★_get_connection 은 vec 미로드 일반 연결 — vec0 조인은 이쪽
    if conn is None:
        raise RuntimeError("sqlite-vec 연결 불가 (미설치?)")
    try:
        conn.execute("BEGIN")
        total = conn.execute("SELECT COUNT(*) FROM ibl_examples").fetchone()[0]
        rows = conn.execute(
            "SELECT e.id, e.intent, e.ibl_code, v.embedding "
            "FROM ibl_examples e JOIN ibl_examples_vec v ON v.rowid = e.id ORDER BY e.id"
        ).fetchall()
    finally:
        conn.close()
    if len(rows) != total:
        raise ValueError(f"임베딩 관측 부족: {len(rows)}/{total}행")
    return rows


def _corpus_fingerprint(rows):
    digest = sha256(Path(__file__).read_bytes())  # 검사 규칙의 변경도 새 입력이다.
    for row in rows:
        digest.update(json.dumps(list(row[:3]), ensure_ascii=False).encode())
        digest.update(sha256(row[3]).digest())
    return digest.hexdigest()


def _measure_overlaps(rows=None) -> List[Dict]:
    """코퍼스 임베딩에서 교차-액션 최근접쌍(cos ≥ COS_THRESHOLD)을 액션쌍 단위로 집계."""
    import numpy as np
    rows = _load_corpus() if rows is None else rows
    if not rows:
        return []

    intents = [r[1] or "" for r in rows]
    acts = [_action_of(r[2]) for r in rows]
    if "?" in acts:
        raise ValueError("액션을 식별하지 못한 예문이 있어 교차-액션 검사를 완료할 수 없습니다")
    mat = np.vstack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    if not np.isfinite(mat).all() or (norms <= 0).any():
        raise ValueError("비유한 또는 빈 임베딩이 있어 검사를 완료할 수 없습니다")
    mat = mat / norms
    sim = mat @ mat.T
    np.fill_diagonal(sim, -1.0)
    action_array = np.asarray(acts)

    pairs: Dict[tuple, Dict] = {}
    for i in range(len(rows)):
        # 같은 액션의 더 가까운 이웃이 교차-액션 후보를 가리지 않게 먼저 제외한다.
        sim[i, action_array == acts[i]] = -1.0
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
    started = datetime.now()
    flags: List[Dict] = []
    error = None
    fingerprint = None
    rows = []
    from audit_lifecycle import due, next_cadence, read_state
    previous = read_state(_STATE_PATH)
    try:
        rows = _load_corpus()
        if not rows:
            return {"skipped": "empty_corpus", "checked_examples": 0}
        fingerprint = _corpus_fingerprint(rows)
        if not due(_STATE_PATH, force, fingerprint=fingerprint):
            return {"skipped": "cadence", "fingerprint": fingerprint}
        flags = _measure_overlaps(rows)
    except Exception as e:
        # ★측정 실패도 실패다 — 못 본 것을 '중복 0'으로 보고하면 이 감사는 눈이 먼 것.
        error = f"측정 실패: {e}"
        logger.warning(f"[VocabOverlap] {error}")

    try:
        cadence = next_cadence(previous, fingerprint=fingerprint,
                               clean=not flags and not error, complete=bool(rows) and not error)
        _FLAGS_PATH.write_text(json.dumps({
            "measured_at": started.isoformat(),
            "threshold": COS_THRESHOLD,
            "flags": flags,
            "error": error, "checked_examples": len(rows), "fingerprint": fingerprint,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        _STATE_PATH.write_text(json.dumps({
            "last_run": started.isoformat(),
            "flag_count": len(flags),
            "error": error,
            "fingerprint": fingerprint, "coverage": "complete" if not error and rows else "insufficient",
            "outcome": "failed" if error else "findings" if flags else "clean", **cadence,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        error = f"{error + '; ' if error else ''}상태 저장 실패: {e}"
        logger.warning(f"[VocabOverlap] {error}")

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
        "flags": flags, "error": error, "checked_examples": len(rows), "fingerprint": fingerprint,
        "coverage": "complete" if not error and rows else "insufficient",
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(_ROOT / "backend"))
    import boot_paths  # noqa: F401 — 층 디렉토리 등재
    r = run_vocab_overlap_check(force=True)
    print(json.dumps(r, ensure_ascii=False, indent=2))
