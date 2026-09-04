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
from runtime_utils import expand_body_path  # 경로 펼침 단일 해소점 (~workspace/·~)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

ASK_TOP_K = 12          # ask가 생성에 쓰는 발췌 수 (설계 §4-3)
SEARCH_TOP_K = 8        # search op 기본
QUOTE_CHARS = 160       # citations quote 길이 (청크 원문에서 결정론 추출)

NOT_IN_SOURCES_MARK = "NOT_IN_SOURCES"
DIGEST_NEEDED_MARK = "DIGEST_NEEDED"   # ask 판정기가 "발췌 단편으론 소개·개요 불가, 소스 전체를 읽어라" 고 넘기는 표식
DIGEST_WINDOW_CHARS = 5000             # 구간 요지 한 번에 읽는 분량(경량 모델)


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ── op 분기 함수 ─────────────────────────────────────────────────────────────

# ── 포식 기억(노트북 = 문서 더미 = 폴더와 같은 대상, 2026-09-03 사용자 판정 "노트북에도 포식기억 붙여.
#    등록하면 자동으로 기억트리가 생겨나게") — 조사는 AI 몫(시스템 AI 위임), 여기는 방아쇠·되읽기만 ──
_SURVEY_DEBOUNCE_S = 600   # 소스를 연달아 넣을 때 조사 위임을 한 번으로 접는다


def _memory_body(name: str) -> str:
    return f"notebook:{name}"


def _notebook_memory_text(name: str, cap: int = 4000) -> str:
    """이 노트북의 포식 기억 문서(있으면) — 산문·단언 절 전부, cap 자 안."""
    try:
        import forage_doc
        p = forage_doc.doc_path_at(_memory_body(name), _memory_body(name))
        if not os.path.exists(p):
            return ""
        text = open(p, encoding="utf-8").read()
        return text if len(text) <= cap else text[:cap] + "\n…(생략)"
    except Exception:
        return ""


def _schedule_survey(name: str, context, why: str) -> dict:
    """등록(create/add) 뒤 시스템 AI 에게 '노트북 조사'를 fire-and-forget 위임. 시험·훈련 출처는 제외, 10분 디바운스."""
    origin = str(getattr(context, "origin", "") or "")
    if origin in ("test", "training"):
        return {"queued": False, "reason": f"origin={origin}"}
    import time
    import notebook_core as core
    mark_dir = core.NOTEBOOK_DIR / ".survey_pending"
    mark_dir.mkdir(parents=True, exist_ok=True)
    mark = mark_dir / (re.sub(r"[^\w가-힣.-]+", "_", name) + ".txt")
    if mark.exists() and time.time() - mark.stat().st_mtime < _SURVEY_DEBOUNCE_S:
        return {"queued": False, "reason": "debounced"}
    mark.write_text(str(time.time()))
    body = _memory_body(name)
    msg = (f"노트북 조사: '{name}' 노트북의 포식 기억을 만들어라(이미 있으면 갱신). "
           f"read_guide 로 folder_survey 가이드의 '노트북(문서 더미)' 절을 따른다. "
           f"소스 목록은 [self:notebook]{{op: \"sources\", name: \"{name}\"}}, 기존 기억과 문서 위치는 "
           f"[self:forage]{{op: \"recall\", body: \"{body}\", locus: \"{body}\"}} 의 doc. "
           f"단언은 [self:forage]{{op: \"note\", body: \"{body}\", locus: \"{body}\" 또는 \"{body}/<소스 제목>\", kind, claim}} "
           f"— 노트북 전체의 정체 단언에는 territory: true. 축척: 거칠게(소스마다 정체·답할 수 있는 물음·겹침, 문서 6KB 안). 사유: {why}")
    try:
        from routing_system import _delegate_unified
        r = _delegate_unified({"scope": "system", "message": msg, "from_agent": "노트북 등록"},
                              str(getattr(context, "project_path", "") or ""))
    except Exception as e:
        return {"queued": False, "reason": f"위임 실패: {e}"}
    return {"queued": bool(isinstance(r, dict) and r.get("success")), "detail": r}


def _op_create(tool_input: dict, context) -> str:
    import notebook_core as core
    name = tool_input.get("name", "")
    out = core.create_notebook(name, tool_input.get("note", ""))
    if isinstance(out, dict) and out.get("success") and name:
        out["memory_survey"] = _schedule_survey(name, context, "노트북 생성")
    return _json(out)


def _op_add(tool_input: dict, context) -> str:
    raw = _op_add_inner(tool_input, context)
    try:
        out = json.loads(raw)
    except Exception:
        return raw
    name = tool_input.get("name", "")
    if isinstance(out, dict) and out.get("success") and name:
        out["memory_survey"] = _schedule_survey(name, context, "소스 추가")
        return _json(out)
    return raw


def _op_add_inner(tool_input: dict, context) -> str:
    import notebook_core as core
    path = str(tool_input.get("path") or "").strip()
    # ★F14-3 (2026-08-20 14회차): 상대 경로 해석 규약 통일 — 집 규약(write·download 와
    # 동일)대로 **프로젝트 기준**, 없으면 저장소 루트 폴백. 옛 동작은 backend cwd 기준이라
    # 같은 문장 안에서 write(프로젝트)와 add(cwd)의 기준이 갈려 예측 불가였다(14회차 I9 실측).
    if path and not core.is_url(path):
        expanded = expand_body_path(path)
        if not os.path.isabs(expanded):
            repo_root = os.environ.get("INDIEBIZ_ROOT") or os.path.abspath(
                os.path.join(CURRENT_DIR, "..", "..", "..", "..", ".."))
            bases = []
            if context is not None and getattr(context, "project_path", None):
                bases.append(context.project_path)
            bases.append(repo_root)
            tried = []
            resolved = None
            for base in bases:
                cand = os.path.abspath(os.path.join(base, expanded))
                tried.append(cand)
                if os.path.isfile(cand):
                    resolved = cand
                    break
            if resolved is None:
                return _json({"success": False,
                              "error": ("파일이 없습니다 — 상대 경로는 프로젝트 기준"
                                        "(없으면 저장소 루트 폴백)으로 해석합니다. 시도: "
                                        + " / ".join(tried))})
            path = resolved
    return _json(core.add_source(
        tool_input.get("name", ""),
        path=path,
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
    out = core.search_chunks(tool_input.get("name", ""), _query_of(tool_input), top_k=top_k, source=tool_input.get("source"))
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

    found = core.search_chunks(name, question, top_k=_as_int(tool_input.get("top_k"), ASK_TOP_K),
                               source=tool_input.get("source"))
    if not found.get("success"):
        return _json(found)
    excerpts = found["results"]
    memory_text = _notebook_memory_text(name)   # 포식 기억(어느 소스가 무엇인가) — 발췌를 읽는 지도
    if not excerpts:
        msg = ("소스에서 관련 발췌를 찾지 못했습니다 — 소스가 이 주제를 다루지 않거나, "
               "op:sources로 색인 상태(indexing/error/stale)를 확인하세요.")
        return _json({"success": True, "notebook": found.get("notebook", name), "question": question,
                      "not_in_sources": True, "answer": "", "citations": [], "items": [],
                      "blocks": [{"type": "paragraph", "text": msg}], "message": msg})

    answer_raw, model_err = _grounded_generate(found.get("note", ""), question, excerpts, memory=memory_text)
    # 되묻기 관문 (2026-09-04): 검색이 주제 발췌를 높은 유사도로 찾았는데 판정기가 **맨 표식만** 내면 그 거절은
    # 의심스럽다(경량 판정기가 '가장 …' 류 판단 질문을 '없음'으로 접던 실측). 검색 사실을 실어 한 번만 되묻는다 —
    # 그래도 표식이면 정직하게 '없음'. 티어 승격이 아니라 계약을 증거(검색 점수)에 거는 것.
    if not model_err and _should_reask(answer_raw, excerpts):
        answer_raw, model_err = _grounded_generate(found.get("note", ""), question, excerpts, memory=memory_text,
                                                   reask_score=_top_score(excerpts))
    if model_err:
        # 생성층 죽어도 검색층은 살아 있다 — 발췌를 정직 반환 (침묵 실패 금지)
        return _json({"success": False, "error": f"근거 고정 생성 실패: {model_err}",
                      "notebook": found["notebook"], "question": question,
                      "items": _excerpt_items(excerpts),
                      "message": "생성은 실패했지만 검색된 발췌를 items로 반환합니다."})

    if DIGEST_NEEDED_MARK in (answer_raw or ""):
        # 전체 소개·개요는 발췌 검색이 아니라 소스 전체 읽기(map-reduce)의 일이다 — 판정기가 넘기면 코드가 돈다.
        return _op_digest({**tool_input, "question": question}, context)

    if _is_not_in_sources(answer_raw, len(excerpts)):
        msg = "소스 안에 이 질문의 답이 없습니다(모델 판정). 일반 지식 답이 필요하면 노트북 밖에서 물어보세요."
        return _json({"success": True, "notebook": found["notebook"], "question": question,
                      "not_in_sources": True, "answer": "", "citations": [], "items": [],
                      "blocks": [{"type": "paragraph", "text": msg}],
                      "search_type": found["search_type"], "message": msg})

    answer, citations, dropped = _verify_citations(_strip_mark(answer_raw), excerpts)
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

def _resolve_source(core, name: str, source=None) -> dict:
    """소스 하나를 고른다 — id 등치 · 제목 부분일치 · 지정 없으면 노트북의 유일한 소스. 여럿인데 지정이 없으면 후보를 들고 거절."""
    ls = core.list_sources(name)
    if not ls.get("success"):
        return ls
    rows = ls["sources"]
    if not rows:
        return {"success": False, "error": f"'{name}' 노트북에 소스가 없습니다."}
    _src = str(source).strip() if source not in (None, "") else ""
    if not _src:
        if len(rows) == 1:
            return {"success": True, "source": rows[0]}
        return {"success": False, "error": f"소스가 {len(rows)}개입니다 — source(id 또는 제목 일부)를 지정하세요.",
                "candidates": [{"id": r["id"], "title": r["title"]} for r in rows[:12]]}
    try:
        from value_semantics import text_match, values_equal
    except ImportError:
        from common.value_semantics import text_match, values_equal
    hit = [r for r in rows if values_equal(str(r["id"]), _src) or text_match("contains", str(r.get("title") or ""), _src)]
    if len(hit) == 1:
        return {"success": True, "source": hit[0]}
    if not hit:
        return {"success": False, "error": f"'{_src}' 에 맞는 소스가 없습니다.", "candidates": [{"id": r["id"], "title": r["title"]} for r in rows[:12]]}
    return {"success": False, "error": f"'{_src}' 에 맞는 소스가 {len(hit)}개 — id 로 지정하세요.", "candidates": [{"id": r["id"], "title": r["title"]} for r in hit[:12]]}


def _source_chunks(core, source_id: int) -> list:
    """소스 하나의 청크 전부, 문서 순서(id 순 = 색인 순)."""
    conn = core._connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, loc, text FROM chunks WHERE source_id=? ORDER BY id", (source_id,)).fetchall()]
    finally:
        conn.close()


def _windows(chunks: list, limit: int = DIGEST_WINDOW_CHARS) -> list:
    """청크를 문서 순서대로 limit 자 안팎의 구간으로 묶는다(청크는 자르지 않는다)."""
    out, cur, size = [], [], 0
    for c in chunks:
        t = c.get("text") or ""
        if cur and size + len(t) > limit:
            out.append(cur); cur, size = [], 0
        cur.append(c); size += len(t)
    if cur:
        out.append(cur)
    return out


def _op_digest(tool_input: dict, context) -> str:
    """소스 전체 소개 (2026-09-04 사용자 신고 — "동영상 내용을 소개해줘" 에 발췌 12개로 답하려다 거절).
    발췌 검색은 '어디에 무엇이 있나'의 도구고, 전체 소개는 소스를 처음부터 끝까지 읽는 일이다:
    구간별 요지(경량, LLM n회) → 하나의 소개(평가 축, LLM 1회). 인용은 구간 번호·시각 자리(loc)로 남긴다."""
    import notebook_core as core
    name = tool_input.get("name", "")
    question = _query_of(tool_input) or "이 소스의 내용을 소개해줘"
    res = _resolve_source(core, name, tool_input.get("source"))
    if not res.get("success"):
        return _json({**res, "items": []})
    src = res["source"]
    chunks = _source_chunks(core, int(src["id"]))
    if not chunks:
        return _json({"success": False, "error": f"'{src.get('title')}' 소스에 색인된 청크가 없습니다(status={src.get('status')}).", "items": []})
    try:
        from consciousness_agent import oneshot_ai_call
    except ImportError as e:
        return _json({"success": False, "error": f"oneshot_ai_call 임포트 불가: {e}", "items": []})
    wins = _windows(chunks)
    gists = []
    for i, w in enumerate(wins, 1):
        loc = f"{(w[0].get('loc') or '').strip()}~{(w[-1].get('loc') or '').strip()}".strip("~")
        body = "\n".join((c.get("text") or "") for c in w)
        p = (f"다음은 '{src.get('title')}' 의 구간 {i}/{len(wins)}({loc})이다. 이 구간의 요지를 사실만, 3~6줄로 적어라. "
             f"고유명사·수치·주장은 보존하고 해석·추측은 넣지 마라. 언어는 이 요청의 언어(한국어).\n\n{body}")
        try:
            g = (oneshot_ai_call(p, system_prompt="너는 문서 구간 요약기다. 요지만, 근거 없는 말 금지.", role="classify") or "").strip()
        except Exception as e:
            g = f"(구간 요지 실패: {e})"
        gists.append({"n": i, "loc": loc, "chunks": len(w), "gist": g})
    outline = "\n\n".join(f"[구간 {g['n']}] ({g['loc']})\n{g['gist']}" for g in gists)
    reduce_prompt = (f"요청: {question}\n소스: '{src.get('title')}' ({src.get('kind')}, 구간 {len(wins)}개, 전체 {sum(len(c.get('text') or '') for c in chunks):,}자)\n\n"
                     f"아래는 소스를 처음부터 끝까지 순서대로 읽고 적은 구간별 요지다. 이것만 근거로 요청에 답하라 — "
                     f"구조(흐름)·핵심 주장·주요 개념을 요청의 언어로 소개하고, 문장 끝에 근거 구간을 [구간 n] 으로 달아라. "
                     f"요지에 없는 내용은 보태지 마라.\n\n{outline}")
    try:
        answer = (oneshot_ai_call(reduce_prompt, system_prompt="너는 근거 고정 소개문 작성자다. 구간 요지만 근거로 쓴다.", role="evaluate") or "").strip()
    except Exception as e:
        return _json({"success": False, "error": f"소개문 생성 실패: {e}", "items": gists,
                      "message": "구간 요지는 items 로 반환합니다."})
    blocks = [{"type": "paragraph", "text": answer}, {"type": "heading", "level": 4, "text": f"구간 요지 ({len(wins)}개)"}]
    blocks += [{"type": "paragraph", "text": f"[구간 {g['n']}] ({g['loc']}) {g['gist']}"} for g in gists]
    return _json({"success": True, "notebook": name, "question": question, "mode": "digest", "source": {"id": src["id"], "title": src.get("title"), "kind": src.get("kind")},
                  "not_in_sources": False, "answer": answer, "blocks": blocks, "items": gists, "windows": len(wins), "chunks": len(chunks)})


COVERAGE_SCORE = 0.6     # 이 위면 발췌가 질문의 주제를 다룬다고 본다(하이브리드 점수, 실측 0.66~0.70 에서 거절 발생)


def _top_score(excerpts: list) -> float:
    try:
        return max(float(r.get("score") or 0.0) for r in excerpts) if excerpts else 0.0
    except (TypeError, ValueError):
        return 0.0


def _should_reask(answer_raw: str, excerpts: list) -> bool:
    """맨 표식(인용 0) + 검색 최고점 ≥ COVERAGE_SCORE 일 때만 한 번 되묻는다."""
    return _is_not_in_sources(answer_raw, len(excerpts)) and _top_score(excerpts) >= COVERAGE_SCORE


def _grounded_generate(note: str, question: str, excerpts: list, memory: str = "", reask_score: float = None):
    """경량 AI 1회 — 발췌만 근거로 [n] 인용 달린 답. 반환 (answer, error).
    memory: 노트북 포식 기억 문서(어느 소스가 무엇이고 어떤 물음에 답하나) — 발췌를 고르는 지도이지 근거가 아니다."""
    try:
        from consciousness_agent import oneshot_ai_call
    except ImportError as e:
        return "", f"oneshot_ai_call 임포트 불가(백엔드 밖 실행?): {e}"

    lines = []
    for i, r in enumerate(excerpts, 1):
        loc = f" {r['loc']}" if r.get("loc") else ""
        lines.append(f"[{i}] ({r['source']}{loc}) {r['text']}")
    goal = f"\n이 노트북의 목적: {note}" if (note or "").strip() else ""
    mem = (f"\n\n노트북 기억(어느 소스가 무엇이고 어떤 물음에 답하나 — 발췌를 판단하는 지도일 뿐, 근거는 여전히 아래 발췌만):\n{memory}"
           if (memory or "").strip() else "")

    system_prompt = (
        "당신은 근거 고정(grounded) 조수다. 규칙:\n"
        "1) 아래 '발췌'들만 근거로 답하라. 당신의 일반 지식으로 보충하지 마라.\n"
        "2) 답의 모든 주장 문장 끝에 근거 발췌 번호를 [1] [2] 형태로 달아라. 여러 발췌면 [1][3].\n"
        "3) 발췌들이 질문의 **주제를 전혀 다루지 않을 때만** 다른 말 없이 정확히 NOT_IN_SOURCES 라고만 답하라. "
        "발췌가 주제를 다루지만 순위·최상급·확정 판단('가장', '~인가')을 직접 주지 않으면 그것은 '없음'이 아니다 — "
        "발췌가 말하는 바를 인용해 답하고, 마지막 한 문장으로 소스가 어디까지 말하는지 한계를 밝혀라. 추측 금지.\n"
        "4) 발췌에 없는 번호를 인용하지 마라.\n"
        "5) 답은 질문의 언어로, 간결하게.\n"
        "6) 질문이 소스 **전체**의 소개·개요·요약·흐름을 요구하는데 발췌가 단편이라 전체를 말할 수 없으면, "
        "발췌를 하나씩 나열하며 설명하지 말고 다른 말 없이 정확히 DIGEST_NEEDED 라고만 답하라 — 그러면 소스 전체를 순서대로 읽어 소개한다."
    )
    reask = ""
    if reask_score is not None:
        reask = (f"\n\n★검색이 이 질문의 주제를 다루는 발췌를 찾았다(최고 유사도 {reask_score:.2f}). "
                 "그러므로 '없음'은 답이 아니다 — 발췌가 이 주제에 대해 말하는 바를 [n] 인용으로 답하고, "
                 "질문이 요구하는 순위·판단이 발췌에 없으면 마지막 한 문장으로 그 한계를 밝혀라.")
    prompt = f"질문: {question}{goal}{mem}{reask}\n\n발췌:\n" + "\n\n".join(lines)

    try:
        answer = oneshot_ai_call(prompt, system_prompt=system_prompt, role="classify")
    except Exception as e:
        return "", str(e)
    if not (answer or "").strip():
        return "", "경량 AI가 빈 응답을 반환"
    return answer.strip(), ""


_CITE_RE = re.compile(r"\[(\d{1,2})\]")


def _is_not_in_sources(answer_raw: str, n_excerpts: int) -> bool:
    """'없음' 판정은 표식이 **답을 대신할 때만** (2026-09-04 실측 — 경량 판정기가 '가장 유용한 사례는?' 같은
    판단 질문에 "발췌는 사례를 나열하지만 순위는 없다 … NOT_IN_SOURCES" 로 설명과 표식을 함께 냈고, 옛 코드는
    표식이 어디에든 있으면 통째로 거절해 인용 달린 설명까지 버렸다). 규칙: 표식이 있고 유효 인용이 하나도
    없으면 '없음', 유효 인용이 있으면 표식은 군말로 보고 답을 살린다."""
    if NOT_IN_SOURCES_MARK not in (answer_raw or ""):
        return False
    valid = set(range(1, n_excerpts + 1))
    cited = [int(m.group(1)) for m in _CITE_RE.finditer(answer_raw) if int(m.group(1)) in valid]
    return not cited


def _strip_mark(answer_raw: str) -> str:
    """답 속에 섞인 표식·그 줄만 걷어낸다(표식 단독 줄은 통째로)."""
    lines = [l for l in (answer_raw or "").splitlines() if l.strip() != NOT_IN_SOURCES_MARK]
    return "\n".join(lines).replace(NOT_IN_SOURCES_MARK, "").strip()


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
        "digest": _op_digest,
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
