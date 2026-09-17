"""트리 기억의 공통 회상 — 가지 먼저, 그 안에서 고르고, 밖에서 하나 보충한다.

정본 설계: docs/TREE_MEMORY_RECALL_COMMON_DESIGN_2026_09_17.md (§5). 심층기억과 세계의 기억이 같은 함수를 쓴다.
블로그 검색에서 확인된 방식이다 — 엔진은 가지의 *라벨*을 알고(항목 벡터에 경로가 실린다), 사전은 가지의
*이유*를 안다(요약·찾는 말·함께 볼 가지). 이 모듈은 저장소를 모른다: 항목·가지는 어댑터(Store)가 준다.

색인은 파생물이다(`data/recall_index/`, git 밖). 항목·가지 텍스트의 해시가 바뀐 것만 다시 임베딩한다.
인코더는 하나(`jhgan/ko-sroberta-multitask`, 블로그와 동일) — 해마 모델은 재학습마다 공간이 바뀌고
세계 어휘에서 나빴다(실측 13/24 대 20/24). ★질문 경로에서 모델을 올리지 않는다: 적재·대량 색인은
백그라운드 스레드가 하고, 그동안 회상은 `unavailable`/`indexing` 으로 조용히 빠진다.
"""
import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

MODEL_NAME = "jhgan/ko-sroberta-multitask"
TEXT_VERSION = "1"          # 항목·가지 텍스트 조립 규칙의 판 — 바꾸면 전부 재색인(블로그 EMBEDDING_VERSION 과 같은 뜻)
INLINE_SYNC_MAX = 12        # 이만큼까지의 변경분은 그 자리에서 임베딩한다. 넘으면 백그라운드.
RRF_K = 60
LABEL_REPEAT = 2

_lock = threading.Lock()
_model = None
_model_state = "idle"       # idle → loading → ready | failed
_cache: Dict[str, Dict[str, Any]] = {}      # store.key → {"sig", "item_ids", "item_vecs", "branch_paths", "branch_vecs"}
_syncing: set = set()


# ─────────────────────────── 단위 ───────────────────────────

@dataclass(frozen=True)
class Item:
    id: str
    path: Tuple[str, ...]            # 가지 경로 하나
    text: str                        # 본문(심층기억) 또는 이름+뜻(세계의 기억)
    cues: str = ""                   # 찾는 말 — 키워드·별칭
    label: str = ""                  # 주입할 때 보일 짧은 표기(없으면 text)


@dataclass(frozen=True)
class Branch:
    path: Tuple[str, ...]
    gist: str = ""                   # 요약 — 지도에 실린다
    cues: str = ""                   # 찾는 말 — 일상 표현. 연상 기준 가지는 비운다
    see_also: Tuple[Tuple[str, ...], ...] = field(default_factory=tuple)   # 함께 볼 가지


class Store:
    """어댑터 계약. key 는 색인 파일 이름이 된다(경로 문자 금지)."""
    key: str = ""

    def items(self) -> List[Item]:
        raise NotImplementedError

    def branches(self) -> List[Branch]:
        raise NotImplementedError

    def lexical(self, query: str, items: Sequence[Item]) -> List[str]:
        """글자 검색 순위(항목 id). 기본은 어절 접두 일치 — 조사 붙은 어절을 놓치지 않게."""
        return lexical_rank(query, items)


# ─────────────────────────── 텍스트 ───────────────────────────

def item_text(it: Item) -> str:
    leaf = it.path[-1] if it.path else ""
    parts = [leaf] * LABEL_REPEAT + ["/".join(it.path), it.text, it.cues]
    return " ".join(p for p in parts if p)


def branch_text(b: Branch) -> str:
    leaf = b.path[-1] if b.path else ""
    return " ".join(p for p in [leaf] * LABEL_REPEAT + ["/".join(b.path), b.gist, b.cues] if p)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


def lexical_rank(query: str, items: Sequence[Item]) -> List[str]:
    q = {t.lower() for t in _TOKEN_RE.findall(query or "")}
    if not q:
        return []
    scored = []
    for it in items:
        toks = {t.lower() for t in _TOKEN_RE.findall(f"{it.text} {it.cues} {' '.join(it.path)}")}
        hit = sum(1 for a in q if any(b.startswith(a) or a.startswith(b) for b in toks))
        if hit:
            scored.append((-hit, it.id))
    return [i for _, i in sorted(scored)]


def under(path: Sequence[str], branch: Sequence[str]) -> bool:
    return tuple(path[:len(branch)]) == tuple(branch)


# ─────────────────────────── 인코더 ───────────────────────────

def _load_model():
    global _model, _model_state
    try:
        from sentence_transformers import SentenceTransformer
        try:
            from runtime_work import service_scope
        except Exception:                                   # 독립 실행(스크립트·시험)
            from contextlib import nullcontext as service_scope
        with service_scope():
            try:
                _model = SentenceTransformer(MODEL_NAME, local_files_only=True)
            except Exception:
                _model = SentenceTransformer(MODEL_NAME)
        _model_state = "ready"
        print(f"[tree_recall] 인코더 적재 완료: {MODEL_NAME}")
    except Exception as e:                                  # noqa: BLE001
        _model_state = "failed"
        print(f"[tree_recall] 인코더 적재 실패(글자 채널만): {e}")


def ensure_model(block: bool = False) -> bool:
    """적재를 시작만 한다. block=True 는 빌드 스크립트·시험용."""
    global _model_state
    with _lock:
        if _model_state == "idle":
            _model_state = "loading"
            t = threading.Thread(target=_load_model, daemon=True, name="tree-recall-encoder")
            t.start()
        else:
            t = None
    if block:
        if t is not None:
            t.join()
        else:
            import time
            while _model_state == "loading":
                time.sleep(0.05)
    return _model_state == "ready"


def model(block: bool = False):
    """인코더 객체(없으면 None). 심층기억의 중복 판정 벡터(memory_db)도 같은 모델을 쓴다 — 기억은 재학습되는 모델에 걸지 않는다."""
    return _model if ensure_model(block=block) else None


def _encode(texts: List[str]):
    import numpy as np
    if not texts:
        return np.zeros((0, 768), dtype="float32")
    return _model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False).astype("float32")


# ─────────────────────────── 색인 ───────────────────────────

def _index_dir() -> str:
    base = os.environ.get("INDIEBIZ_RECALL_INDEX_DIR")
    if base:
        return base
    from runtime_utils import get_base_path
    return os.path.join(str(get_base_path()), "data", "recall_index")


def _index_paths(key: str) -> Tuple[str, str]:
    d = _index_dir()
    return os.path.join(d, f"{key}.npz"), os.path.join(d, f"{key}.json")


def _load_disk(key: str) -> Dict[str, Any]:
    import numpy as np
    npz, meta = _index_paths(key)
    try:
        with open(meta, encoding="utf-8") as f:
            m = json.load(f)
        if m.get("model") != MODEL_NAME or m.get("text_version") != TEXT_VERSION:
            return {}
        arr = np.load(npz)
        return {"hashes": m["hashes"], "vecs": arr["vecs"]}
    except Exception:
        return {}


def _save_disk(key: str, hashes: List[str], vecs) -> None:
    import numpy as np
    npz, meta = _index_paths(key)
    os.makedirs(os.path.dirname(npz), exist_ok=True)
    tmp = npz + ".tmp.npz"
    np.savez(tmp, vecs=vecs)
    os.replace(tmp, npz)
    with open(meta + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"model": MODEL_NAME, "text_version": TEXT_VERSION, "hashes": hashes}, f)
    os.replace(meta + ".tmp", meta)


def _build(store: Store, items: List[Item], branches: List[Branch], allow: int) -> Optional[Dict[str, Any]]:
    """텍스트 해시로 벡터를 재사용하고 모자란 것만 임베딩. 모자란 수가 allow 를 넘으면 None."""
    import numpy as np
    texts = [item_text(i) for i in items] + [branch_text(b) for b in branches]
    hashes = [_sha(t) for t in texts]
    sig = _sha("|".join(hashes))
    hit = _cache.get(store.key)
    if hit and hit["sig"] == sig:
        return hit
    disk = _load_disk(store.key)
    known = {h: disk["vecs"][k] for k, h in enumerate(disk.get("hashes", []))} if disk else {}
    missing = [k for k, h in enumerate(hashes) if h not in known]
    if len(missing) > allow:
        return None
    if missing:
        new = _encode([texts[k] for k in missing])
        for k, v in zip(missing, new):
            known[hashes[k]] = v
    vecs = np.stack([known[h] for h in hashes]) if hashes else np.zeros((0, 768), dtype="float32")
    if missing or not disk or len(disk.get("hashes", [])) != len(hashes):
        _save_disk(store.key, hashes, vecs)
    n = len(items)
    iv, dv = vecs[:n], vecs[n:]
    # 가지 벡터 = 사전 텍스트 + 소속 항목 평균(실측에서 가장 나았던 조합). 소속이 없으면 사전만.
    bv = []
    for k, b in enumerate(branches):
        ix = [j for j, it in enumerate(items) if under(it.path, b.path)]
        v = dv[k] + (iv[ix].mean(0) if ix else 0)
        norm = float(np.linalg.norm(v)) or 1.0
        bv.append(v / norm)
    out = {"sig": sig, "item_vecs": iv, "branch_vecs": np.stack(bv) if bv else np.zeros((0, 768), dtype="float32")}
    _cache[store.key] = out
    return out


def _sync_background(store: Store) -> None:
    def run():
        try:
            ensure_model(block=True)
            if _model_state == "ready":
                _build(store, store.items(), store.branches(), allow=10 ** 9)
        except Exception as e:                              # noqa: BLE001
            print(f"[tree_recall] 색인 동기화 실패({store.key}): {e}")
        finally:
            _syncing.discard(store.key)
    if store.key in _syncing:
        return
    _syncing.add(store.key)
    threading.Thread(target=run, daemon=True, name=f"tree-recall-sync-{store.key[:12]}").start()


def build_now(store: Store) -> Dict[str, Any]:
    """빌드 스크립트·시험용 동기 색인."""
    ensure_model(block=True)
    if _model_state != "ready":
        raise RuntimeError("encoder unavailable")
    return _build(store, store.items(), store.branches(), allow=10 ** 9)


# ─────────────────────────── 회상 ───────────────────────────

def _rrf(orders: Sequence[Sequence[str]]) -> List[str]:
    score: Dict[str, float] = {}
    for order in orders:
        for r, i in enumerate(order):
            score[i] = score.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
    return sorted(score, key=lambda i: -score[i])


def recall(store: Store, query: str, *, n_branches: int = 2, k_in: int = 2, k_out: int = 1,
           branch_filter: Optional[Sequence[Sequence[str]]] = None, wait: bool = False) -> Dict[str, Any]:
    """가지 n개 → 그 안 k_in + 밖 k_out. branch_filter 를 주면 가지 고르기를 건너뛴다(AI 의 직접 검색).

    status: ok | empty | unavailable(인코더 없음) | indexing(색인 동기화 중) | lexical_only
    """
    import numpy as np
    items, branches = store.items(), store.branches()
    out = {"status": "empty", "branches": [], "items": [], "outside": [], "outside_beats_inside": False}
    if not items or not (query or "").strip():
        return out
    lex = store.lexical(query, items)
    idx = None
    if ensure_model(block=wait):
        idx = _build(store, items, branches, allow=10 ** 9 if wait else INLINE_SYNC_MAX)
        if idx is None:
            _sync_background(store)
            out["status"] = "indexing"
    else:
        out["status"] = "unavailable"
    by_id = {it.id: it for it in items}
    if idx is None:
        # 의미 채널 없이: 글자로 잡힌 것만. 가지 고르기는 하지 않는다(라벨만으로 가지를 단정하지 않는다).
        picked = [by_id[i] for i in lex[:k_in + k_out] if i in by_id]
        if picked:
            out.update(status="lexical_only", items=picked)
        return out
    q = _encode([query[:2000]])[0]
    sims = idx["item_vecs"] @ q
    sem = [items[k].id for k in np.argsort(-sims)[:50]]
    fused = _rrf([sem, lex[:50]])
    if branch_filter is not None:
        chosen = [tuple(b) for b in branch_filter]
    else:
        order = np.argsort(-(idx["branch_vecs"] @ q))[:n_branches] if len(branches) else []
        chosen = [branches[k].path for k in order]
        extra = [s for k in order for s in branches[k].see_also if s not in chosen]
        chosen += extra[:n_branches]                         # 함께 볼 가지 — 사전이 아는 흩어짐
    inside = [i for i in fused if any(under(by_id[i].path, b) for b in chosen)]
    if len(inside) < k_in:                                    # 융합 상위 50 밖에 있는 가지 안 항목
        rest = sorted((k for k, it in enumerate(items)
                       if it.id not in inside and any(under(it.path, b) for b in chosen)), key=lambda k: -sims[k])
        inside += [items[k].id for k in rest]
    outside = [i for i in fused if i not in set(inside)]
    pos = {i: r for r, i in enumerate(fused)}
    pick_in, pick_out = inside[:k_in], outside[:k_out]
    beats = bool(pick_in and pick_out and pos.get(pick_out[0], 10 ** 6) < min(pos.get(i, 10 ** 6) for i in pick_in))
    out.update(status="ok", branches=chosen, items=[by_id[i] for i in pick_in],
               outside=[by_id[i] for i in pick_out], outside_beats_inside=beats)
    return out


def search(store: Store, query: str, *, limit: int = 10, min_sim: float = 0.0,
           branch_filter: Optional[Sequence[Sequence[str]]] = None, wait: bool = True) -> Dict[str, Any]:
    """AI 가 직접 부르는 조회 — 가지 고르기 없이 전체(또는 branch_filter 안)를 의미+글자 융합 순위로.

    자동 주입(recall)과 같은 항목 벡터·같은 융합을 쓴다. 부른 쪽이 기다리는 호출이므로 기본은 wait=True
    (인코더 적재·첫 색인을 그 자리에서). min_sim 미만은 의미 채널에서 빠진다 — 결과가 비면 빈 목록이 정직한 답이다.
    status: ok | empty | unavailable
    """
    import numpy as np
    items = store.items()
    if not items or not (query or "").strip():
        return {"status": "empty", "ids": []}
    if not ensure_model(block=wait):
        return {"status": "unavailable", "ids": []}
    idx = _build(store, items, store.branches(), allow=10 ** 9 if wait else INLINE_SYNC_MAX)
    if idx is None:
        _sync_background(store)
        return {"status": "unavailable", "ids": []}
    q = _encode([query[:2000]])[0]
    sims = idx["item_vecs"] @ q
    keep = [k for k, it in enumerate(items)
            if branch_filter is None or any(under(it.path, tuple(b)) for b in branch_filter)]
    allowed = {items[k].id for k in keep}
    sem = [items[k].id for k in sorted(keep, key=lambda k: -sims[k])[:max(50, limit * 3)] if sims[k] >= min_sim]
    lex = [i for i in store.lexical(query, items) if i in allowed][:50]
    return {"status": "ok", "ids": _rrf([sem, lex])[:limit]}

