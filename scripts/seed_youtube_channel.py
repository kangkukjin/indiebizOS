#!/usr/bin/env python3
"""`[sense:video]{op:"channel"}` 해마 용례를 시드한다.

채널 op는 구현·카탈로그·fixture가 먼저 추가됐지만 자연어→IBL 교재와 관측 인자
표면이 없었다. DB(즉시 회상)와 ibl_distilled.json(다음 재학습)을 함께 갱신한다.
반복 실행은 intent 기준으로 중복을 건너뛴다.

실행: .venv/bin/python scripts/seed_youtube_channel.py [--dry-run]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401


# intent, IBL code, nodes, category, tags
NEW = [
    ("@YouTube 채널의 최신 영상 3개 보여줘",
     '[sense:video]{op: "channel", handle: "@YouTube", limit: 3}',
     "sense", "media", "youtube,channel,handle,latest"),
    ("@YouTube 최근 업로드 3개",
     '[sense:video]{op: "channel", handle: "@YouTube", limit: 3}',
     "sense", "media", "youtube,channel,handle,latest,short"),
    ("유튜브 @핸들 최신 영상 보여줘",
     '[sense:video]{op: "channel", handle: "@YouTube", limit: 5}',
     "sense", "media", "youtube,channel,handle,latest,short"),
    ("@mkbhd 채널 최근 영상",
     '[sense:video]{op: "channel", handle: "@mkbhd", limit: 5}',
     "sense", "media", "youtube,channel,handle,latest,short"),
    ("유튜브에서 @mkbhd 채널 정보와 최근 업로드를 찾아줘",
     '[sense:video]{op: "channel", handle: "@mkbhd", limit: 5}',
     "sense", "media", "youtube,channel,handle,metadata"),
    ("이 유튜브 핸들이 어느 채널인지 확인해줘 @veritasium",
     '[sense:video]{op: "channel", handle: "@veritasium"}',
     "sense", "media", "youtube,channel,handle,resolve"),
    ("유튜브 채널 핸들로 채널 ID랑 이름을 알아내줘",
     '[sense:video]{op: "channel", handle: "@YouTube", limit: 1}',
     "sense", "media", "youtube,channel,handle,channel_id"),
    ("이 채널 URL의 최근 영상들을 보여줘 https://www.youtube.com/@YouTube",
     '[sense:video]{op: "channel", url: "https://www.youtube.com/@YouTube", limit: 5}',
     "sense", "media", "youtube,channel,url,latest"),
    ("https://www.youtube.com/@mkbhd 채널 메타데이터를 조회해줘",
     '[sense:video]{op: "channel", url: "https://www.youtube.com/@mkbhd", limit: 3}',
     "sense", "media", "youtube,channel,url,metadata"),
    ("이 유튜브 channel_id의 최신 업로드를 찾아줘 UCBR8-60-B28hp2BmDPdntcQ",
     '[sense:video]{op: "channel", channel_id: "UCBR8-60-B28hp2BmDPdntcQ", limit: 5}',
     "sense", "media", "youtube,channel,channel_id,latest"),
    ("채널 ID UCBR8-60-B28hp2BmDPdntcQ가 어떤 유튜브 채널인지 알려줘",
     '[sense:video]{op: "channel", channel_id: "UCBR8-60-B28hp2BmDPdntcQ", limit: 1}',
     "sense", "media", "youtube,channel,channel_id,resolve"),
    ("이 채널 최신 영상의 제목과 업로드 날짜만 표로 보여줘",
     '[sense:video]{op: "channel", handle: "@YouTube", limit: 10} '
     '>> [table:select]{columns: ["title", "upload_date", "url"]}',
     "sense,table", "media", "youtube,channel,handle,select,pipeline"),
    ("@veritasium 최근 영상 5개를 최신 날짜순으로 정리해줘",
     '[sense:video]{op: "channel", handle: "@veritasium", limit: 5} '
     '>> [table:sort]{by: "upload_date", desc: true}',
     "sense,table", "media", "youtube,channel,handle,sort,pipeline"),
    ("두 유튜브 채널의 최근 영상을 한 목록으로 합쳐줘",
     '[sense:video]{op: "channel", handle: "@mkbhd", limit: 3} & '
     '[sense:video]{op: "channel", handle: "@veritasium", limit: 3} '
     '>> [table:union]',
     "sense,table", "media", "youtube,channel,parallel,union"),
    ("이 채널의 최신 업로드 5개를 간단히 요약해줘",
     '[sense:video]{op: "channel", handle: "@YouTube", limit: 5} '
     '>> [table:brief]{instruction: "최신 업로드 주제 간단 요약"}',
     "sense,table", "media", "youtube,channel,brief,pipeline"),
    ("Find the latest videos from the YouTube channel @YouTube",
     '[sense:video]{op: "channel", handle: "@YouTube", limit: 5}',
     "sense", "media", "youtube,channel,handle,english"),
    ("Resolve this YouTube channel URL and list its three newest uploads",
     '[sense:video]{op: "channel", url: "https://www.youtube.com/@veritasium", limit: 3}',
     "sense", "media", "youtube,channel,url,english"),
]


def _preflight():
    import yaml
    from ibl.ibl_parser import parse

    registry = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    video = registry["nodes"]["sense"]["actions"]["video"]
    ops = set(video["ops"]["values"])
    if "channel" not in ops:
        raise SystemExit("sense:video op enum에 channel이 없음 — 시드 중단")
    for intent, code, *_ in NEW:
        try:
            parse(code)
        except Exception as exc:
            raise SystemExit(f"파싱 실패: {intent!r}: {exc}") from exc
    print(f"검증 통과 ✓ ({len(NEW)}건 파싱·sense:video#channel op 실존)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    _preflight()
    if args.dry_run:
        return

    from ibl_usage_db import IBLUsageDB

    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"
    with sqlite3.connect(ROOT / "data" / "ibl_usage.db") as conn:
        existing = {row[0] for row in conn.execute("SELECT intent FROM ibl_examples")}
    batch = [
        {"intent": intent, "ibl_code": code, "nodes": nodes, "category": category,
         "difficulty": 2, "source": "manual_seed", "tags": tags}
        for intent, code, nodes, category, tags in NEW if intent not in existing
    ]
    added = db.add_examples_batch(batch) if batch else 0
    print(f"해마 DB: +{added}건 (중복 스킵 {len(NEW) - len(batch)}건)")

    distilled_path = ROOT / "data" / "training" / "ibl_distilled.json"
    distilled = json.loads(distilled_path.read_text(encoding="utf-8"))
    have = {row.get("intent") for row in distilled}
    training_added = 0
    for intent, code, nodes, category, _tags in NEW:
        if intent in have:
            continue
        distilled.append({"intent": intent, "ibl_code": code, "nodes": nodes,
                          "category": category, "difficulty": 2, "source": "manual_seed"})
        training_added += 1
    distilled_path.write_text(
        json.dumps(distilled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"재학습 JSON: +{training_added}건 → {len(distilled)}건")


if __name__ == "__main__":
    main()
