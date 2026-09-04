"""
chunk_ops.py — [table:chunk] 덩이 변환자 (어휘 개정 2026-09-05, 사용자 판정 — 개정 후보 5). handler.py 에서 분할(1500줄 관문).

긴 문자열 하나(크롤 본문·산문) 또는 본문 열이 있는 items(자막 구간)를 덩이 items 로 자른다 — 자막 84K 가
[table:brief] 입력 상한 6만 자에서 죽던 자리. 이 낱말로 긴 원문 처리가 관용구(자르기 → 덩이마다 brief → 종합)로 조립된다.
"""
import re


_CHUNK_TEXT_FIELDS = ("text", "transcript", "content", "message", "body")


def _chunk_source_text(prev, params):
    """chunk 의 본문 찾기: text 파라미터 > 평문 prev > dict 의 text 계열 필드(field 로 지정 가능). 반환 (본문, 봉투|None, 사유|None)."""
    t = params.get("text")
    if isinstance(t, str) and t.strip():
        return t, None, None
    if isinstance(prev, str):
        return prev, None, None
    if isinstance(prev, dict):
        field = params.get("field")
        if field and isinstance(prev.get(field), str) and prev[field].strip():
            return prev[field], prev, None
        if isinstance(prev.get("items"), list) and prev["items"]:
            return None, prev, None      # items 통화가 있으면 그것이 본문 — 봉투의 message 는 안내문일 때가 많다(자막 op 실측)
        for k in ([field] if field else list(_CHUNK_TEXT_FIELDS)):
            v = prev.get(k) if k else None
            if isinstance(v, str) and v.strip():
                return v, prev, None
        return None, prev, f"chunk: 본문 문자열을 찾지 못했습니다 (찾은 키: {cands}, 받은 키: {list(prev.keys())[:12]}). field 로 지정하세요."
    if isinstance(prev, list):
        return None, {"items": prev}, None
    return None, None, "chunk: 입력이 문자열도 봉투도 아닙니다."


def _chunk_rows(rows, params, size):
    """items 통화(자막 구간·검색 결과처럼 행마다 본문이 있는 것) → 행 경계를 지키며 size 안에 담은 덩이 items.
    field(기본 text 계열 첫 키)의 문자열을 줄바꿈으로 이어 붙인다. start=첫 행 번호, rows=담긴 행 수.
    행 하나가 size 를 넘으면 그 행만 글자로 내려간다(침묵 통짜 금지)."""
    field = params.get("field")
    if not field:
        for r in rows:
            if isinstance(r, dict):
                field = next((k for k in _CHUNK_TEXT_FIELDS if isinstance(r.get(k), str)), None)
                if field:
                    break
    if not field:
        return None, f"chunk: 행에서 본문 키를 찾지 못했습니다 (후보 {list(_CHUNK_TEXT_FIELDS)}, 첫 행 키: {list(rows[0].keys())[:12] if rows and isinstance(rows[0], dict) else '-'}). field 로 지정하세요."
    items, buf, buf_start, cur = [], [], 0, 0
    def _flush():
        if buf:
            piece = "\n".join(buf)
            items.append({"index": len(items), "text": piece, "chars": len(piece), "start": buf_start, "rows": len(buf)})
    for i, r in enumerate(rows):
        t = r.get(field) if isinstance(r, dict) else None
        if not isinstance(t, str) or not t.strip():
            continue
        if len(t) > size:
            _flush(); buf, cur = [], 0
            # 행 하나가 size 를 넘으면 그 행 본문을 by(기본 paragraph — 경계 없으면 줄·글자로 내려감) 규칙으로 자른다
            for sub in _op_chunk(t, {"size": size, "overlap": params.get("overlap", 0), "by": params.get("by", "paragraph")})["items"]:
                items.append({"index": len(items), "text": sub["text"], "chars": sub["chars"], "start": i, "rows": 1})
            continue
        if buf and cur + 1 + len(t) > size:
            _flush(); buf, buf_start, cur = [t], i, len(t)
        else:
            if not buf:
                buf_start = i
            buf.append(t); cur = cur + (1 if cur else 0) + len(t)
    _flush()
    return items, None


def _op_chunk(prev, params):
    """긴 문자열 하나 → 덩이 items (어휘 개정 2026-09-05, 사용자 판정 — 개정 후보 5).

    왜: 자막 84,352자 >> [table:brief] 는 입력 상한 60,000자에서 정직하게 죽고, 안내(take/filter/each)는 items 에만
    듣는다 — 문자열엔 자를 것이 없었다. 이 낱말이 열리면 긴 원문 처리가 낱말 하나(핸들러 안 요약)가 아니라
    관용구(자르기 → 덩이마다 brief → 종합 brief)로 조립된다.
    params: size(덩이 상한 자, 기본 20000) · overlap(겹침 자, 기본 0, chars 만) · by(chars|paragraph|line — paragraph/line 은
    그 경계로 나눈 뒤 size 안에서 이어 붙인다, 기본 paragraph) · field(dict 입력의 본문 키) · text(직접 본문).
    출력 items: {index, text, chars, start} — start 는 원문 안 시작 오프셋(chars) 또는 첫 조각 번호(paragraph/line)."""
    text, env, why = _chunk_source_text(prev, params)
    if why:
        return {"success": False, "error": why}
    try:
        size = int(params.get("size", 20000))
        overlap = int(params.get("overlap", 0))
    except Exception:
        return {"success": False, "error": f"chunk: size/overlap 이 정수가 아닙니다: {params.get('size')!r}/{params.get('overlap')!r}"}
    if size <= 0:
        return {"success": False, "error": "chunk: size 는 1 이상이어야 합니다."}
    if overlap < 0 or overlap >= size:
        return {"success": False, "error": f"chunk: overlap 은 0 이상 size 미만이어야 합니다 (size={size}, overlap={overlap})."}
    by = str(params.get("by", "paragraph") or "paragraph").lower()
    if by not in ("chars", "paragraph", "line"):
        return {"success": False, "error": f"chunk: by 는 chars|paragraph|line 중 하나입니다: {by!r}"}
    items = []
    if text is None and isinstance(env, dict) and isinstance(env.get("items"), list):
        rows = env["items"]
        items, why = _chunk_rows(rows, params, size)
        if why:
            return {"success": False, "error": why}
        out = {"success": True, "items": items, "count": len(items), "source_rows": len(rows),
               "source_chars": sum(it["chars"] for it in items), "by": "rows", "size": size}
        for k in ("video_id", "title", "url", "path", "language"):
            if k in env:
                out[k] = env[k]
        return out
    if by == "chars":
        step = size - overlap
        pos = 0
        while pos < len(text):
            piece = text[pos:pos + size]
            items.append({"index": len(items), "text": piece, "chars": len(piece), "start": pos})
            if pos + size >= len(text):
                break
            pos += step
    else:
        parts = [p for p in re.split(r"\n\s*\n" if by == "paragraph" else r"\n", text) if p.strip()]
        if by == "paragraph" and len(parts) <= 1 and len(text) > size:
            # 문단 경계가 없는 긴 본문(자막 전사 등)은 줄로, 그것도 없으면 글자로 내려간다 — 침묵 통짜 금지
            parts = [p for p in re.split(r"\n", text) if p.strip()]
            if len(parts) <= 1:
                return _op_chunk(prev, {**params, "by": "chars"})
        buf, buf_start, joiner = [], 0, ("\n\n" if by == "paragraph" else "\n")
        def _flush():
            if buf:
                piece = joiner.join(buf)
                items.append({"index": len(items), "text": piece, "chars": len(piece), "start": buf_start})
        for i, p in enumerate(parts):
            if len(p) > size:
                _flush(); buf, buf_start = [], i + 1
                for sub in _op_chunk(p, {"size": size, "overlap": overlap, "by": "chars"})["items"]:
                    items.append({"index": len(items), "text": sub["text"], "chars": sub["chars"], "start": i})
                continue
            cur = len(joiner.join(buf)) if buf else 0
            if buf and cur + len(joiner) + len(p) > size:
                _flush(); buf, buf_start = [p], i
            else:
                if not buf:
                    buf_start = i
                buf.append(p)
        _flush()
    out = {"success": True, "items": items, "count": len(items), "source_chars": len(text),
           "by": by, "size": size, "overlap": overlap}
    if isinstance(env, dict):
        for k in ("video_id", "title", "url", "path", "language"):
            if k in env and k not in out:
                out[k] = env[k]
    return out
