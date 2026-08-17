"""
Notebook Handler — [self:notebook] 근거 고정 질의 (op 분기)
==========================================================
노트북(이름 붙인 소스 묶음)에 넣고(add), 소스 안에서만 답하며 인용을 다는(ask) 어휘.
저장·색인·검색 = notebook_core.py (LLM 0) / 이 파일 = op 분기 + ask 생성 계약.

ask의 2층 방어 (설계 §4-3):
  1) 경량 AI 제약 생성 — 발췌만 근거·문장마다 [n] 인용·모름이면 NOT_IN_SOURCES
  2) 인용 후검증(결정론) — 답 속 [n]이 실제 전달한 발췌인지 검사, 무효 인용은 제거·집계.
     quote는 모델이 아니라 코드가 청크 원문에서 뽑는다 = 인용 환각 원리적 차단.

설계 정본: docs/NOTEBOOK_GROUNDED_QUERY_DESIGN.md
"""

import os
import re
import sys
import json

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

ASK_TOP_K = 12          # ask가 생성에 쓰는 발췌 수 (설계 §4-3)
SEARCH_TOP_K = 8        # search op 기본
QUOTE_CHARS = 160       # citations quote 길이 (청크 원문에서 결정론 추출)

NOT_IN_SOURCES_MARK = "NOT_IN_SOURCES"


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ── op 분기 함수 ─────────────────────────────────────────────────────────────

def _op_create(tool_input: dict, context) -> str:
    import notebook_core as core
    return _json(core.create_notebook(tool_input.get("name", ""), tool_input.get("note", "")))


def _op_add(tool_input: dict, context) -> str:
    import notebook_core as core
    return _json(core.add_source(
        tool_input.get("name", ""),
        path=tool_input.get("path", ""),
        text=tool_input.get("text", ""),
        title=tool_input.get("title", ""),
    ))


def _op_list(tool_input: dict, context) -> str:
    import notebook_core as core
    books = core.list_notebooks()
    items = [{
        "title": b["name"],
        "name": b["name"],
        "meta": f"소스 {b['source_count']} · 청크 {b['chunk_count']} · {str(b.get('updated_at') or '')[:16]}",
        "summary": b.get("note") or "",
        "url": "",
    } for b in books]
    return _json({"success": True, "count": len(books), "notebooks": books, "items": items,
                  "semantic": core.semantic_available(),
                  "message": "노트북이 없습니다. op:create로 만드세요." if not books else ""})


def _op_sources(tool_input: dict, context) -> str:
    import notebook_core as core
    out = core.list_sources(tool_input.get("name", ""))
    if out.get("success"):
        out["items"] = [{
            "title": s["title"],
            "meta": " · ".join(x for x in [
                f"#{s['id']}", s["kind"], f"청크 {s['chunk_count']}", s["status"],
                s.get("stale") and f"⚠️{s['stale']}"] if x),
            "summary": s.get("error") or (s.get("path") or ""),
            "source_id": s["id"],
            "notebook": out.get("notebook", ""),
            "url": "",
        } for s in out.get("sources", [])]
    return _json(out)


def _op_remove(tool_input: dict, context) -> str:
    import notebook_core as core
    return _json(core.remove_source(tool_input.get("name", ""), tool_input.get("source_id")))


def _op_delete(tool_input: dict, context) -> str:
    import notebook_core as core
    return _json(core.delete_notebook(tool_input.get("name", "")))


def _query_of(tool_input: dict) -> str:
    # 정본=query (param-canon 게이트). q/question 은 yaml aliases 로 정규화되지만
    # 직접 호출(reload 밖 경로) 방어로 여기서도 읽는다 (memory top_k/limit 선례).
    return (tool_input.get("query") or tool_input.get("q") or tool_input.get("question") or "").strip()


def _op_search(tool_input: dict, context) -> str:
    """생성 없는 발췌 검색 — LLM 0의 싼 경로. items 통화로 table 파이프 직결."""
    import notebook_core as core
    top_k = _as_int(tool_input.get("top_k"), SEARCH_TOP_K)
    out = core.search_chunks(tool_input.get("name", ""), _query_of(tool_input), top_k=top_k)
    if not out.get("success"):
        return _json(out)
    items = [{
        "title": r["source"],
        "meta": " · ".join(x for x in [r.get("loc") or "", f"score {r['score']}"] if x),
        "summary": (r["text"][:300] + ("…" if len(r["text"]) > 300 else "")),
        "source_id": r["source_id"],
        "chunk_id": r["id"],
        "url": "",
    } for r in out["results"]]
    return _json({"success": True, "notebook": out["notebook"], "search_type": out["search_type"],
                  "count": len(items), "items": items,
                  "message": "" if items else "이 노트북에서 관련 발췌를 찾지 못했습니다."})


def _op_ask(tool_input: dict, context) -> str:
    import notebook_core as core
    name = tool_input.get("name", "")
    question = _query_of(tool_input)
    if not question:
        return _json({"success": False, "error": "query(질문)가 필요합니다."})

    found = core.search_chunks(name, question, top_k=_as_int(tool_input.get("top_k"), ASK_TOP_K))
    if not found.get("success"):
        return _json(found)
    excerpts = found["results"]
    if not excerpts:
        msg = ("소스에서 관련 발췌를 찾지 못했습니다 — 소스가 이 주제를 다루지 않거나, "
               "op:sources로 색인 상태(indexing/error/stale)를 확인하세요.")
        return _json({"success": True, "notebook": found.get("notebook", name), "question": question,
                      "not_in_sources": True, "answer": "", "citations": [], "items": [],
                      "blocks": [{"type": "paragraph", "text": msg}], "message": msg})

    answer_raw, model_err = _grounded_generate(found.get("note", ""), question, excerpts)
    if model_err:
        # 생성층 죽어도 검색층은 살아 있다 — 발췌를 정직 반환 (침묵 실패 금지)
        return _json({"success": False, "error": f"근거 고정 생성 실패: {model_err}",
                      "notebook": found["notebook"], "question": question,
                      "items": _excerpt_items(excerpts),
                      "message": "생성은 실패했지만 검색된 발췌를 items로 반환합니다."})

    if NOT_IN_SOURCES_MARK in answer_raw:
        msg = "소스 안에 이 질문의 답이 없습니다(모델 판정). 일반 지식 답이 필요하면 노트북 밖에서 물어보세요."
        return _json({"success": True, "notebook": found["notebook"], "question": question,
                      "not_in_sources": True, "answer": "", "citations": [], "items": [],
                      "blocks": [{"type": "paragraph", "text": msg}],
                      "search_type": found["search_type"], "message": msg})

    answer, citations, dropped = _verify_citations(answer_raw, excerpts)
    # blocks = 계기(질문 탭)의 답변 렌더 IR — 데스크탑·원격 blocks 뷰가 그대로 그린다
    blocks = [{"type": "paragraph", "text": answer}]
    if citations:
        blocks.append({"type": "heading", "level": 4, "text": "인용"})
    return _json({"success": True, "notebook": found["notebook"], "question": question,
                  "not_in_sources": False, "answer": answer, "blocks": blocks,
                  "citations": citations, "items": _citation_items(citations),
                  "citation_dropped": dropped, "search_type": found["search_type"],
                  "excerpts_used": len(excerpts)})


def _as_int(v, default: int) -> int:
    try:
        n = int(v)
        return n if 0 < n <= 50 else default
    except (TypeError, ValueError):
        return default


# ── ask 내부: 제약 생성 + 인용 후검증 ────────────────────────────────────────

def _grounded_generate(note: str, question: str, excerpts: list):
    """경량 AI 1회 — 발췌만 근거로 [n] 인용 달린 답. 반환 (answer, error)."""
    try:
        from consciousness_agent import oneshot_ai_call
    except ImportError as e:
        return "", f"oneshot_ai_call 임포트 불가(백엔드 밖 실행?): {e}"

    lines = []
    for i, r in enumerate(excerpts, 1):
        loc = f" {r['loc']}" if r.get("loc") else ""
        lines.append(f"[{i}] ({r['source']}{loc}) {r['text']}")
    goal = f"\n이 노트북의 목적: {note}" if (note or "").strip() else ""

    system_prompt = (
        "당신은 근거 고정(grounded) 조수다. 규칙:\n"
        "1) 아래 '발췌'들만 근거로 답하라. 당신의 일반 지식으로 보충하지 마라.\n"
        "2) 답의 모든 주장 문장 끝에 근거 발췌 번호를 [1] [2] 형태로 달아라. 여러 발췌면 [1][3].\n"
        "3) 발췌들만으로 답할 수 없으면 다른 말 없이 정확히 NOT_IN_SOURCES 라고만 답하라. 추측 금지.\n"
        "4) 발췌에 없는 번호를 인용하지 마라.\n"
        "5) 답은 질문의 언어로, 간결하게."
    )
    prompt = f"질문: {question}{goal}\n\n발췌:\n" + "\n\n".join(lines)

    try:
        answer = oneshot_ai_call(prompt, system_prompt=system_prompt, role="classify")
    except Exception as e:
        return "", str(e)
    if not (answer or "").strip():
        return "", "경량 AI가 빈 응답을 반환"
    return answer.strip(), ""


_CITE_RE = re.compile(r"\[(\d{1,2})\]")


def _verify_citations(answer: str, excerpts: list):
    """결정론 후검증: 답 속 [n]이 전달한 발췌 범위 안인지. 무효 인용은 제거하고 센다.
    quote는 청크 원문에서 코드가 뽑는다 — 모델이 지어낸 인용문이 낄 자리가 없다."""
    valid = set(range(1, len(excerpts) + 1))
    used, dropped = [], 0

    def _sub(m):
        nonlocal dropped
        n = int(m.group(1))
        if n in valid:
            if n not in used:
                used.append(n)
            return m.group(0)
        dropped += 1
        return ""

    cleaned = _CITE_RE.sub(_sub, answer).strip()
    citations = []
    for n in used:
        r = excerpts[n - 1]
        citations.append({
            "n": n,
            "source": r["source"],
            "loc": r.get("loc") or "",
            "quote": r["text"][:QUOTE_CHARS] + ("…" if len(r["text"]) > QUOTE_CHARS else ""),
            "source_id": r["source_id"],
            "chunk_id": r["id"],
        })
    return cleaned, citations, dropped


def _citation_items(citations: list) -> list:
    return [{
        "title": f"[{c['n']}] {c['source']}",
        "meta": c["loc"],
        "summary": c["quote"],
        "url": "",
    } for c in citations]


def _excerpt_items(excerpts: list) -> list:
    return [{
        "title": r["source"],
        "meta": " · ".join(x for x in [r.get("loc") or "", f"score {r.get('score')}"] if x),
        "summary": r["text"][:300],
        "url": "",
    } for r in excerpts]


# ── 디스패처 (--check가 이 dict 키로 src.ops.values와 정확 비교 — 키 집합 주의) ──

_OP_DISPATCHERS = {
    "notebook_op": {
        "create": _op_create,
        "add": _op_add,
        "ask": _op_ask,
        "search": _op_search,
        "sources": _op_sources,
        "remove": _op_remove,
        "list": _op_list,
        "delete": _op_delete,
    },
}

_OP_DEFAULTS = {"notebook_op": "ask"}


def execute(tool_input: dict, context) -> str:
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = (tool_input.get("op") or "").strip() or _OP_DEFAULTS.get(tool_name, "")
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if fn is None:
                ops = "|".join(_OP_DISPATCHERS[tool_name])
                return _json({"success": False, "error": f"알 수 없는 op '{op}'. ({ops})"})
            return fn(tool_input, context)
        return _json({"success": False, "error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        return _json({"success": False, "error": str(e)})
