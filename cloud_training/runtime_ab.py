#!/usr/bin/env python3
"""런타임-충실 A/B — compare_models.py 가 "보류"를 낼 때 기각 전에 돌린다.

사용: .venv/bin/python3 cloud_training/runtime_ab.py <A_dir> <B_dir>
라이브 해마와 같은 공간을 잰다: 질의(raw) ↔ 저장 용례 전체(`_prepare_search_text`), 순수 의미 검색(FTS 제외).
  probe  = compare_models.PROBES 의 기대 액션이 상위 용례 코드에 있는가
  new    = 아래 NEW(최근 시딩 어휘 — 재학습마다 갈아 끼운다)
  heldout= 학습기 test 분할, 같은 intent 문장의 저장 행은 빼고(누설 차단) 패턴 일치
compare 의 desc·프로브는 액션 설명문 공간이라 런타임에 없는 손익을 잰다(2026-10-06: 프로브 −9 인데 여기선 동률).
"""
import sys, sqlite3, io, contextlib
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cloud_training")); sys.path.insert(0, str(REPO / "backend"))
import boot_paths  # noqa
with contextlib.redirect_stdout(io.StringIO()):
    import compare_models as C
    test_pairs, _, _ = C.build_split()
from datastore.ibl_usage_db import IBLUsageDB
from sentence_transformers import SentenceTransformer
import numpy as np
T = C.T
rows = sqlite3.connect(str(REPO / "data/ibl_usage.db")).execute("select intent, ibl_code from ibl_examples order by id").fetchall()
docs = [IBLUsageDB._prepare_search_text(i, c) for i, c in rows]
pats = [T.normalize_code_to_pattern(c) for _, c in rows]
intents = [i.strip() for i, _ in rows]
NEW = [("런처 프로젝트 목록 좀 보자","self:project"),("휴지통에 들어간 스위치 되살려줘","self:trash"),
 ("채팅방 하나 만들어서 에이전트 초대해","others:chat_room"),("이웃 창고에 새로 올라온 거 있나","others:warehouse"),
 ("내 창고 2레벨에 파일 올려줘","self:warehouse"),("메일 지금 바로 받아와","others:channel"),
 ("동영상을 mp4로 바꿔줘","self:media"),("위임한 작업 어디까지 됐는지 봐줘","self:task"),
 ("유튜브 패키지 켜줘","self:package"),("새 에이전트 하나 만들어서 검색만 시켜","others:agents"),
 ("즐겨찾기에 사이트 추가해줘","limbs:launch"),("영상에 자막 달려 있는지 봐줘","self:media")]
def run(path):
    m = SentenceTransformer(path, device="cpu")
    enc = lambda t: m.encode(t, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False, batch_size=64)
    D = enc(docs)
    def topk(qs, k=5, drop=None):
        S = enc(qs) @ D.T
        out = []
        for j in range(len(qs)):
            s = S[j].copy()
            if drop: s[[x for x, it in enumerate(intents) if it == drop[j]]] = -1
            out.append(np.argsort(-s)[:k])
        return out
    res = {}
    for name, qs in (("probe66", C.PROBES), ("new12", NEW)):
        tk = topk([q for q, _ in qs]); miss = []; h1 = h5 = 0
        for (q, exp), idx in zip(qs, tk):
            ok1 = exp in rows[idx[0]][1]; ok5 = any(exp in rows[i][1] for i in idx)
            h1 += ok1; h5 += ok5
            if not ok5: miss.append(q)
        res[name] = (h1, h5, len(qs), miss)
    # held-out: 같은 intent 문장의 저장 행을 빼고(누설 차단) 패턴 일치
    qs = [p[0] for p in test_pairs]; tk = topk(qs, drop=[q.strip() for q in qs]); h1 = h5 = 0
    for p, idx in zip(test_pairs, tk):
        h1 += pats[idx[0]] == p[1]; h5 += any(pats[i] == p[1] for i in idx)
    res["heldout"] = (h1, h5, len(qs), [])
    return res
for label, path in (("A", sys.argv[1]), ("B", sys.argv[2])):
    for k, (h1, h5, n, miss) in run(path).items():
        print(f"{label} {k:8} T1 {h1}/{n} ({100*h1/n:.1f})  T5 {h5}/{n} ({100*h5/n:.1f})" + (f"  T5실패: {miss}" if miss else ""))
