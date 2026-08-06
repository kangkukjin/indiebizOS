#!/usr/bin/env python3
"""seed_render_vocab.py — 슬라이드 2축 개편(2026-08-06) 해마 시드.

render 파라미터(native|image|html)·image_<톤> design_system 신어휘 용례를 심고,
낡은 관용구("무료로/가볍게" → layout 강제) 2건을 render:"html" 정본으로 교체한다.
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
1회 실행 후 ibl_distilled.json 이관은 별도(재학습 코퍼스).
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── render 파라미터 (렌더 방식 3택) ──
    ("가볍게 HTML 방식으로 슬라이드 한 장 만들어줘",
     '[self:slide]{op: "create", instruction: "핵심 명제를 한 장으로", render: "html"}'),
    ("나중에 글자를 직접 고칠 수 있게 HTML 렌더로 슬라이드 뽑아줘",
     '[self:slide]{op: "create", instruction: "핵심 요약 한 장", render: "html"}'),
    ("이미지+글자 합성 방식으로 슬라이드 만들어줘",
     '[self:slide]{op: "create", instruction: "핵심 개념을 일러스트와 함께", render: "image"}'),
    ("그림은 전면으로 깔고 글자는 선명하게 나오는 슬라이드로 해줘",
     '[self:slide]{op: "create", instruction: "핵심 은유를 전면 일러스트로", render: "image"}'),
    ("이 슬라이드만 통짜 이미지 말고 HTML로 다시 만들어줘",
     '[self:slide]{op: "edit", lecture_id: "lec_001", slide_id: "s3", instruction: "같은 내용을 HTML로", render: "html"}'),
    ("이 장은 그림 위에 글자 얹는 합성 방식으로 다시 뽑아줘",
     '[self:slide]{op: "edit", lecture_id: "lec_001", slide_id: "s2", instruction: "같은 명제를 일러스트 합성으로", render: "image"}'),
    ("슬라이드 렌더 방식을 이미지 온리로 해서 가장 예쁘게 한 장",
     '[self:slide]{op: "create", instruction: "표지 한 장", render: "native"}'),
    # ── image_<톤> 덱 (프리미엄 일러스트 톤) ──
    ("잉크+청사진 톤으로 강의 덱 만들어줘",
     '[self:lecture]{op: "create", title: "새 강의", design_system: "image_ink_blueprint"}'),
    ("시네마틱 3D 톤의 임팩트 있는 발표 덱 새로 만들어줘",
     '[self:lecture]{op: "create", title: "발표", design_system: "image_cinematic_3d"}'),
    ("아이소메트릭 도면 느낌 톤으로 시스템 구조 강의 덱 생성",
     '[self:lecture]{op: "create", title: "시스템 구조", design_system: "image_isometric"}'),
    ("라인아트 듀오톤으로 고급스러운 강의 덱 하나",
     '[self:lecture]{op: "create", title: "새 강의", design_system: "image_lineart_duotone"}'),
    ("빈티지북 톤인데 그림 전면에 글자 또렷한 합성 방식 덱으로",
     '[self:lecture]{op: "create", title: "새 강의", design_system: "image_vintage_book"}'),
]

# 낡은 관용구 교체 — 옛 답(layout 강제)도 동작은 하지만, 정본은 render:"html"
REPLACE = {
    "이미지 생성 없이 무료로 빠르게 슬라이드 한 장 뽑아줘":
        '[self:slide]{op: "create", instruction: "핵심 명제를 한 장으로", render: "html"}',
    "가볍게 텍스트로만 요약 카드 슬라이드 한 장 만들어줘":
        '[self:slide]{op: "create", instruction: "핵심 요약 카드 한 장", render: "html", aesthetic: "tech_minimal"}',
}

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"

# 교체: 옛 행 삭제 → 새 코드로 재추가 (vec0 는 DELETE→INSERT, _delete_examples 가 처리)
import sqlite3
from ibl_usage_db import DB_PATH
conn = sqlite3.connect(DB_PATH)
old_ids = []
for intent in REPLACE:
    rows = conn.execute("SELECT id FROM ibl_examples WHERE intent = ?", (intent,)).fetchall()
    old_ids += [r[0] for r in rows]
conn.close()
if old_ids:
    db._delete_examples(old_ids)
    print(f"낡은 관용구 삭제: {len(old_ids)}건 {old_ids}")

batch = [
    {"intent": i, "ibl_code": c, "nodes": "self", "category": "single",
     "difficulty": 1, "source": "manual_seed", "tags": "render,슬라이드,2축"}
    for i, c in NEW + list(REPLACE.items())
]
n = db.add_examples_batch(batch)
print(f"시드 추가: {n}건")

# 회상 프로브 (하이브리드 직행 확인)
for q in ["가볍게 HTML로 슬라이드 하나", "이미지+글자 방식으로 슬라이드", "잉크+청사진 톤 강의 덱", "무료로 빠르게 슬라이드 한 장"]:
    hits = db.search_hybrid(q, top_k=1)
    if hits:
        h = hits[0]
        print(f"  「{q}」 → {h.ibl_code[:85]}  (score={getattr(h, 'score', '?')})")
    else:
        print(f"  「{q}」 → (no hit)")
