#!/usr/bin/env python3
"""forwarding_census_report.py — Phase 0 포워딩 인구조사 집계 (몸 독립 마이그레이션)

ibl_engine._census_log 가 쌓은 data/forwarding_census.jsonl 을 읽어
"어떤 어휘가 어느 방향으로 전선을 건너는가"를 요약한다.

답할 질문:
  1. 인지가 임의로 조립하는 크로스바디 어휘(why=auto/hub)가 실제로 얼마나 되나?
  2. 뜨거운 패턴 상위 N = Phase 4 진열(계기 부여) 후보
  3. 표면 분포(project 앱모드/수동모드 vs 인지 프로젝트) — 이미 결정화된 호출 vs 인지 조립

사용:
  python3 scripts/forwarding_census_report.py            # 전체 기간
  python3 scripts/forwarding_census_report.py --days 7   # 최근 7일
  python3 scripts/forwarding_census_report.py --file <다른 몸의 jsonl>  # 폰에서 가져온 파일 합산 등

stdlib 전용 (폰/윈도우 이식성 — fcntl 등 유닉스 전용 모듈 금지 지대).
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

BASE = os.environ.get("INDIEBIZ_BASE_PATH") or os.path.join(os.path.dirname(__file__), "..")
DEFAULT_PATH = os.path.join(BASE, "data", "forwarding_census.jsonl")


def load(paths, since_ts=None):
    rows = []
    for p in paths:
        if not os.path.exists(p):
            print(f"(없음: {p})", file=sys.stderr)
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if since_ts and r.get("ts", "") < since_ts:
                    continue
                rows.append(r)
    return rows


def bar(n, total, width=30):
    filled = int(width * n / total) if total else 0
    return "█" * filled + "·" * (width - filled)


def section(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}")


def top(counter, total, n=15):
    for key, cnt in counter.most_common(n):
        print(f"  {cnt:6d}  {bar(cnt, total)}  {key}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None, help="최근 N일만")
    ap.add_argument("--file", action="append", default=None,
                    help="jsonl 경로(복수 지정 가능 — 폰에서 pull 한 파일 합산)")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    since = None
    if args.days:
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - args.days * 86400))

    paths = args.file or [DEFAULT_PATH]
    rows = load(paths, since)
    if not rows:
        print("인구조사 기록이 아직 없습니다 — 크로스바디 포워딩이 한 번도 일어나지 않았거나 카운터 설치 이전입니다.")
        return
    total = len(rows)

    first, last = rows[0].get("ts", "?"), rows[-1].get("ts", "?")
    print(f"포워딩 인구조사: {total}건  ({first} ~ {last})")

    section("방향 (self → to)")
    top(Counter(f"{r.get('self')} → {r.get('to')}" for r in rows), total, args.top)

    section("어휘 (node:action) — 상위가 Phase 4 진열 후보")
    top(Counter(r.get("act") for r in rows), total, args.top)

    section("이유 (why: auto=능력 자동 / hub=@hub / alias=@명시)")
    top(Counter(r.get("why") for r in rows), total, args.top)

    section("표면 (project) — 앱모드/수동모드=결정화된 호출, 그 외=인지 조립")
    top(Counter(str(r.get("project")) for r in rows), total, args.top)

    section("인지-조립 크로스바디 어휘만 (why≠alias, project∉{앱모드,수동모드}) — Phase 3 절단 대상의 실측")
    cog = [r for r in rows if r.get("why") != "alias"
           and r.get("project") not in ("앱모드", "수동모드")]
    print(f"  {len(cog)}건 / 전체 {total}건 ({100.0 * len(cog) / total:.1f}%)")
    if cog:
        top(Counter(f"{r.get('self')} → {r.get('to')}  {r.get('act')}" for r in cog), len(cog), args.top)

    section("일별 추이")
    for day, cnt in sorted(Counter((r.get("ts") or "?")[:10] for r in rows).items()):
        print(f"  {day}  {cnt:6d}  {bar(cnt, total)}")


if __name__ == "__main__":
    main()
