"""store_waste_audit.py — 저장소 낭비 주간 감사 (2026-09-07 신설)

## 왜 있나 — 살아있는 내용보다 껍데기가 50배 큰 파일
실증(2026-09-07): `data/ibl_usage.db` 가 791MB 였는데 실제 내용(예문 3,734건 +
일일 집계)은 2.5MB 였다. 나머지는 sqlite-vec `vec0` 의 **빈 청크** — 벡터는
1,024칸짜리 블롭(768차원 float32 = 3.15MB)에 담기는데, 옛 sqlite-vec 은 칸이 다
비어도 블롭을 회수하지 않았다. 청크 226개 중 **222개가 유효 비트 전부 0**,
즉 698MB 가 한 개도 안 든 껍데기였다. 같은 부류가 blog_insight.db 에도 있었다
(청크 46개, 점유 8%, 133MB).

지금 쓰는 sqlite-vec 0.1.9 는 빈 청크를 회수한다(실측: 3,000건 삽입→전삭제→
재삽입에서 청크 수가 3→0→3). 그러니 이건 **옛 판본이 남긴 잔재**이고 재발하지
않아야 정상이다 — 그 "정상"을 사람 눈이 아니라 이 감사가 지킨다. 세어만 두고
보는 게 아니라(카운터 감시 금지), 임계를 넘으면 self_check 가 실패한다.

## 무엇을 보나 (결정론, LLM 0)
1) **vec0 청크 잔재** — 청크 ≥2 이고 슬롯 점유율 < 50% → 회수 가능 MB 를 깃발.
   처방 = 벡터를 읽어 테이블을 DROP/재생성 후 재삽입, 그리고 VACUUM.
2) **미회수 프리페이지** — freelist 가 파일의 25% 이상이고 8MB 이상 → VACUUM.

## 깃발이 아닌 것 — 청크 1개의 구조적 최소치
벡터가 한 개뿐이어도 vec0 은 청크 하나(3.1MB)를 통째로 잡는다. 프로젝트별
`memory_*.db` 25개가 여기 해당한다(합 ~78MB). 이건 잔재가 아니라 **할당 단위**라
재구성해도 줄지 않는다 — 줄이려면 테이블 생성 시 `chunk_size` 를 낮춰야 하고,
그건 이 감사가 아니라 언어/스키마 결정이다. 그래서 청크 1개짜리는 깃발하지 않고
`structural` 로 따로 보고한다(고칠 수 없는 것을 부채로 세면 감사가 양치기 소년이 된다).

## 규율
- **보고만, 고치지 않음**. VACUUM·재구성은 라이브 DB 를 통째로 다시 쓰는 파괴적
  작업이라 사람/AI 의 판단과 백업이 앞선다(`data/_backups/` 규약).
- `_backups/` 는 감사 대상이 아니다 — 백업은 그때의 모양대로 두는 게 목적이다.
- 열지 못한 파일은 '깨끗함'이 아니라 `unchecked` 로 분리한다(doc_drift 와 같은 규율).
"""
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent
_STATE_PATH = _ROOT / "data" / ".store_waste_state.json"
_FLAGS_PATH = _ROOT / "data" / "store_waste_flags.json"

CADENCE_HOURS = 168          # 주 1회 (doc_drift·data_ownership 과 같은 카덴스)

VEC_MIN_CHUNKS = 2           # 청크 1개 = 구조적 최소 할당, 잔재가 아니다
VEC_MAX_OCCUPANCY = 0.5      # 점유율이 이 아래면 잔재
FREE_RATIO = 0.25            # freelist 가 파일의 이 비율 이상이고
FREE_MIN_BYTES = 8 * 1024**2 # 절대량도 이만큼은 돼야 깃발 (작은 DB 의 소음 제외)

# 감사 대상 루트 — 몸이 쓰는 살아있는 저장소만.
_SCAN_ROOTS = ("data", "projects")
_SKIP_DIRS = {"_backups", "node_modules", ".venv", "release", "__pycache__"}


def _targets() -> List[Path]:
    out = []
    for root in _SCAN_ROOTS:
        base = _ROOT / root
        if not base.is_dir():
            continue
        for p in base.rglob("*.db"):
            if _SKIP_DIRS & set(p.parts):
                continue
            if p.is_file():
                out.append(p)
    return sorted(out)


def _audit_one(path: Path) -> Dict:
    """DB 한 개의 낭비 실측. 열지 못하면 error 를 담아 돌려준다."""
    rel = str(path.relative_to(_ROOT))
    size = path.stat().st_size
    res = {"db": rel, "size_mb": round(size / 1e6, 1), "flags": [], "structural": []}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except Exception as e:
        res["error"] = str(e)
        return res
    try:
        page = conn.execute("PRAGMA page_size").fetchone()[0]
        free = conn.execute("PRAGMA freelist_count").fetchone()[0] * page
        if size and free >= FREE_MIN_BYTES and free / size >= FREE_RATIO:
            res["flags"].append({
                "kind": "freelist", "db": rel, "reclaim_mb": round(free / 1e6, 1),
                "detail": f"미회수 프리페이지 {free/1e6:.1f}MB / 파일 {size/1e6:.1f}MB ({free/size*100:.0f}%)",
                "hint": "VACUUM (백업 먼저: VACUUM INTO data/_backups/…)",
            })
        for (chunks_tbl,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%\\_chunks' ESCAPE '\\'"):
            rows = conn.execute(f"SELECT size, validity FROM '{chunks_tbl}'").fetchall()
            if not rows:
                continue
            cap = sum(r[0] for r in rows)
            live = sum(bin(int.from_bytes(r[1], "little")).count("1") for r in rows)
            if not cap:
                continue
            occ = live / cap
            vec_tbl = chunks_tbl[: -len("_chunks")] + "_vector_chunks00"
            try:
                blob = conn.execute(f"SELECT SUM(LENGTH(vectors)) FROM '{vec_tbl}'").fetchone()[0] or 0
            except Exception:
                blob = 0
            entry = {"db": rel, "table": chunks_tbl, "chunks": len(rows),
                     "live": live, "capacity": cap, "occupancy": round(occ, 3),
                     "reclaim_mb": round(blob * (1 - occ) / 1e6, 1)}
            if len(rows) >= VEC_MIN_CHUNKS and occ < VEC_MAX_OCCUPANCY:
                res["flags"].append({
                    "kind": "vec_chunk_residue", **entry,
                    "detail": f"청크 {len(rows)}개, 슬롯 {live}/{cap} 점유 {occ*100:.0f}%",
                    "hint": "벡터를 읽어 vec0 테이블 DROP·재생성·재삽입 후 VACUUM",
                })
            elif len(rows) == 1 and occ < VEC_MAX_OCCUPANCY:
                res["structural"].append(entry)   # 할당 단위 — 재구성해도 안 줄어든다
    except Exception as e:
        res["error"] = str(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return res


def measure() -> Dict:
    flags, structural, unchecked = [], [], []
    for p in _targets():
        r = _audit_one(p)
        if r.get("error"):
            unchecked.append(f"{r['db']}: {r['error']}")
            continue
        flags.extend(r["flags"])
        structural.extend(r["structural"])
    flags.sort(key=lambda f: -f.get("reclaim_mb", 0))
    return {"flags": flags, "structural": structural, "unchecked": unchecked}


def _should_run(force: bool) -> bool:
    if force:
        return True
    try:
        last = json.loads(_STATE_PATH.read_text(encoding="utf-8")).get("last_run")
        if last and datetime.fromisoformat(last) > datetime.now() - timedelta(hours=CADENCE_HOURS):
            return False
    except Exception:
        pass
    return True


def run_store_waste_check(force: bool = False) -> Dict:
    """주간 카덴스로 저장소 낭비를 감사하고 self_checks 형식 1건을 반환.

    run_maintenance_bundle 합류. 깃발은 data/store_waste_flags.json 에 —
    **보고만, 고치지 않음**(VACUUM·재구성=백업이 앞서는 파괴적 작업).
    """
    if not _should_run(force):
        return {"skipped": "cadence"}
    started = datetime.now()
    flags, structural, unchecked, error = [], [], [], None
    try:
        r = measure()
        flags, structural, unchecked = r["flags"], r["structural"], r["unchecked"]
    except Exception as e:
        # ★측정 실패도 실패다 — 못 본 것을 '낭비 0'으로 보고하면 이 감사는 눈이 먼 것.
        error = f"측정 실패: {e}"
        logger.warning(f"[StoreWaste] {error}")
    reclaim = round(sum(f.get("reclaim_mb", 0) for f in flags), 1)
    try:
        _STATE_PATH.write_text(json.dumps({
            "last_run": started.isoformat(), "flag_count": len(flags),
            "reclaim_mb": reclaim, "unchecked": unchecked, "error": error,
        }, ensure_ascii=False), encoding="utf-8")
        _FLAGS_PATH.write_text(json.dumps({
            "measured_at": started.isoformat(), "flags": flags,
            "structural": structural, "unchecked": unchecked,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[StoreWaste] 상태 저장 실패 (무시): {e}")
    if flags:
        logger.warning(f"[StoreWaste] 저장소 낭비 {len(flags)}건 / 회수 가능 {reclaim}MB — store_waste_flags.json")
    else:
        logger.info("[StoreWaste] 저장소 낭비 깃발 0")
    return {
        "node": "__static__",
        "action": "store_waste",
        "success": not flags and not error,
        "response_ms": int((datetime.now() - started).total_seconds() * 1000),
        "data_quality": ("ok" if not flags and not error
                         else "waste" if flags else "audit_incomplete"),
        "error_message": (f"저장소 낭비 {len(flags)}건 / 회수 가능 {reclaim}MB — store_waste_flags.json"
                          if flags else error),
        "flags": flags, "structural": structural, "unchecked": unchecked,
        "reclaim_mb": reclaim,
    }

