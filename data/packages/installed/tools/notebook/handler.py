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
CARD_DIRECT_MAX = 45000                # 이 아래면 문서를 통째로 읽고 카드를 쓴다, 위면 구간 요지를 거쳐 쓴다
CARD_WAIT_S = 240                      # add 뒤 색인이 끝나길 기다리는 상한(카드는 청크가 있어야 쓴다)
READ_MAX_DOCS = 4                      # ask 가 한 번에 통째로 읽는 문서 수 상한
READ_MAX_CHARS = 90000                 # ask 가 한 번에 읽는 본문 합 상한(넘으면 카드+발췌로 강등, 신고)
MAP_MAX_CHARS = 24000                  # 선택 호출에 넣는 지도 상한


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
        if out.get("source_id"):
            _card_after_index(name, int(out["source_id"]))   # 문서 단위 카드 — 넣을 때 한 번 읽는다
            out["card"] = "색인 뒤 자동 작성(op:map 으로 확인)"
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
        for s in out["sources"]:
            p = _card_path(core, tool_input.get("name", ""), s["id"])
            s["card_gist"] = _card_gist(p) if p.exists() else ""
        out["items"] = [{
            "title": s["title"],
            "meta": " · ".join(x for x in [
                f"#{s['id']}", s["kind"], f"청크 {s['chunk_count']}", s["status"],
                s.get("stale") and f"⚠️{s['stale']}", (not s.get("card_gist")) and "카드 없음"] if x),
            "summary": s.get("error") or s.get("card_gist") or (s.get("path") or ""),
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


def _map_items(core, name: str) -> dict:
    """지도 재료 — 소스마다 카드 한 줄. {success, notebook, note, items, text, missing}"""
    ls = core.list_sources(name)
    if not ls.get("success"):
        return ls
    items, lines, missing = [], [], 0
    for s in ls["sources"]:
        p = _card_path(core, name, s["id"])
        gist = _card_gist(p) if p.exists() else ""
        if not gist:
            missing += 1
        lines.append(f"- #{s['id']} {s.get('title')} ({s.get('kind')} · {int(s.get('char_count') or 0):,}자) — {gist or '(카드 없음)'}")
        items.append({**{k: s.get(k) for k in ("id", "title", "kind", "char_count", "status")}, "gist": gist, "card": str(p) if p.exists() else None})
    return {"success": True, "notebook": ls.get("notebook"), "note": ls.get("note", ""), "items": items,
            "text": "\n".join(lines), "missing": missing}


LEXICAL_MAX_SHARE = 0.25   # 이 비율보다 많은 청크에 나오는 낱말은 증거가 아니다('방법'·'최근' 같은 흔한 말)


def _lexical_sources(core, notebook_id: int, question: str) -> set:
    """질문의 **드문 낱말**이 실제로 나오는 소스 집합 (FTS, LLM 0). 흔한 낱말('방법')은 어느 문서에나 있어
    증거가 못 된다 — 2026-09-04 감귤 실측: OR 검색이 '방법' 하나로 강행을 발동시켰다."""
    safe = re.sub(r"[^\w\s가-힣]", " ", question or "")
    tokens = [t for t in dict.fromkeys(safe.split()) if len(t) >= 2][:12]
    if not tokens:
        return set()
    conn = core._connect()
    try:
        total = conn.execute("SELECT count(*) FROM chunks WHERE notebook_id=?", (notebook_id,)).fetchone()[0] or 0
        if not total:
            return set()
        out = set()
        for t in tokens:
            q = '"' + t.replace('"', '""') + '"'
            try:
                n = conn.execute("SELECT count(*) FROM chunks_fts f JOIN chunks c ON c.id = f.rowid WHERE chunks_fts MATCH ? AND c.notebook_id=?",
                                 (q, notebook_id)).fetchone()[0]
                if 0 < n <= max(1, int(total * LEXICAL_MAX_SHARE)):
                    out |= {int(r[0]) for r in conn.execute(
                        "SELECT DISTINCT c.source_id FROM chunks_fts f JOIN chunks c ON c.id = f.rowid WHERE chunks_fts MATCH ? AND c.notebook_id=?",
                        (q, notebook_id)).fetchall()}
            except Exception:
                continue
        return out
    finally:
        conn.close()


def _search_hints(core, name: str, question: str, top_k: int = 12) -> list:
    """청크 검색을 **위치 색인**으로 쓴다 — 어느 문서에 질문의 낱말·뜻이 실제로 나오는가(LLM 0). 문서별 최고점·건수."""
    try:
        f = core.search_chunks(name, question, top_k=top_k)
    except Exception:
        return []
    # 어휘 일치(FTS)는 따로 센다 — 하이브리드 점수는 정규화돼 무관한 내용도 0.7 이 나오지만(2026-09-04 감귤 실측),
    # 낱말이 본문에 실제로 있는지는 FTS 만이 말한다. '증거가 판단을 이긴다'의 증거는 이것이다.
    try:
        nb = core.get_notebook(name)
        fts_src = _lexical_sources(core, nb["id"], question) if nb else set()
    except Exception:
        fts_src = set()
    agg = {}
    for r in (f.get("results") or []):
        sid = r.get("source_id")
        if sid is None:
            continue
        a = agg.setdefault(int(sid), {"source_id": int(sid), "source": r.get("source"), "score": 0.0, "hits": 0, "loc": r.get("loc"),
                                      "lexical": int(sid) in fts_src})
        a["hits"] += 1
        if float(r.get("score") or 0) > a["score"]:
            a["score"] = round(float(r.get("score") or 0), 3); a["loc"] = r.get("loc")
    return sorted(agg.values(), key=lambda x: (-int(x["lexical"]), -x["score"]))[:6]


def _select_sources(question: str, note: str, map_text: str, hints: list = None) -> dict:
    """AI 가 지도(카드 한 줄)와 검색 힌트(어느 문서 본문에 실제로 나오나)를 보고 읽을 문서를 고른다 (경량 1회).
    {mode: map|read|none, sources: [ids], why}. 분류기가 아니라 판단이다 — 다만 증거(검색 점수)가 판단을 이긴다:
    none 이라 해도 힌트 최고점 ≥ COVERAGE_SCORE 면 그 문서들을 읽는다(2026-09-04 실측: 카드 한 줄에 '주가'가 없다고
    삼성 주가 질문을 none 으로 접었는데 본문엔 날짜별 등락이 있었다)."""
    from consciousness_agent import oneshot_ai_call
    from runtime_utils import parse_first_json
    hints = hints or []
    system = ("너는 노트북 사서다. 질문·소스 지도(소스마다 한 줄)·검색 힌트(질문의 낱말·뜻이 본문에 실제로 나온 문서와 점수)를 보고 "
              "어느 문서를 통째로 읽어야 답할 수 있는지 고른다. JSON 만 답하라: "
              "{\"mode\": \"read\"|\"map\"|\"none\", \"sources\": [소스 번호…], \"why\": \"한 줄\"}. "
              f"mode=read: 읽을 문서 번호(최대 {READ_MAX_DOCS}, 관련성 높은 순). 문서가 그 주제를 *언급*만 해도 read 다 — "
              "질문을 '주제로 삼은' 문서가 있어야 하는 게 아니다(부분 언급·수치·날짜가 답이 된다). 검색 힌트에 오른 문서는 우선 후보다. "
              "mode=map: 지도만으로 답이 되는 물음(무엇이 있나·어떤 소스들이 다루나·전체 조망). "
              "mode=none: 지도·힌트 어디에도 그 주제가 전혀 없을 때만.")
    hint_text = ("\n검색 힌트(본문 일치, 낱말 일치 우선):\n" + "\n".join(f"- #{h['source_id']} {h['source']} ({'낱말 일치' if h.get('lexical') else '뜻 근접만'}, 점수 {h['score']}, 발췌 {h['hits']}{', 자리 ' + str(h['loc']) if h.get('loc') else ''})" for h in hints)) if hints else "\n검색 힌트: 없음(본문 일치 0)"
    prompt = f"질문: {question}\n" + (f"노트북 목적: {note}\n" if note else "") + f"\n소스 지도:\n{map_text[:MAP_MAX_CHARS]}" + hint_text
    raw = oneshot_ai_call(prompt, system_prompt=system, role="classify") or ""
    d = parse_first_json(raw)
    if not isinstance(d, dict):
        return {"mode": "read", "sources": [], "why": "선택 응답 파싱 실패 — 지도 상위로 폴백", "raw": raw[:200]}
    ids = []
    for x in (d.get("sources") or []):
        try:
            ids.append(int(str(x).lstrip("#")))
        except ValueError:
            pass
    sel = {"mode": str(d.get("mode") or "read"), "sources": ids[:READ_MAX_DOCS], "why": str(d.get("why") or ""), "hints": hints}
    # 증거가 판단을 이긴다: none 인데 질문의 낱말이 본문에 실제로 있으면(FTS) 그 문서들을 읽는다
    lexical = [h for h in hints if h.get("lexical")]
    if sel["mode"] == "none" and lexical:
        sel["mode"] = "read"; sel["sources"] = [h["source_id"] for h in lexical[:READ_MAX_DOCS]]
        sel["why"] = f"낱말 일치 증거로 강행({len(lexical)}문서) — 사서 판정: {sel['why']}"
    elif sel["mode"] == "read" and not sel["sources"] and hints:
        sel["sources"] = [h["source_id"] for h in hints[:READ_MAX_DOCS]]
    return sel


def _read_whole(core, name: str, src: dict, budget: int) -> tuple:
    """문서 하나를 통째로(예산 안) — (본문, 읽은 자수, 강등 여부). 큰 문서는 카드 + 앞부분으로 강등하고 신고."""
    chunks = _source_chunks(core, int(src["id"]))
    body = "\n\n".join(f"[{(c.get('loc') or '').strip()}] {c.get('text') or ''}" for c in chunks)
    if len(body) <= budget:
        return body, len(body), False
    p = _card_path(core, name, src["id"])
    card = open(p, encoding="utf-8").read() if p.exists() else ""
    head = body[:max(0, budget - len(card) - 200)]
    return (card + "\n\n[본문 앞부분 — 예산으로 절단]\n" + head), len(head) + len(card), True


def _answer_from_docs(question: str, note: str, docs: list) -> tuple:
    """읽은 문서들만 근거로 답 (평가 축 1회). 인용은 [#소스번호 자리]. 반환 (answer, err)."""
    from consciousness_agent import oneshot_ai_call
    system = ("당신은 근거 고정(grounded) 조수다. 아래 '문서'들만 근거로 답하라. 일반 지식으로 보충하지 마라. "
              "문장마다 근거를 [#소스번호 자리] 로 달아라(자리 = 문서 안의 [..] 표지, 예 [#19 3. 주목할 AI 활용 사례] 또는 [#67 12:00]). "
              "문서들이 질문의 주제를 전혀 다루지 않을 때만 정확히 NOT_IN_SOURCES 라고만 답하라. "
              "주제를 다루지만 확정 판단·순위가 없으면 문서가 말하는 바를 답하고 마지막 한 문장으로 한계를 밝혀라. 답은 질문의 언어로.")
    parts = [f"=== 문서 #{d['id']} · {d['title']} ({d['kind']}, {d['chars']:,}자{' · 절단' if d['truncated'] else ''}) ===\n{d['body']}" for d in docs]
    prompt = f"질문: {question}\n" + (f"노트북 목적: {note}\n" if note else "") + "\n" + "\n\n".join(parts)
    try:
        a = oneshot_ai_call(prompt, system_prompt=system, role="evaluate") or ""
    except Exception as e:
        return "", str(e)
    return a.strip(), ("" if a.strip() else "빈 응답")


def _answer_from_map(question: str, note: str, map_text: str, cards: list) -> tuple:
    from consciousness_agent import oneshot_ai_call
    system = ("당신은 노트북 사서다. 아래 소스 지도와 카드만 근거로, 이 노트북에 무엇이 있고 어느 소스가 무엇을 다루는지 답하라. "
              "소스는 [#번호] 로 가리켜라. 지도에 없는 내용은 보태지 마라. 답은 질문의 언어로.")
    prompt = f"질문: {question}\n" + (f"노트북 목적: {note}\n" if note else "") + f"\n소스 지도:\n{map_text[:MAP_MAX_CHARS]}" + ("\n\n카드:\n" + "\n\n".join(cards) if cards else "")
    try:
        a = oneshot_ai_call(prompt, system_prompt=system, role="evaluate") or ""
    except Exception as e:
        return "", str(e)
    return a.strip(), ("" if a.strip() else "빈 응답")


_DOC_CITE_RE = re.compile(r"\[#(\d+)([^\]]*)\]")


def _ask_by_cards(core, name: str, question: str, m: dict) -> str:
    """문서 단위 ask (2026-09-04 사용자 판정): 지도 → 문서 선택 → 통째로 읽기 → 근거 답."""
    note = m.get("note") or ""
    sel = _select_sources(question, note, m["text"], _search_hints(core, name, question))
    by_id = {int(i["id"]): i for i in m["items"]}
    if sel["mode"] == "none" and not sel["sources"]:
        msg = f"지도상 이 노트북은 이 주제를 다루지 않습니다(사서 판정: {sel.get('why') or ''}). 소스 지도는 op:map."
        return _json({"success": True, "notebook": m["notebook"], "question": question, "mode": "none", "not_in_sources": True,
                      "answer": "", "citations": [], "items": [], "blocks": [{"type": "paragraph", "text": msg}], "message": msg, "selection": sel})
    if sel["mode"] == "map":
        cards = []
        for sid in sel["sources"][:READ_MAX_DOCS]:
            it = by_id.get(sid)
            if it and it.get("card"):
                cards.append(open(it["card"], encoding="utf-8").read()[:6000])
        answer, err = _answer_from_map(question, note, m["text"], cards)
        if err:
            return _json({"success": False, "error": f"지도 답 생성 실패: {err}", "items": m["items"], "message": "지도는 items 로 반환합니다."})
        return _json({"success": True, "notebook": m["notebook"], "question": question, "mode": "map", "not_in_sources": False,
                      "answer": answer, "blocks": [{"type": "paragraph", "text": answer}], "citations": [], "items": [],
                      "selection": sel, "map_sources": len(m["items"])})
    ids = [i for i in sel["sources"] if i in by_id] or [int(i["id"]) for i in m["items"][:1]]
    docs, budget, degraded = [], READ_MAX_CHARS, []
    for sid in ids[:READ_MAX_DOCS]:
        src = by_id[sid]
        body, used, trunc = _read_whole(core, name, src, max(8000, budget // max(1, (len(ids) - len(docs)))))
        budget -= used
        docs.append({"id": sid, "title": src.get("title"), "kind": src.get("kind"), "chars": int(src.get("char_count") or used), "body": body, "truncated": trunc})
        if trunc:
            degraded.append(sid)
        if budget <= 0:
            break
    answer, err = _answer_from_docs(question, note, docs)
    if err:
        return _json({"success": False, "error": f"근거 고정 생성 실패: {err}", "notebook": m["notebook"], "question": question,
                      "items": [{"title": d["title"], "source_id": d["id"], "summary": by_id[d["id"]].get("gist", "")} for d in docs],
                      "message": "생성은 실패했지만 고른 문서 목록을 items 로 반환합니다.", "selection": sel})
    if NOT_IN_SOURCES_MARK in answer and not _DOC_CITE_RE.search(answer):
        msg = "고른 문서 안에 이 질문의 답이 없습니다(모델 판정). 읽은 문서: " + ", ".join(f"#{d['id']} {d['title']}" for d in docs)
        return _json({"success": True, "notebook": m["notebook"], "question": question, "mode": "read", "not_in_sources": True,
                      "answer": "", "citations": [], "items": [], "blocks": [{"type": "paragraph", "text": msg}], "message": msg,
                      "read": [d["id"] for d in docs], "selection": sel})
    answer = _strip_mark(answer)
    read_ids = {d["id"] for d in docs}
    cites, seen = [], set()
    for mm in _DOC_CITE_RE.finditer(answer):
        sid = int(mm.group(1)); loc = mm.group(2).strip()
        if sid in read_ids and (sid, loc) not in seen:
            seen.add((sid, loc)); cites.append({"source_id": sid, "source": by_id[sid].get("title"), "loc": loc})
    blocks = [{"type": "paragraph", "text": answer}]
    if degraded:
        blocks.append({"type": "paragraph", "text": "⚠ 예산으로 앞부분만 읽은 문서: " + ", ".join(f"#{i}" for i in degraded)})
    return _json({"success": True, "notebook": m["notebook"], "question": question, "mode": "read", "not_in_sources": False,
                  "answer": answer, "blocks": blocks, "citations": cites,
                  "items": [{"title": c["source"], "meta": f"#{c['source_id']} · {c['loc']}", "summary": "", "source_id": c["source_id"]} for c in cites],
                  "read": [{"source_id": d["id"], "title": d["title"], "chars": d["chars"], "truncated": d["truncated"]} for d in docs],
                  "selection": sel})


def _op_ask(tool_input: dict, context) -> str:
    import notebook_core as core
    name = tool_input.get("name", "")
    question = _query_of(tool_input)
    if not question:
        return _json({"success": False, "error": "query(질문)가 필요합니다."})

    # 문서 단위 경로 (2026-09-04): 카드가 하나라도 있으면 지도→선택→통째로 읽기. 카드가 없으면 옛 청크 검색 경로.
    if not tool_input.get("source") and not tool_input.get("chunks"):
        m = _map_items(core, name)
        if m.get("success") and m["items"] and m["missing"] < len(m["items"]):
            try:
                return _ask_by_cards(core, name, question, m)
            except Exception as e:
                print(f"[notebook] 문서 단위 ask 실패 → 청크 경로 폴백: {e}")

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


# =============================================================================
# 소스 카드 (2026-09-04 사용자 판정 "문서가 단위, 카드가 지도, 답할 때는 골라서 통째로")
#   정본 = data/notebook/cards/<노트북>/<source_id>.md (사람이 고친다), DB 는 한 줄 요약(gist)만 색인.
#   650자 청크는 위치 색인으로 남고, 이해의 단위는 문서다. 카드는 "무엇인가·구조·핵심·답할 물음"을
#   AI 가 한 번 읽고 쓴다(넣을 때 자동, op:card 로 다시). 지도(op:map)는 카드 한 줄들의 목록.
# =============================================================================

def _card_dir(core, name: str):
    return core.NOTEBOOK_DIR / "cards" / re.sub(r"[^\w가-힣.-]+", "_", name)


def _card_path(core, name: str, source_id: int):
    return _card_dir(core, name) / f"{int(source_id)}.md"


def _card_gist(path) -> str:
    """카드의 `> 한 줄` — 지도에 실린다. 없으면 빈 문자열."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("> "):
                    return line[2:].strip()
    except OSError:
        pass
    return ""


def _card_prompt(title: str, kind: str, body: str, via_gists: bool) -> tuple:
    system = ("너는 문서 카드 작성자다. 주어진 본문만 근거로, 아래 형식을 정확히 지켜 한국어로 쓴다(고유명사·용어는 원어 보존). "
              "추측·평가 금지, 본문에 없는 말 금지. 카드는 이 문서를 읽을지 말지를 고르는 지도이므로 사실·구조·물음을 정확히.")
    fmt = ("> (한 줄 요약 — 이 문서가 무엇이고 무엇을 말하는지, 80자 안)\n\n"
           "## 무엇인가\n(종류·저자·시기·목적 2~4문장)\n\n"
           "## 구조\n(절·주제 전환 순서대로 `- [자리] 제목 — 한 줄`; 자막이면 시각, 문서면 절 제목)\n\n"
           "## 핵심 주장·수치·이름\n(- 항목 5~12개, 수치·날짜·이름 그대로)\n\n"
           "## 답할 수 있는 물음\n(- 이 문서가 답해 줄 물음 5~10개, 물음 형태로)")
    src = "구간별 요지(문서를 처음부터 끝까지 순서대로 읽고 적은 것)" if via_gists else "본문 전체"
    prompt = f"문서: '{title}' ({kind})\n아래는 {src}다.\n\n형식:\n{fmt}\n\n{src}:\n{body}"
    return system, prompt


def _write_card(core, name: str, src: dict, force: bool = False) -> dict:
    """소스 하나의 카드를 쓴다(있고 force 아니면 그대로). 반환 {success, path, gist, chars, via}."""
    from datetime import datetime
    path = _card_path(core, name, src["id"])
    if path.exists() and not force:
        return {"success": True, "path": str(path), "gist": _card_gist(path), "skipped": "exists"}
    chunks = _source_chunks(core, int(src["id"]))
    if not chunks:
        return {"success": False, "error": f"청크 없음(status={src.get('status')})"}
    try:
        from consciousness_agent import oneshot_ai_call
    except ImportError as e:
        return {"success": False, "error": f"oneshot_ai_call 임포트 불가: {e}"}
    total = sum(len(c.get("text") or "") for c in chunks)
    via = "direct"
    if total <= CARD_DIRECT_MAX:
        body = "\n\n".join(f"[{(c.get('loc') or '').strip()}] {c.get('text') or ''}" for c in chunks)
    else:
        via = "gists"
        parts = []
        for i, w in enumerate(_windows(chunks), 1):
            loc = f"{(w[0].get('loc') or '').strip()}~{(w[-1].get('loc') or '').strip()}".strip("~")
            text = "\n".join((c.get("text") or "") for c in w)
            g = oneshot_ai_call(f"다음 구간({loc})의 요지를 사실만 3~6줄로. 고유명사·수치 보존, 추측 금지.\n\n{text}",
                                system_prompt="너는 문서 구간 요약기다.", role="classify") or ""
            parts.append(f"[구간 {i} · {loc}]\n{g.strip()}")
        body = "\n\n".join(parts)
    system, prompt = _card_prompt(src.get("title") or "", src.get("kind") or "", body, via == "gists")
    try:
        card = (oneshot_ai_call(prompt, system_prompt=system, role="classify") or "").strip()
    except Exception as e:
        return {"success": False, "error": f"카드 생성 실패: {e}"}
    if not card.startswith(">"):
        card = "> " + card.split("\n", 1)[0].strip()[:120] + "\n\n" + card
    head = (f'<!-- notebook-card notebook="{name}" source_id="{src["id"]}" kind="{src.get("kind") or ""}" chars="{total}" '
            f'chunks="{len(chunks)}" via="{via}" written="{datetime.now().strftime("%Y-%m-%d %H:%M")}" -->\n'
            f"# 카드 — {src.get('title') or ''}\n"
            f"<!-- 이 카드가 정본이다 — 고치면 지도(op:map)와 ask 의 문서 선택이 따라온다. `> 한 줄` 이 지도에 실린다. -->\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(head + card + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return {"success": True, "path": str(path), "gist": _card_gist(path), "chars": total, "via": via}


def _op_card(tool_input: dict, context) -> str:
    """카드 쓰기 — source 지정(id·제목 일부) 또는 전부(기본: 카드 없는 소스만, force 면 전부 다시)."""
    import notebook_core as core
    name = tool_input.get("name", "")
    ls = core.list_sources(name)
    if not ls.get("success"):
        return _json({**ls, "items": []})
    force = bool(tool_input.get("force"))
    if tool_input.get("source") not in (None, ""):
        res = _resolve_source(core, name, tool_input.get("source"))
        if not res.get("success"):
            return _json({**res, "items": []})
        targets = [res["source"]]
    else:
        targets = [s for s in ls["sources"] if s.get("status") == "ready"]
    items, written, skipped, failed = [], 0, 0, 0
    for s in targets:
        r = _write_card(core, name, s, force=force)
        if r.get("success"):
            if r.get("skipped"):
                skipped += 1
            else:
                written += 1
        else:
            failed += 1
        items.append({"title": s.get("title"), "source_id": s["id"], "summary": r.get("gist") or r.get("error") or "",
                      "meta": " · ".join(x for x in [f"#{s['id']}", s.get("kind"), r.get("via"), r.get("skipped") and "기존", (not r.get("success")) and "실패"] if x)})
    return _json({"success": failed == 0, "notebook": name, "written": written, "skipped": skipped, "failed": failed,
                  "items": items, "message": f"카드 {written}건 작성, {skipped}건 기존, {failed}건 실패 — 지도는 op:map"})


def _op_card_read(tool_input: dict, context) -> str:
    """카드 원문 읽기 — 앱의 카드 편집 폼이 이 결과의 {text} 로 채운다."""
    import notebook_core as core
    name = tool_input.get("name", "")
    res = _resolve_source(core, name, tool_input.get("source") or tool_input.get("source_id"))
    if not res.get("success"):
        return _json({**res, "items": []})
    src = res["source"]; p = _card_path(core, name, src["id"])
    text = open(p, encoding="utf-8").read() if p.exists() else ""
    return _json({"success": True, "notebook": name, "source_id": src["id"], "title": src.get("title"), "kind": src.get("kind"),
                  "chars": src.get("char_count"), "exists": p.exists(), "path": str(p), "gist": _card_gist(p) if p.exists() else "",
                  "text": text, "items": [],
                  "message": "" if p.exists() else "카드가 아직 없습니다 — 'AI 에게 맡기기'로 쓰거나 직접 적으세요."})


def _op_card_save(tool_input: dict, context) -> str:
    """카드 저장 — 사람이 고친 원문을 정본 파일에 원자 쓰기. 머리 표식이 없으면 붙여 준다."""
    import notebook_core as core
    from datetime import datetime
    name = tool_input.get("name", "")
    text = str(tool_input.get("text") or "")
    if not text.strip():
        return _json({"success": False, "error": "text(카드 본문)가 비어 있습니다.", "items": []})
    res = _resolve_source(core, name, tool_input.get("source") or tool_input.get("source_id"))
    if not res.get("success"):
        return _json({**res, "items": []})
    src = res["source"]; p = _card_path(core, name, src["id"])
    if not text.lstrip().startswith("<!-- notebook-card"):
        text = (f'<!-- notebook-card notebook="{name}" source_id="{src["id"]}" kind="{src.get("kind") or ""}" via="human" '
                f'written="{datetime.now().strftime("%Y-%m-%d %H:%M")}" -->\n' + text.lstrip())
    if "\n> " not in text and not text.lstrip().startswith("> "):
        return _json({"success": False, "error": "카드에는 `> 한 줄 요약` 줄이 있어야 합니다(지도에 실리는 줄).", "items": []})
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp"); tmp.write_text(text.rstrip("\n") + "\n", encoding="utf-8"); os.replace(tmp, p)
    return _json({"success": True, "notebook": name, "source_id": src["id"], "path": str(p), "gist": _card_gist(p),
                  "items": [], "message": f"카드 저장 — 지도 한 줄: {_card_gist(p)[:80]}"})


def _op_map(tool_input: dict, context) -> str:
    """지도 — 소스마다 카드 한 줄(LLM 0). "이 노트북에 무엇이 있나"는 이것으로 답한다; 문서를 고르는 눈."""
    import notebook_core as core
    name = tool_input.get("name", "")
    ls = core.list_sources(name)
    if not ls.get("success"):
        return _json({**ls, "items": []})
    items, lines, missing = [], [], 0
    for s in ls["sources"]:
        p = _card_path(core, name, s["id"])
        gist = _card_gist(p) if p.exists() else ""
        if not gist:
            missing += 1
        lines.append(f"- #{s['id']} {s.get('title')} ({s.get('kind')} · {int(s.get('char_count') or 0):,}자) — {gist or '(카드 없음 — op:card)'}")
        items.append({"source_id": s["id"], "title": s.get("title"), "kind": s.get("kind"), "chars": s.get("char_count"),
                      "gist": gist, "card": str(p) if p.exists() else None, "summary": gist or "(카드 없음)",
                      "meta": f"#{s['id']} · {s.get('kind')} · {int(s.get('char_count') or 0):,}자", "notebook": ls.get("notebook")})
    text = f"# 지도 — {ls.get('notebook')}\n" + (f"> {ls.get('note')}\n" if ls.get("note") else "") + "\n".join(lines)
    return _json({"success": True, "notebook": ls.get("notebook"), "note": ls.get("note"), "count": len(items),
                  "missing_cards": missing, "text": text, "items": items, "blocks": [{"type": "paragraph", "text": text}]})


def _card_after_index(name: str, source_id: int):
    """add 뒤 색인이 끝나면 카드를 쓴다(데몬 스레드) — 넣는 순간이 문서를 한 번 읽는 자리다."""
    import threading, time

    def _run():
        try:
            import notebook_core as core
            t0 = time.time()
            while time.time() - t0 < CARD_WAIT_S:
                st = core._source_status(int(source_id))
                if st and st.get("status") == "ready":
                    conn = core._connect()
                    try:
                        row = conn.execute("SELECT * FROM sources WHERE id=?", (int(source_id),)).fetchone()
                    finally:
                        conn.close()
                    if row:
                        r = _write_card(core, name, dict(row), force=True)
                        print(f"[notebook] 카드 {'작성' if r.get('success') else '실패'}: {name} #{source_id} {r.get('gist') or r.get('error') or ''}"[:200])
                    return
                if st and st.get("status") == "error":
                    return
                time.sleep(2)
            print(f"[notebook] 카드 대기 상한: {name} #{source_id} — op:card 로 다시")
        except Exception as e:
            print(f"[notebook] 카드 스레드 오류: {e}")
    threading.Thread(target=_run, name=f"notebook-card-{source_id}", daemon=True).start()  # cc-ok: 수명 ≤ CARD_WAIT_S(240초) 폴링 뒤 종료, 리로드로 죽어도 카드는 op:card 로 재작성되는 파생물(원자 쓰기)이라 잃는 것이 없다


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
        "card": _op_card,
        "card_read": _op_card_read,
        "card_save": _op_card_save,
        "map": _op_map,
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
