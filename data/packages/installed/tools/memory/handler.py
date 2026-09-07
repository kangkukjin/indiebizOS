"""
Memory Handler - 메모리 통합 관리
심층 메모리 + 대화 이력을 통합 검색
"""
import json
import os
import sqlite3
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


# ── op 분기 함수 (진짜 디스패처 — memory_db 는 sys.modules 캐시라 재임포트 비용 0) ──

def _op_save(tool_input: dict, context) -> str:
    import memory_db
    return _memory_save(memory_db, tool_input, context.project_path, context.agent_id)


def _op_search(tool_input: dict, context) -> str:
    import memory_db
    return _memory_search(memory_db, tool_input, context.project_path, context.agent_id)


def _op_read(tool_input: dict, context) -> str:
    import memory_db
    return _memory_read(memory_db, tool_input, context.project_path, context.agent_id)


def _op_delete(tool_input: dict, context) -> str:
    import memory_db
    return _memory_delete(memory_db, tool_input, context.project_path, context.agent_id)


def _store(tool_input: dict) -> str:
    return "실행" if str(tool_input.get("store") or "").strip() == "실행" else "심층"


def _op_recall(tool_input: dict, context) -> str:
    """한 가지(node)를 연다 — 문서 전문 + 그 가지의 기억 + 하위 가지. node 없음 = 지도(목차) 전체.
    store:"실행" 이면 실행기억(해마 용례) 주제 트리(backend hippo_tree)를 연다."""
    import memory_db, memory_tree
    if _store(tool_input) == "실행":
        import hippo_tree
        node = hippo_tree.norm_topic(tool_input.get("node") or "")
        if not node and not tool_input.get("node"):
            hippo_tree.sync_all()
            return json.dumps({"success": True, "store": "실행", "node": "", "map": hippo_tree.map_text(),
                               "nodes": hippo_tree.map_lines(), "items": hippo_tree.rows_of(""),
                               "message": "실행기억 지도(목차). 가지를 열려면 node 를 지정하라."}, ensure_ascii=False, indent=2)
        out = hippo_tree.recall(node, expand=tool_input.get("expand"))   # 이름 먼저(2026-09-05): 본문은 expand 로만
        out["store"] = "실행"
        return json.dumps(out, ensure_ascii=False, indent=2)
    db_path = memory_db._get_db_path(context.project_path, context.agent_id)
    node = memory_tree.norm_node(tool_input.get("node") or "")
    if not node and not tool_input.get("node"):
        memory_tree.sync_all(db_path)
        return json.dumps({"success": True, "node": "", "map": memory_tree.map_text(db_path),
                           "nodes": memory_tree.map_lines(db_path),
                           "items": memory_tree.rows_of(db_path, ""),
                           "message": "지도(목차). 가지를 열려면 node 를 지정하라."}, ensure_ascii=False, indent=2)
    out = memory_tree.recall(db_path, node)
    return json.dumps(out, ensure_ascii=False, indent=2)


def _op_move(tool_input: dict, context) -> str:
    """기억 하나를 다른 가지로 옮긴다(memory_id + node)."""
    import memory_db, memory_tree
    memory_id = tool_input.get("memory_id")
    if memory_id is None:
        return json.dumps({"success": False, "error": "memory_id가 필요합니다."}, ensure_ascii=False)
    if "node" not in tool_input:
        return json.dumps({"success": False, "error": "node가 필요합니다(빈 문자열 = 뿌리)."}, ensure_ascii=False)
    if _store(tool_input) == "실행":
        import hippo_tree
        return json.dumps(hippo_tree.move(int(memory_id), tool_input.get("node") or ""), ensure_ascii=False)
    db_path = memory_db._get_db_path(context.project_path, context.agent_id)
    return json.dumps(memory_tree.move(db_path, int(memory_id), tool_input.get("node") or ""), ensure_ascii=False)


# 2026-05-28 dispatcher 표준화 → 2026-08-05 진짜 디스패처로 전환 (music-player 동형).
# --check 가 이 dict 키로 src.ops.values 와 정확 비교 — 키 집합 변경 금지.
_OP_DISPATCHERS = {
    "memory_op": {"save": _op_save, "search": _op_search, "read": _op_read, "delete": _op_delete,
                  "recall": _op_recall, "move": _op_move},
}
# memory_op는 op 필수 — _OP_DEFAULTS 항목 없음.


def _with_success(payload: str) -> str:
    """딕셔너리 봉투에 success 를 채운다 — 규약의 소유자는 `common.currency.stamp_success`.

    비대칭이 있었다: 실패는 `success: false` 를 말하는데 성공은 아무 말도 안 했다
    (`{"memory_id": 500, "message": "…저장 완료…"}`). 그래서 `resp.get("success")` 로
    판정한 쪽이 **성공한 저장을 실패로 읽고 같은 요청을 또 보냈다** — 기억 원장에 같은
    내용이 두 행 생긴 실측(2026-09-07)의 직접 원인이다.

    엔진 경계에도 같은 계약이 있지만(모든 라우터 공유) 여기에도 두는 이유: 이 핸들러는
    엔진 밖에서도 불린다(직접 호출·시험). **두 벌이 아니라 같은 함수**를 부른다.
    산문 반환(read 의 전문)은 그 함수가 통화 모양 그대로 흘린다.
    """
    from common.currency import stamp_success
    return stamp_success(payload)


def execute(tool_input: dict, context) -> str:
    """메모리 & 스킬 도구 실행 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name

    try:
        # 통합 도구 (op 분기) — IBL 어휘에 노출
        if tool_name in _OP_DISPATCHERS:
            import memory_db  # 옛 체인의 op 파싱 전 임포트 위치 보존 (unknown op 여도 로드)
            op = (tool_input.get("op") or "").strip()
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if fn is None:
                return json.dumps({"success": False, "error": f"알 수 없는 op '{op}'. (save|search|read|delete|recall|move)"}, ensure_ascii=False)
            return _with_success(fn(tool_input, context))

        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ============ 에이전트 메모리 도구 ============

def _memory_save(db, tool_input, project_path, agent_id):
    content = tool_input.get("content", "")
    if not content.strip():
        return json.dumps({"success": False, "error": "content가 필요합니다."}, ensure_ascii=False)

    # ★B53-5 (53회차 상상훈련, 2026-09-02): 유효집합 밖 category 는 저장소가 '기타' 로
    #   정규화하는데 종전엔 **말없이** 그랬다 — 같은 값으로 검색하면 영원히 0건(침묵 강등).
    #   정규화 자체는 저장소의 계약(normalize_category 한 벌)이고, 여기서는 그 사실을 신고한다.
    _given = str(tool_input.get("category") or "").strip()
    _used = db.normalize_category(_given)
    _node = str(tool_input.get("node") or "").strip()
    memory_id = db.save(
        project_path=project_path,
        agent_id=agent_id,
        content=content,
        keywords=tool_input.get("keywords", ""),
        category=_used,
        node=_node,
    )

    out = {
        "memory_id": memory_id,
        "node": _node,
        "message": f"메모리 저장 완료 (ID: {memory_id}, 가지: {_node or '뿌리'})",
    }
    if not _node:
        out["hint"] = "node 를 비우면 뿌리(미배치)에 놓인다 — 지도(memory_map)의 가지 이름을 붙이면 그 문서에 실린다."
    if _given and _used != _given:
        _valid = sorted(db.VALID_CATEGORIES)
        out["category_normalized"] = {"given": _given, "used": _used, "valid": _valid}
        out["warning"] = (f"category '{_given}' 은(는) 유효 분류가 아니라 '{_used}' 로 저장했습니다 "
                          f"— 유효: {_valid}. 같은 값으로 검색하면 0건이 됩니다(search 는 이 값을 거절합니다).")
    return json.dumps(out, ensure_ascii=False, indent=2)


def _memory_search(db, tool_input, project_path, agent_id):
    """통합 검색: 심층 메모리 + 대화 이력"""
    query = tool_input.get("query", "")
    if not query.strip():
        return json.dumps({"success": False, "error": "query가 필요합니다."}, ensure_ascii=False)

    # 정본 파라미터=top_k (스키마·문서). limit 은 yaml aliases 로 정규화되지만,
    # 직접 호출(reload 밖 경로) 방어로 여기서도 둘 다 읽는다.
    limit = tool_input.get("top_k", tool_input.get("limit", 10))
    results = []

    # ★B53-5: 저장이 '기타' 로 정규화하는 값을 검색이 원문 그대로 대조하면 영원히 0건 —
    #   유효집합 밖 category 는 0건(침묵) 대신 명시 거절(유효 값 동반). 대칭이 서야 왕복이 산다.
    _cat = str(tool_input.get("category") or "").strip() or None
    if _cat and _cat not in db.VALID_CATEGORIES:
        return json.dumps({
            "success": False, "items": [],
            "error": (f"category '{_cat}' 은(는) 유효 분류가 아닙니다 — 유효: {sorted(db.VALID_CATEGORIES)}. "
                      f"(save 는 이 값을 '기타' 로 정규화해 저장합니다 — 그 기억은 category 없이 query 로 찾으세요)"),
        }, ensure_ascii=False)

    # 1) 심층 메모리 검색
    deep_results = db.search(
        project_path=project_path,
        agent_id=agent_id,
        query=query,
        category=_cat,
        limit=limit
    )
    # node 필터(옵션): 그 가지와 그 아래만
    _node = str(tool_input.get("node") or "").strip().strip("/")
    if _node:
        deep_results = [r for r in deep_results
                        if (r.get("node") or "") == _node or (r.get("node") or "").startswith(_node + "/")]
    for r in deep_results:
        r["source"] = "deep_memory"
    results.extend(deep_results)

    # 2) 대화 이력 검색
    # ★침묵 클램프 청산(2026-08-24 #repair B6): 깎았으면 깎았다고 말한다.
    _conv_req, _conv_lim = limit, min(limit, 5)
    conv_results = _search_conversations(project_path, query, limit=_conv_lim)
    results.extend(conv_results)
    _clamp = ({"clamped": True, "requested": _conv_req,
               "message": f"대화 이력은 상한 {_conv_lim}건까지만 함께 봅니다(요청 {_conv_req})."}
              if _conv_req > _conv_lim else {})

    # 레코드 통화 부착(비파괴) — memories 목록을 records로. >> [table:document/spreadsheet] 파이프용.
    return json.dumps({
        "count": len(results),
        "memories": results,
        "items": _memories_to_records(results),
        **_clamp,
    }, ensure_ascii=False, indent=2)


def _memories_to_records(memories: list) -> list:
    """메모리/대화 검색 결과 → 레코드 통화 records[{title,meta,summary,url}].
    deep_memory 행(preview/category/keywords/created_at) + conversation 행(preview/from_agent/created_at) 두 형태 수용."""
    records = []
    for m in (memories or []):
        if not isinstance(m, dict):
            continue
        preview = m.get("preview") or m.get("content") or ""
        source = m.get("source")
        if source == "conversation":
            frm, to = m.get("from_agent"), m.get("to_agent")
            title = (f"{frm} → {to}" if frm and to else (frm or to or "대화")) or "대화"
            meta = [m.get("created_at"), "대화"]
        else:
            # deep_memory: 별도 제목 없음 → preview 첫 줄을 제목으로.
            title = (preview.split("\n", 1)[0][:60]).strip() or "메모"
            meta = [m.get("created_at"), m.get("category"), m.get("keywords")]
        rec = {
            "title": title,
            "meta": " · ".join(str(x) for x in meta if x),
            "summary": "" if preview == title else preview,
            "url": "",
        }
        # memory_id 병기 (2026-08-16 상상훈련 6회차 B2): desc 계약이 "read/delete —
        # memory_id (search 결과의 id)"인데 카드 투영이 id 를 접어 사슬이 끊겨 있었다.
        if m.get("id") is not None:
            rec["memory_id"] = m["id"]
        records.append(rec)
    return records


def _search_conversations(project_path, query, limit=5):
    """conversations.db에서 대화 이력 검색"""
    conv_db_path = os.path.join(project_path, "conversations.db")
    if not os.path.exists(conv_db_path):
        return []

    try:
        conn = sqlite3.connect(conv_db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT m.id, a_from.name as from_agent, a_to.name as to_agent,
                   substr(m.content, 1, 200) as preview,
                   m.message_time as created_at
            FROM messages m
            LEFT JOIN agents a_from ON m.from_agent_id = a_from.id
            LEFT JOIN agents a_to ON m.to_agent_id = a_to.id
            WHERE m.content LIKE ?
            ORDER BY m.message_time DESC
            LIMIT ?
        """, (f"%{query}%", limit)).fetchall()

        conn.close()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "preview": r["preview"],
                "from_agent": r["from_agent"],
                "to_agent": r["to_agent"],
                "created_at": r["created_at"],
                "source": "conversation"
            })
        return results
    except Exception:
        return []


def _memory_read(db, tool_input, project_path, agent_id):
    memory_id = tool_input.get("memory_id")
    if not memory_id:
        return json.dumps({"success": False, "error": "memory_id가 필요합니다."}, ensure_ascii=False)

    memory = db.read(project_path, agent_id, memory_id)
    if not memory:
        return json.dumps({"success": False, "error": f"ID {memory_id} 메모리 없음"}, ensure_ascii=False)

    parts = [memory['content']]
    meta = []
    if memory.get('created_at'):
        meta.append(f"작성: {memory['created_at']}")
    if memory.get('used_at'):
        meta.append(f"최근참조: {memory['used_at']}")
    if memory['category']:
        meta.append(f"카테고리: {memory['category']}")
    if memory['keywords']:
        meta.append(f"키워드: {memory['keywords']}")
    if meta:
        parts.append(f"[{' | '.join(meta)}]")

    return "\n".join(parts)


def _memory_delete(db, tool_input, project_path, agent_id):
    memory_id = tool_input.get("memory_id")
    if not memory_id:
        return json.dumps({"success": False, "error": "memory_id가 필요합니다."}, ensure_ascii=False)

    deleted = db.delete(project_path, agent_id, memory_id)
    if not deleted:
        # ★못 지운 것을 success 로 내보내면 초크포인트가 거짓을 물들인다(⑧′) —
        #   지울 행이 없었다는 사실은 실패로 말해야 다음 문장이 멈춘다.
        return json.dumps({
            "success": False, "deleted": False, "memory_id": memory_id,
            "error": f"메모리 ID {memory_id} 를 찾지 못해 삭제하지 못했습니다 "
                     f"(이미 지워졌거나 다른 자아·프로젝트의 기억일 수 있습니다).",
        }, ensure_ascii=False, indent=2)
    return json.dumps({
        "success": True, "deleted": True, "memory_id": memory_id,
        "message": f"메모리 ID {memory_id} 삭제 완료"
    }, ensure_ascii=False, indent=2)
