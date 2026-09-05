#!/usr/bin/env python3
"""IBL 조합 비용 — 한 주행이 모델을 몇 번 불렀고 얼마나 타이핑·되읽기했나 (2026-09-05, 사용자 판정).

왜: 목표는 모델의 *창의적 조합 능력* — 결과를 안 보고도 긴 프로그램을 한 번에 맞게 써서 모델 호출
수를 줄이는 것이다(반복 보고서를 얼린 워크플로로 돌리는 것은 거부됨). 09-05 실측은 보고서 주행이
호출 23·45·13회, 액션 1개짜리 호출 7·20·4, 되읽기가 타이핑의 10배였다. 그런데 이 비용(적합도)은
원장에만 있고 모델의 눈에 없었다 — 육종(선택압)은 적합도가 보여야 한다. 이 측정기는 수치를 재고
보여주기만 한다. 무엇을 이름 붙이고 어떻게 줄일지는 모델의 몫이다(AI 의 일을 고정 프로그램으로
만들지 말 것).

★`scripts/ibl_composition_metrics.py`(조합률 *성분* 측정기, 08-21)와 다른 물음이다 — 그쪽은 문장의
모양(표꼬리/다단/팬아웃), 이쪽은 주행의 **호출 경제**(몇 번·몇 자·첫 프로그램이 맞았나).

읽는 것: data/world_pulse.db 의 episode_log + trajectory_event(ibl.started/ibl.finished).
쓰는 것: data/health/composition_metrics_<YYYY-MM-DD>.json 스냅샷(--no-json 으로 끔). 개인 명사
(질의어·경로·사용자 문장)는 출력에 넣지 않는다 — 수치·에피소드 id·머리(node:action)만.

에피소드별 수치:
  호출        = ibl.started 수(모델이 execute_ibl 을 부른 횟수)
  1액션 호출  = action_count == 1 인 호출(결과를 보려고 한 문장씩 따로 돌린 흔적)
  액션/호출   = action_count 평균
  타이핑      = code_chars 합 / 되읽기 = result_chars 합 / 되읽기 배율 = 되읽기 ÷ 타이핑
  실패        = ibl.finished.success == false
  첫 프로그램 = 첫 ibl.started 가 action_count ≥ 2 이고 그 ibl.finished 가 success (True/False/None=호출 없음)
  통화 부류 실패 = episode_log.log 의 통화 불일치·미기록 변수·타입 오류 메시지 매치 수
                   (정적 검사가 없앨 부류 — 09-05 실패의 대부분)
필터: --days N(14) · --source usage · --all-sources · 정기 보고서(`보고서 써줘` 로 끝나는 요청)는
      기본 제외(--include-reports 로 포함) — 지표는 **새 요청**에서 잰다.

사용: python3 scripts/ibl_composition_cost_metrics.py [--days 14] [--include-reports] [--all-sources]
                                                     [--json 경로 | --no-json] [--limit N]
"""
import argparse
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import boot_paths  # noqa: E402,F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "world_pulse.db")
HEALTH_DIR = os.path.join(ROOT, "data", "health")

# 통화 부류 실패 — 실행기가 내는 문장(정본은 엔진 쪽; 문장이 바뀌면 여기도 같이 고친다)
CURRENCY_FAIL_RE = re.compile(
    r"통화 종류가 같아야|같은 통화여야|아직 값을 기록하지 않았습니다|에는 string 이 와야|통화\(items/table\)로 파싱되지")
REPORT_TAIL = "보고서 써줘"      # 정기 보고서 요청의 꼬리(스케줄러가 내려보내는 문장)


# ─────────────────────────── 계산 ───────────────────────────

def is_report_request(user_message: Optional[str]) -> bool:
    return (user_message or "").strip().endswith(REPORT_TAIL)


def currency_failures(log: Optional[str]) -> int:
    return len(CURRENCY_FAIL_RE.findall(log or ""))


def _fmt_k(n: int) -> str:
    n = int(n or 0)
    if n < 1000:
        return f"{n}자"
    return f"{n / 1000:.1f}K자" if n < 10000 else f"{round(n / 1000)}K자"


def episode_metrics(conn: sqlite3.Connection, ep: Dict[str, Any]) -> Dict[str, Any]:
    """한 에피소드의 호출 경제. ibl.started 와 그 다음 ibl.finished 를 순서대로 짝짓는다
    (사이에 ibl.resumed 가 끼어도 무시; 짝 없는 started 는 미완으로 센다)."""
    rows = conn.execute(
        "SELECT kind, data FROM trajectory_event WHERE episode_id=? AND kind IN ('ibl.started','ibl.finished') "
        "ORDER BY event_seq", (ep["id"],)).fetchall()
    calls: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    for kind, data in rows:
        try:
            d = json.loads(data or "{}")
        except ValueError:
            d = {}
        if kind == "ibl.started":
            c = {"action_count": int(d.get("action_count") or 0), "actions": list(d.get("actions") or []),
                 "code_chars": int(d.get("code_chars") or 0), "pipes": int(d.get("pipes") or 0),
                 "result_chars": 0, "success": None, "elapsed_ms": 0}
            calls.append(c)
            pending.append(c)
        elif pending:
            c = pending.pop(0)
            c["result_chars"] = int(d.get("result_chars") or 0)
            c["success"] = bool(d.get("success", False))
            c["elapsed_ms"] = int(d.get("elapsed_ms") or 0)
    n = len(calls)
    typed = sum(c["code_chars"] for c in calls)
    reread = sum(c["result_chars"] for c in calls)
    failed = sum(1 for c in calls if c["success"] is False)
    single = sum(1 for c in calls if c["action_count"] == 1)
    first = calls[0] if calls else None
    first_ok: Optional[bool] = None
    if first is not None:
        first_ok = bool(first["action_count"] >= 2 and first["success"] is True)
    heads = Counter(a for c in calls for a in c["actions"])
    return {
        "id": ep["id"],
        "date": (ep.get("started_at") or "")[:10],
        "source": ep.get("source") or "",
        "report": is_report_request(ep.get("user_message")),
        "calls": n,
        "single_action_calls": single,
        "actions_per_call": round(sum(c["action_count"] for c in calls) / n, 2) if n else 0.0,
        "typed_chars": typed,
        "reread_chars": reread,
        "reread_ratio": round(reread / typed, 1) if typed else 0.0,
        "failed_calls": failed,
        "first_program_success": first_ok,
        "first_call_actions": list(first["actions"]) if first else [],
        "currency_failures": currency_failures(ep.get("log")),
        "total_ms": int(ep.get("total_ms") or 0),
        "top_heads": [h for h, _ in heads.most_common(5)],
    }


def load_episodes(conn: sqlite3.Connection, days: int = 14, source: Optional[str] = "usage",
                  exclude_reports: bool = True, now: Optional[datetime] = None,
                  limit: Optional[int] = None) -> List[Dict[str, Any]]:
    since = ((now or datetime.now()) - timedelta(days=days)).isoformat()
    sql = "SELECT id, started_at, source, user_message, log, total_ms FROM episode_log WHERE started_at >= ?"
    args: List[Any] = [since]
    if source:
        sql += " AND source = ?"
        args.append(source)
    sql += " ORDER BY id DESC"
    if limit:
        sql += " LIMIT ?"
        args.append(int(limit))
    out = []
    for r in conn.execute(sql, args).fetchall():
        ep = dict(zip(("id", "started_at", "source", "user_message", "log", "total_ms"), r))
        if exclude_reports and is_report_request(ep["user_message"]):
            continue
        out.append(ep)
    return out


def measure(conn: sqlite3.Connection, **kw) -> List[Dict[str, Any]]:
    return [episode_metrics(conn, ep) for ep in load_episodes(conn, **kw)]


def _median(xs: List[float]) -> float:
    return round(statistics.median(xs), 1) if xs else 0.0


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """집계 — IBL 호출이 하나라도 있던 에피소드만 분모(호출 0 은 따로 신고)."""
    with_calls = [r for r in rows if r["calls"] > 0]
    n = len(with_calls)
    fp = [r for r in with_calls if r["first_program_success"] is not None]
    fp_ok = sum(1 for r in fp if r["first_program_success"])
    return {
        "episodes": len(rows),
        "episodes_with_calls": n,
        "episodes_without_calls": len(rows) - n,
        "median": {
            "calls": _median([r["calls"] for r in with_calls]),
            "single_action_calls": _median([r["single_action_calls"] for r in with_calls]),
            "actions_per_call": _median([r["actions_per_call"] for r in with_calls]),
            "typed_chars": _median([r["typed_chars"] for r in with_calls]),
            "reread_chars": _median([r["reread_chars"] for r in with_calls]),
            "reread_ratio": _median([r["reread_ratio"] for r in with_calls if r["typed_chars"]]),
            "failed_calls": _median([r["failed_calls"] for r in with_calls]),
            "total_ms": _median([r["total_ms"] for r in with_calls]),
        },
        "sum": {
            "calls": sum(r["calls"] for r in with_calls),
            "single_action_calls": sum(r["single_action_calls"] for r in with_calls),
            "typed_chars": sum(r["typed_chars"] for r in with_calls),
            "reread_chars": sum(r["reread_chars"] for r in with_calls),
            "failed_calls": sum(r["failed_calls"] for r in with_calls),
            "currency_failures": sum(r["currency_failures"] for r in rows),
        },
        "first_program_success": {"ok": fp_ok, "of": len(fp),
                                  "rate": round(fp_ok / len(fp), 2) if fp else None},
        "single_action_share": round(sum(r["single_action_calls"] for r in with_calls)
                                     / max(1, sum(r["calls"] for r in with_calls)), 2),
    }


# ─────────────────────────── 표면 ───────────────────────────

def render_table(rows: List[Dict[str, Any]]) -> str:
    head = f"{'id':>5} {'날짜':10} {'호출':>4} {'1액션':>5} {'액션/호출':>8} {'타이핑':>8} {'되읽기':>8} {'배율':>5} {'실패':>4} {'통화':>4} {'첫프로그램':6} {'시간':>7}  첫 호출 머리"
    lines = [head, "-" * len(head)]
    for r in sorted(rows, key=lambda x: x["id"]):
        fp = {True: "✓", False: "✗", None: "–"}[r["first_program_success"]]
        secs = f"{r['total_ms'] / 1000:.0f}s"
        heads = ", ".join(r["first_call_actions"][:4]) + (" …" if len(r["first_call_actions"]) > 4 else "")
        lines.append(f"{r['id']:>5} {r['date']:10} {r['calls']:>4} {r['single_action_calls']:>5} "
                     f"{r['actions_per_call']:>8.2f} {_fmt_k(r['typed_chars']):>8} {_fmt_k(r['reread_chars']):>8} "
                     f"{r['reread_ratio']:>5.1f} {r['failed_calls']:>4} {r['currency_failures']:>4} {fp:^10} {secs:>7}  {heads}")
    return "\n".join(lines)


def render_summary(agg: Dict[str, Any]) -> str:
    m, s, fp = agg["median"], agg["sum"], agg["first_program_success"]
    return "\n".join([
        f"에피소드 {agg['episodes']} (IBL 호출 있음 {agg['episodes_with_calls']} · 없음 {agg['episodes_without_calls']})",
        f"중앙값  호출 {m['calls']} · 1액션 호출 {m['single_action_calls']} · 액션/호출 {m['actions_per_call']} · "
        f"타이핑 {_fmt_k(m['typed_chars'])} · 되읽기 {_fmt_k(m['reread_chars'])}(배율 {m['reread_ratio']}) · "
        f"실패 {m['failed_calls']} · 시간 {m['total_ms'] / 1000:.0f}s",
        f"합계    호출 {s['calls']} · 1액션 호출 {s['single_action_calls']}({agg['single_action_share']:.0%}) · "
        f"타이핑 {_fmt_k(s['typed_chars'])} · 되읽기 {_fmt_k(s['reread_chars'])} · 실패 {s['failed_calls']} · "
        f"통화 부류 실패 {s['currency_failures']}",
        f"첫 프로그램 성공  {fp['ok']}/{fp['of']}" + (f" ({fp['rate']:.0%})" if fp['rate'] is not None else ""),
    ])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--source", default="usage")
    ap.add_argument("--all-sources", action="store_true")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--exclude-reports", dest="exclude_reports", action="store_true", default=True)
    g.add_argument("--include-reports", dest="exclude_reports", action="store_false")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--json", default=None, help="스냅샷 경로(기본 data/health/composition_metrics_<날짜>.json)")
    ap.add_argument("--no-json", action="store_true")
    ap.add_argument("--db", default=DB)
    a = ap.parse_args(argv)

    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    try:
        rows = measure(conn, days=a.days, source=None if a.all_sources else a.source,
                       exclude_reports=a.exclude_reports, limit=a.limit)
    finally:
        conn.close()
    agg = aggregate(rows)
    print(f"# IBL 조합 비용 — 최근 {a.days}일 · source={'전체' if a.all_sources else a.source} · "
          f"정기 보고서 {'제외' if a.exclude_reports else '포함'}")
    print(render_table(rows))
    print()
    print(render_summary(agg))
    if not a.no_json:
        path = a.json or os.path.join(HEALTH_DIR, f"composition_metrics_{datetime.now().strftime('%Y-%m-%d')}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        snap = {"measured_at": datetime.now().isoformat(timespec="seconds"),
                "filter": {"days": a.days, "source": None if a.all_sources else a.source,
                           "exclude_reports": a.exclude_reports},
                "aggregate": agg,
                "episodes": [{k: v for k, v in r.items() if k != "source"} for r in rows]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
        print(f"\n스냅샷 → {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
