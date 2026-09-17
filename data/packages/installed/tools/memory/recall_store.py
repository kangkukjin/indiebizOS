"""심층기억의 회상 어댑터 — backend/datastore/tree_recall.Store 구현.

항목 = memories 행(가지 경로 = node), 가지 = 주제 트리의 노드 + 가지 문서의 사전 항목(memory_tree.entry_of).
읽기만 한다 — 회상 색인은 tree_recall 이 data/recall_index/ 에 따로 두며, 이 패키지의 memories_vec
(중복 판정·모순 스캔이 쓰는 해마 공간 벡터)는 건드리지 않는다.
"""
import hashlib
import sqlite3
from typing import List

import memory_tree
from tree_recall import Branch, Item, Store

ITEM_CHARS = 200            # 주입 표기의 건당 상한 — 넘으면 자르고 ‹#id› 로 전문을 연다


class DeepMemoryStore(Store):
    def __init__(self, db_path: str, before: str = ""):
        self.db_path = db_path
        self.before = before                                  # 평가용: 이 시각 이전에 생긴 기억만
        self.key = "deep_" + hashlib.sha256(db_path.encode("utf-8")).hexdigest()[:16] + ("_cut" if before else "")
        self._items = None
        self._branches = None

    def items(self) -> List[Item]:
        if self._items is None:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5)
            try:
                sql = "SELECT id, COALESCE(node,''), content, COALESCE(keywords,'') FROM memories"
                args = ()
                if self.before:
                    sql += " WHERE created_at < ?"
                    args = (self.before,)
                rows = conn.execute(sql, args).fetchall()
            finally:
                conn.close()
            self._items = [Item(id=str(i), path=tuple(p for p in node.split("/") if p), text=content or "",
                                cues=kw, label=_label(i, node, content or "")) for i, node, content, kw in rows]
        return self._items

    def branches(self) -> List[Branch]:
        if self._branches is None:
            out = []
            for row in memory_tree.map_lines(self.db_path):
                if not row["node"]:
                    continue
                e = memory_tree.entry_of(row["doc"]) if row.get("doc") else {"gist": "", "cues": "", "see_also": []}
                out.append(Branch(path=tuple(row["node"].split("/")), gist=e["gist"], cues=e["cues"],
                                  see_also=tuple(tuple(x.split("/")) for x in e["see_also"])))
            self._branches = out
        return self._branches


def _label(mem_id, node: str, content: str) -> str:
    text = " ".join(content.split())
    if len(text) > ITEM_CHARS:
        text = text[:ITEM_CHARS] + "…"
    return f"- [{node or '뿌리'}] {text} ‹#{mem_id}›"
