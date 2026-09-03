#!/usr/bin/env python3
"""seed_snapshot_row.py — 1행 스냅샷 병기(B36-2)로 새로 열린 문형 시드 (2026-08-24).

배경: 단일 개체 조회가 통화(items)를 안 내서 `[table:each]` 팬아웃이 원 행을 그대로
흘리던(passthrough_rows) 부류를 수리했다 — sense:video#info · sense:reverse_geocode ·
옛 탐색 낱말(2026-09-03 은퇴). 기계는 열렸는데 코퍼스에 용례가 없으면 모델은 옛 우회(`&` N중 병렬 +
머릿속 판별)를 계속 쓴다. 실사용에서 실제로 막혔던 자리를 그대로 접어 시드한다:
  · ep1874(유튜브 AI 팁 보고서) — 후보 18편의 upload_date 6개월 규칙을 `&` 8중으로 우회
  · ep1339(부동산 발굴 보고서) — 좌표 3곳 주소를 `&` 3중으로 우회
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401,E402
from ibl_usage_db import IBLUsageDB  # noqa: E402
from ibl.ibl_parser import parse as parse_ibl  # noqa: E402  시드 전 문법 검증

# (intent, code, nodes, category, tags)
NEW = [
    # ── sense:video#info — 6개월 규칙이 산문에서 문장 안 술어로 ──
    ("후보 영상들 업로드 날짜 확인해서 6개월 지난 건 빼줘",
     '[table:each]{items: [{id: "hLFnGFYJ3vs"}, {id: "wfMCWxJ-ri4"}, {id: "8ib4Qnh2HFE"}], '
     'do: "[sense:video]{op: \'info\', video_id: \'$it.id\'}"} '
     '>> [table:filter]{where: "upload_date >= 20260224"} '
     '>> [table:select]{columns: ["video_id", "title", "upload_date"]}',
     "table,sense", "media", "팬아웃,최신성,스냅샷"),
    ("이 영상들 제목이랑 조회수 한 표로 보여줘",
     '[table:each]{items: [{id: "jNQXAC9IVRw"}, {id: "hLFnGFYJ3vs"}], '
     'do: "[sense:video]{op: \'info\', video_id: \'$it.id\'}"} '
     '>> [table:select]{columns: ["title", "uploader", "view_count"]} '
     '>> [table:sort]{by: "view_count", desc: true}',
     "table,sense", "media", "팬아웃,스냅샷,정렬"),
    ("이 영상 정보를 표로 받아서 재생시간 10분 넘는 것만",
     '[sense:video]{op: "info", video_id: "8ib4Qnh2HFE"} '
     '>> [table:filter]{where: "duration >= 600"}',
     "sense,table", "media", "스냅샷,단건"),
    # ── sense:reverse_geocode — 좌표 여러 개를 한 문장으로 ──
    ("이 좌표 세 곳이 각각 어느 동인지 알려줘",
     '[table:each]{items: [{lat: 36.652605, lon: 127.455804}, {lat: 36.65024, lon: 127.456204}, '
     '{lat: 36.638056, lon: 127.432546}], '
     'do: "[sense:reverse_geocode]{lat: $it.lat, lon: $it.lon}"} '
     '>> [table:select]{columns: ["lat", "lon", "address"]}',
     "table,sense", "places", "팬아웃,역지오코딩,스냅샷"),
    ("매물 좌표들을 주소로 바꿔서 구별로 묶어줘",
     '[table:each]{items: [{lat: 37.5665, lon: 126.978}, {lat: 35.1796, lon: 129.0756}], '
     'do: "[sense:reverse_geocode]{lat: $it.lat, lon: $it.lon}"} '
     '>> [table:groupby]{by: "region_2depth"}',
     "table,sense", "places", "팬아웃,역지오코딩,집계"),
]


def main():
    db = IBLUsageDB()
    if hasattr(db, "_load_model_sync"):
        db._load_model_sync()   # ★벡터가 조용히 안 붙는 함정 방지
    bad = []
    for intent, code, *_ in NEW:
        try:
            parse_ibl(code)
        except Exception as e:
            bad.append((intent, f"{type(e).__name__}: {e}"))
    if bad:
        for i, e in bad:
            print(f"[문법 실패] {i}\n   {e}")
        raise SystemExit("문법 검증 실패 — 시드 중단")

    rows = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat,
             "difficulty": 2, "source": "seed_snapshot_row", "tags": t}
            for i, c, n, cat, t in NEW]
    added = db.add_examples_batch(rows)
    print(f"시드 {added}/{len(rows)}건 추가 (거부분은 소유-게이트)")


if __name__ == "__main__":
    main()
