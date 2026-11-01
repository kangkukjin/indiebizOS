#!/usr/bin/env python3
"""개인 문서 검색 비교 실험 (106회차 base).

사용: python3 run_experiment.py --input <자료폴더> --queries <질문JSON> --output <결과JSON>
      [--methods <설정폴더>] [--qrels <qrels.json>] [--no-dense]

- 자료폴더: manifest.json(id,file) + docs/. manifest 가 없으면 docs/*.md|txt 파일명 앞부분('_' 앞)을 ID 로 쓴다.
- 질문JSON: [{id, question, type}, ...]
- 방법 설정: methods/*.json (읽기 전용으로 열고 실행 전후 SHA-256 을 결과에 기록·대조).
- 결과 results[]: question_id, method(이름@단위), top_docs(최대 3), answer(검색만 시험 → null),
  보조로 top_passages(문단 단위 근거 발췌)와 scores.
- 외부 통신 없음: 임베딩은 로컬 캐시 모델만(HF_HUB_OFFLINE=1). 모델이 없으면 dense/rrf 는 건너뛰고 skipped 에 기록.
"""
import argparse, glob, hashlib, json, math, os, re, sys, time
from collections import Counter

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

HERE = os.path.dirname(os.path.abspath(__file__))


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_docs(input_dir):
    man = os.path.join(input_dir, "manifest.json")
    docs = []
    if os.path.exists(man):
        for m in json.load(open(man, encoding="utf-8")):
            p = os.path.join(input_dir, "docs", m["file"])
            docs.append({"id": m["id"], "kind": m.get("kind"), "text": open(p, encoding="utf-8").read()})
    else:
        for p in sorted(glob.glob(os.path.join(input_dir, "docs", "*"))):
            if p.endswith((".md", ".txt")):
                docs.append({"id": os.path.basename(p).split("_")[0], "kind": None,
                             "text": open(p, encoding="utf-8").read()})
    return docs


def split_paragraphs(text, min_len=30):
    raw = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    out, carry = [], ""
    for c in raw:
        c = (carry + "\n" + c).strip() if carry else c
        if len(c) < min_len:
            carry = c
            continue
        out.append(c)
        carry = ""
    if carry:
        if out:
            out[-1] += "\n" + carry
        else:
            out.append(carry)
    return out


PUNCT = re.compile(r"[^\w가-힣]+")


def tok_whitespace(s, cfg):
    s = s.lower() if cfg.get("lowercase") else s
    toks = s.split()
    if cfg.get("strip_punct"):
        toks = [PUNCT.sub("", t) for t in toks]
    return [t for t in toks if t]


def tok_ko(s, cfg):
    s = s.lower() if cfg.get("lowercase") else s
    out = []
    for m in re.finditer(r"[가-힣]+|[a-z0-9_]+", s):
        w = m.group(0)
        if re.match(r"[가-힣]", w):
            if len(w) == 1:
                out.append(w)
            else:
                out.extend(w[i:i + 2] for i in range(len(w) - 1))
        else:
            out.append(w)
    return out


TOKENIZERS = {"whitespace": tok_whitespace, "hangul_char_bigram+ascii_word": tok_ko}


class BM25:
    def __init__(self, corpus_tokens, k1, b):
        self.k1, self.b = k1, b
        self.tf = [Counter(t) for t in corpus_tokens]
        self.dl = [len(t) for t in corpus_tokens]
        self.avgdl = sum(self.dl) / max(len(self.dl), 1)
        df = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(corpus_tokens)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}

    def scores(self, q):
        res = []
        for tf, dl in zip(self.tf, self.dl):
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            res.append(s)
        return res


_MODEL_CACHE = {}


def get_model(name):
    if name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer
        _MODEL_CACHE[name] = SentenceTransformer(name, local_files_only=True, device="cpu")
    return _MODEL_CACHE[name]


def units_for(docs, unit):
    """반환: [(doc_id, passage_text)]"""
    if unit == "doc":
        return [(d["id"], d["text"]) for d in docs]
    return [(d["id"], p) for d in docs for p in split_paragraphs(d["text"])]


def doc_ranking(unit_list, scores):
    best = {}
    for (did, txt), s in zip(unit_list, scores):
        if did not in best or s > best[did][0]:
            best[did] = (s, txt)
    return sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))


def run_method(cfg, docs, queries, unit, cache):
    key = (cfg["name"], unit)
    if key in cache:
        return cache[key]
    ul = units_for(docs, unit)
    out = {}
    if cfg["kind"] == "bm25":
        tk = TOKENIZERS[cfg["tokenizer"]]
        bm = BM25([tk(t, cfg) for _, t in ul], cfg["k1"], cfg["b"])
        for q in queries:
            out[q["id"]] = doc_ranking(ul, bm.scores(tk(q["question"], cfg)))
    elif cfg["kind"] == "dense":
        m = get_model(cfg["model"])
        E = m.encode([t for _, t in ul], normalize_embeddings=cfg.get("normalize", True), batch_size=16)
        Q = m.encode([q["question"] for q in queries], normalize_embeddings=cfg.get("normalize", True))
        sims = Q @ E.T
        for i, q in enumerate(queries):
            out[q["id"]] = doc_ranking(ul, [float(x) for x in sims[i]])
    cache[key] = out
    return out


def rrf(rankings, k):
    agg, ev = {}, {}
    for r in rankings:
        for rank, (did, (s, txt)) in enumerate(r, 1):
            agg[did] = agg.get(did, 0.0) + 1.0 / (k + rank)
            ev.setdefault(did, txt)
    return sorted(((d, (s, ev[d])) for d, s in agg.items()), key=lambda kv: (-kv[1][0], kv[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--methods", default=os.path.join(HERE, "methods"))
    ap.add_argument("--qrels", default=None, help="선택: 있으면 hit@3 를 덧붙인다")
    ap.add_argument("--no-dense", action="store_true")
    a = ap.parse_args()

    cfg_paths = sorted(glob.glob(os.path.join(a.methods, "*.json")))
    before = {os.path.basename(p): sha256(p) for p in cfg_paths}
    cfgs = {}
    units_cfg = {"units": ["doc", "paragraph"], "top_k": 3}
    for p in cfg_paths:
        c = json.load(open(p, encoding="utf-8"))
        if os.path.basename(p) == "units.json":
            units_cfg = c
        else:
            cfgs[c["name"]] = c

    docs = load_docs(a.input)
    queries = json.load(open(a.queries, encoding="utf-8"))
    topk = units_cfg.get("top_k", 3)
    results, skipped, cache = [], [], {}
    t0 = time.time()
    order = [n for n in ("bm25_ws", "bm25_ko", "dense_ko", "rrf_bm25ko_dense") if n in cfgs] + \
            [n for n in cfgs if n not in ("bm25_ws", "bm25_ko", "dense_ko", "rrf_bm25ko_dense")]
    for unit in units_cfg["units"]:
        for name in order:
            cfg = cfgs[name]
            try:
                if cfg["kind"] == "rrf":
                    comps = [run_method(cfgs[c], docs, queries, unit, cache) for c in cfg["components"]]
                    ranks = {q["id"]: rrf([c[q["id"]] for c in comps], cfg["k"]) for q in queries}
                else:
                    if cfg["kind"] == "dense" and a.no_dense:
                        raise RuntimeError("--no-dense")
                    ranks = run_method(cfg, docs, queries, unit, cache)
            except Exception as e:  # 모델 부재 등은 숨기지 않고 기록
                skipped.append({"method": f"{name}@{unit}", "reason": f"{type(e).__name__}: {e}"[:300]})
                continue
            for q in queries:
                r = ranks[q["id"]][:topk]
                results.append({
                    "question_id": q["id"], "method": f"{name}@{unit}",
                    "top_docs": [d for d, _ in r], "answer": None,
                    "scores": [round(s, 4) for _, (s, _) in r],
                    "top_passages": [txt[:240] for _, (_, txt) in r] if unit == "paragraph" else None,
                })
    after = {os.path.basename(p): sha256(p) for p in cfg_paths}

    out = {
        "run": {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "elapsed_s": round(time.time() - t0, 2),
                "input": os.path.abspath(a.input), "queries": os.path.abspath(a.queries),
                "n_docs": len(docs), "n_queries": len(queries),
                "doc_sha256": {d["id"]: hashlib.sha256(d["text"].encode()).hexdigest() for d in docs},
                "answer_policy": "검색만 시험 → answer=null"},
        "method_configs": cfgs, "units": units_cfg,
        "config_sha256_before": before, "config_sha256_after": after,
        "config_unchanged": before == after,
        "skipped": skipped, "results": results,
    }
    if a.qrels and os.path.exists(a.qrels):
        qr = json.load(open(a.qrels, encoding="utf-8"))["qrels"]
        ev = []
        for r in results:
            g = qr.get(r["question_id"])
            if not g:
                continue
            rel2 = [d for d, v in g.get("relevant", {}).items() if v >= 2]
            req = g.get("all_required", rel2[:1])
            ranks = {d: (r["top_docs"].index(d) + 1 if d in r["top_docs"] else None) for d in g.get("relevant", {})}
            ev.append({"question_id": r["question_id"], "method": r["method"],
                       "hit@3": (all(d in r["top_docs"] for d in req) if g.get("answerable") else None),
                       "relevant_ranks": ranks,
                       "distractors_in_top3": [d for d in g.get("distractors", []) if d in r["top_docs"]]})
        out["evaluation_against_self_qrels"] = ev
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({"output": a.output, "n_results": len(results), "skipped": skipped,
                      "config_unchanged": before == after}, ensure_ascii=False))
    if before != after:
        sys.exit(2)


if __name__ == "__main__":
    main()
