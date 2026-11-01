#!/usr/bin/env python3
"""보조 분석: 정답 문단(qrels anchor 정규식)이 문단 순위 몇 위인지 방법별로 측정.
사용: python3 analyze_passages.py --input <자료폴더> --queries <질문JSON> --anchors <anchors.json> --output <json>
anchors.json: {question_id: {doc_id: 정규식}} — 결과 확인 전 qrels 의 anchor 를 정규식으로 옮긴 것."""
import argparse, json, os, re, importlib.util
H = os.path.dirname(os.path.abspath(__file__))
s = importlib.util.spec_from_file_location("rx", os.path.join(H, "run_experiment.py")); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
ap = argparse.ArgumentParser(); [ap.add_argument(x, required=True) for x in ("--input", "--queries", "--anchors", "--output")]
a = ap.parse_args()
docs = m.load_docs(a.input); Q = json.load(open(a.queries, encoding="utf-8")); A = json.load(open(a.anchors, encoding="utf-8"))
ul = m.units_for(docs, "paragraph")
cfg = {n: json.load(open(os.path.join(H, "methods", n + ".json"))) for n in ("bm25_ws", "bm25_ko", "dense_ko")}
rank_lists = {}
for n in ("bm25_ws", "bm25_ko"):
    c = cfg[n]; tk = m.TOKENIZERS[c["tokenizer"]]; bm = m.BM25([tk(t, c) for _, t in ul], c["k1"], c["b"])
    rank_lists[n] = {q["id"]: sorted(range(len(ul)), key=lambda i, sc=bm.scores(tk(q["question"], c)): -sc[i]) for q in Q}
mod = m.get_model(cfg["dense_ko"]["model"]); E = mod.encode([t for _, t in ul], normalize_embeddings=True); QE = mod.encode([q["question"] for q in Q], normalize_embeddings=True)
S = QE @ E.T
rank_lists["dense_ko"] = {q["id"]: sorted(range(len(ul)), key=lambda i, k=k: -S[k][i]) for k, q in enumerate(Q)}
rr = {}
for q in Q:
    agg = {}
    for n in ("bm25_ko", "dense_ko"):
        for r, i in enumerate(rank_lists[n][q["id"]], 1): agg[i] = agg.get(i, 0) + 1 / (60 + r)
    rr[q["id"]] = sorted(agg, key=lambda i: -agg[i])
rank_lists["rrf_bm25ko_dense"] = rr
out = {"n_paragraphs": len(ul), "rows": []}
for q in Q:
    for did, pat in A.get(q["id"], {}).items():
        idx = [i for i, (d, t) in enumerate(ul) if d == did and re.search(pat, t)]
        row = {"question_id": q["id"], "doc": did, "anchor": pat, "anchor_paragraphs": len(idx)}
        for n, L in rank_lists.items():
            row[n] = min(L[q["id"]].index(i) + 1 for i in idx) if idx else None
        out["rows"].append(row)
json.dump(out, open(a.output, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False))
