"""세계의 기억의 회상 어댑터 — tree_recall.Store 구현 (공통 회상 설계 §5).

항목 = 세계 지도의 어휘(이름·뜻·별칭, 가지 = 분류 경로 앞 두 단), 가지 사전 = data/knowledge_catalog/branches.yaml
(찾는 말·요약·함께 볼 가지). 글자 채널은 기존 knowledge_catalog.search 를 그대로 쓴다 — 이름·별칭을 실제로
말한 경우의 정밀한 길. 지도(최상위 분야 목차)는 어휘에서 파생한다 — 손으로 쓰지 않는다.
"""
from collections import Counter
from pathlib import Path
from typing import List

from knowledge_catalog import load_snapshot, search
from tree_recall import Branch, Item, Store

DICT_PATH = "data/knowledge_catalog/branches.yaml"
BRANCH_DEPTH = 2
_cache = {}


def _dictionary(root: Path) -> dict:
    import yaml
    try:
        doc = yaml.safe_load((root / DICT_PATH).read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {}
    out = {}
    for row in doc.get("branches") or []:
        path = tuple(str(p) for p in (row.get("path") or []))
        if path:
            out[path] = {"gist": str(row.get("gist") or ""), "cues": str(row.get("cues") or ""),
                         "see_also": tuple(tuple(str(p) for p in s) for s in (row.get("see_also") or []))}
    return out


class WorldStore(Store):
    def __init__(self, root):
        self.root = Path(root)
        self.snapshot = load_snapshot(self.root)
        dict_bytes = (self.root / DICT_PATH).read_bytes() if (self.root / DICT_PATH).exists() else b""
        import hashlib
        self.key = "world"
        self._sig = self.snapshot.revision + hashlib.sha256(dict_bytes).hexdigest()[:12]

    def _built(self):
        hit = _cache.get("v")
        if hit and hit["sig"] == self._sig:
            return hit
        entries = self.snapshot.entries
        # 세부 주제까지 항목의 검색 문맥에 포함하되, 가지 선택은 앞 두 단에서 한다.
        items = [Item(id=e.id, path=tuple(e.path),
                      text=" ".join(p for p in (e.name, e.name, e.hint, e.scope_note) if p),
                      cues=" ".join(e.aliases), label=f"{'/'.join(e.path)}: {e.name}") for e in entries]
        entry = _dictionary(self.root)
        paths = sorted({it.path[:BRANCH_DEPTH] for it in items if it.path})
        branches = [Branch(path=p, **entry.get(p, {})) for p in paths]
        top = Counter(e.path[0] for e in entries if e.path)
        world_map = " · ".join(f"{name} {n}" for name, n in sorted(top.items()))
        hit = {"sig": self._sig, "items": items, "branches": branches, "map": world_map,
               "unknown": sorted("/".join(p) for p in entry if p not in set(paths))}
        _cache["v"] = hit
        return hit

    def items(self) -> List[Item]:
        return self._built()["items"]

    def branches(self) -> List[Branch]:
        return self._built()["branches"]

    def map_text(self) -> str:
        return self._built()["map"]

    def unknown_dictionary_paths(self) -> List[str]:
        return self._built()["unknown"]

    def lexical(self, query: str, items) -> List[str]:
        return [e.id for e, _ in search(self.root, self.snapshot, query)[0]]
