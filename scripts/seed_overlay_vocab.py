#!/usr/bin/env python3
"""seed_overlay_vocab.py — 슬라이드 '글자 얹기'(2026-08-09) 해마 시드.

image_edit 의 결정론 오버레이 파라미터(overlay_text/position/size/color/chip/clear)
용례를 심는다 — "이미지 구석에 한 줄만"이 이미지 모델 재생성이 아니라 이 경로로 직행하게.
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    ("슬라이드 이미지 오른쪽 아래에 '자료: 국토교통부 2026' 한 줄만 넣어줘. 그림은 그대로 두고",
     '[self:slide]{op: "image_edit", lecture_id: "lec_001", slide_id: "s3", overlay_text: "자료: 국토교통부 2026", overlay_position: "bottom-right"}'),
    ("이 슬라이드 그림 위에 출처 문구만 작게 얹어줘, 이미지 재생성은 하지 말고",
     '[self:slide]{op: "image_edit", lecture_id: "lec_001", slide_id: "s2", overlay_text: "출처: 통계청 KOSIS", overlay_position: "bottom-right", overlay_size: "small"}'),
    ("슬라이드 왼쪽 위에 '제3장 시장 개관' 큰 글씨로 배경칩 달아서 올려줘",
     '[self:slide]{op: "image_edit", lecture_id: "lec_001", slide_id: "s1", overlay_text: "제3장 시장 개관", overlay_position: "top-left", overlay_size: "large", overlay_chip: true}'),
    ("이미지 픽셀은 하나도 안 바꾸고 캡션 한 줄만 슬라이드 하단 가운데에 추가",
     '[self:slide]{op: "image_edit", lecture_id: "lec_001", slide_id: "s4", overlay_text: "2026년 상반기 기준", overlay_position: "bottom"}'),
    ("밝은 그림이라 어두운 글자로 슬라이드에 문구 얹어줘",
     '[self:slide]{op: "image_edit", lecture_id: "lec_001", slide_id: "s2", overlay_text: "핵심 요약", overlay_position: "top-right", overlay_color: "black"}'),
    ("슬라이드에 얹었던 글자 다 지우고 원본 그림으로 되돌려줘",
     '[self:slide]{op: "image_edit", lecture_id: "lec_001", slide_id: "s3", overlay_clear: true}'),
]

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"

batch = [
    {"intent": i, "ibl_code": c, "nodes": "self", "category": "single",
     "difficulty": 1, "source": "manual_seed", "tags": "overlay,글자얹기,슬라이드"}
    for i, c in NEW
]
n = db.add_examples_batch(batch)
print(f"시드 추가: {n}건")

# ibl_distilled 이관 (재학습 코퍼스)
dist_path = os.path.join(os.path.dirname(__file__), "..", "data", "training", "ibl_distilled.json")
with open(dist_path, encoding="utf-8") as f:
    dist = json.load(f)
have = {d.get("intent") for d in dist}
added = 0
for i, c in NEW:
    if i not in have:
        dist.append({"intent": i, "ibl_code": c, "nodes": "self", "category": "single",
                     "difficulty": 1, "source": "manual_seed"})
        added += 1
with open(dist_path, "w", encoding="utf-8") as f:
    json.dump(dist, f, ensure_ascii=False, indent=1)
print(f"ibl_distilled: +{added} → {len(dist)}")

# 회상 프로브 (하이브리드 직행 확인)
for q in ["슬라이드 이미지 구석에 한 줄만 넣어줘", "그림은 그대로 두고 출처 문구만 얹어",
          "슬라이드에 얹은 글자 지워줘", "슬라이드 제목 한 줄만 바꿔줘"]:
    hits = db.search_hybrid(q, top_k=1)
    if hits:
        h = hits[0]
        print(f"  「{q}」 → {h.ibl_code[:95]}  (score={getattr(h, 'score', '?')})")
    else:
        print(f"  「{q}」 → (no hit)")
