"""포식 기억의 장소 찾기 어댑터 — tree_recall.Store 구현.

포식 기억은 "장소를 주면 그 장소의 전부"다. 고르는 일이 끼는 곳은 **장소를 모를 때 어느 장소인가**를 찾는 앞 단계 하나뿐이고
(심층기억의 가지 고르기와 같은 부류), 이 어댑터가 그 단계다. 그래서 항목 = 단언이 아니라 **장소 하나**:
  id = 주소(locus) · path = 주소의 단들(끝 이름이 항목 텍스트에 두 번 실린다) · text = 그 장소의 단언들(정체 먼저) ·
  cues = 그 장소 문서의 `찾는 말:` 줄(주인이 그 장소를 부를 법한 일상 표현 — 없으면 비어 있다)
가지는 두지 않는다 — 장소의 트리는 분류가 아니라 주소라서, 가지를 먼저 고를 이유가 없다(search 만 쓴다).
docs/FORAGE_MEMORY_AUDIT_2026_09_18.md §6.
"""
import os
import re
from typing import Dict, List

from tree_recall import Item, Store

TEXT_MAX = 700
_KIND_ORDER = {"identity": 0, "convention": 1, "substrate": 2, "dead_branch": 3}
_CUES_RE = re.compile(r"(?m)^찾는 말:\s*(.+?)\s*$")
_CAND_RE = re.compile(r'찾는 말 후보: "(.+?)"')   # 정리 패스가 되먹인 질문(forage_consolidation.fold_place_trail)
_cache: Dict[str, object] = {}


def cues_of(doc_path: str) -> str:
    """장소 문서의 찾는 말 — 머리의 `찾는 말:` 줄(사람·조사하는 AI 가 쓴다) + `## 갱신 기록` 의 `찾는 말 후보` 줄(되먹임)."""
    try:
        text = open(doc_path, encoding="utf-8").read()
    except OSError:
        return ""
    head = text.split("\n## ", 1)[0]
    return " ".join(m.strip() for m in _CUES_RE.findall(head) + _CAND_RE.findall(text))


class ForageStore(Store):
    key = "forage_places"

    def _sig(self) -> str:
        import forage_memory as FM
        import forage_doc as FD
        try:
            db = os.path.getmtime(os.path.abspath(FM._DB_PATH))
        except OSError:
            db = 0
        docs = max((os.path.getmtime(p) for p, _b, _r in FD._scan_docs()), default=0)
        return f"{db}:{docs}"

    def items(self) -> List[Item]:
        import forage_memory as FM
        import forage_doc as FD
        sig = self._sig()
        if _cache.get("sig") == sig:
            return _cache["items"]  # type: ignore[return-value]
        conn = FM._connect()
        try:
            rows = [dict(r) for r in conn.execute("SELECT body, locus, kind, claim, confidence FROM forage_map")]
        finally:
            conn.close()
        cues = {}
        for p, b, r in FD._scan_docs():
            c = cues_of(p)
            if c:
                cues[FM.place_id(b, r)] = c
        by_place: Dict[str, List[dict]] = {}
        for r in rows:
            by_place.setdefault(FM.place_id(r["body"], r["locus"]), []).append(r)
        items = []
        for pid, rs in by_place.items():
            rs.sort(key=lambda r: (_KIND_ORDER.get(r["kind"], 9), -float(r["confidence"] or 0)))
            text = " / ".join(r["claim"].split(" ‹", 1)[0] for r in rs)[:TEXT_MAX]
            parts = tuple(p for p in re.split(r"[/:]", pid) if p)
            items.append(Item(id=pid, path=parts, text=text, cues=cues.get(pid, "")))
        _cache.update(sig=sig, items=items)
        return items

    def branches(self):
        return []
