"""doc_build.py — 입력 → 문서 IR(blocks) → 렌더 오케스트레이션 (handler.py 에서 분리, 2026-08-06 1500줄 규칙).

[table:structure]=콘텐츠→문서 IR(경량 LLM 편집자) · [table:document]=문서 IR→포맷.
마크다운 파서·프론트매터·items→blocks 가 여기, blocks→포맷 변환기는 doc_formats.py
(이 모듈이 그쪽을 단방향으로 부른다).
"""
import json
import re
import os

from common.pkg_utils import load_sibling

_fmt = load_sibling(__file__, "doc_formats")
_doc_blocks_to_html = _fmt._doc_blocks_to_html
_doc_css = _fmt._doc_css
_doc_blocks_to_typst = _fmt._doc_blocks_to_typst
_doc_blocks_to_docx = _fmt._doc_blocks_to_docx
_doc_blocks_to_pptx = _fmt._doc_blocks_to_pptx
_doc_blocks_to_markdown = _fmt._doc_blocks_to_markdown

# ── B: 구조화 원자 — 콘텐츠 → 문서 IR (A획득→B구조화→IR→emit 파이프라인) ──
_STRUCTURE_PROMPT = """당신은 콘텐츠를 깔끔한 문서 구조로 정리하는 편집자입니다. 주어진 내용을 문서 IR(JSON)로 변환합니다.

출력은 JSON 한 객체만: {"title": "...", "blocks": [ ... ]}
블록 타입:
- {"type":"heading","level":2,"text":"..."}   (level 1~4)
- {"type":"paragraph","text":"..."}
- {"type":"list","ordered":false,"items":["...","..."]}
- {"type":"table","columns":["...","..."],"rows":[["...","..."]]}
- {"type":"quote","text":"...","cite":"..."}
- {"type":"code","text":"...","lang":"..."}
- {"type":"divider"}

원칙: 내용을 지어내지 말고 주어진 것에서만. title=핵심을 담은 명제. 긴 글은 heading으로 섹션화, 나열은 list, 비교·수치는 table. JSON 외 텍스트 금지."""


def structure_document(tool_input, output_base="."):
    """[table:structure] — 원본 콘텐츠를 문서 IR(blocks)로 구조화 (LLM 편집자).

    파라미터: content(필수, 원본 텍스트) · instruction(선택, 정리 방향).
    반환: {success, title, blocks, block_count}. render_document로 이어 렌더(>> 파이프 지원).
    """
    import json as _json

    content = (tool_input.get("content") or "").strip()
    # >> 파이프: 이전 액션의 텍스트 결과를 content로 받음
    if not content:
        pr = tool_input.get("_prev_result")
        if isinstance(pr, str):
            content = pr.strip()
        elif isinstance(pr, dict):
            content = str(pr.get("summary") or pr.get("content") or pr.get("text") or "").strip()
    if not content:
        return _json.dumps({"success": False, "error": "content(구조화할 원본 내용)가 필요합니다."},
                           ensure_ascii=False)

    instruction = (tool_input.get("instruction") or "").strip()
    user = f"# 정리할 내용\n{content[:16000]}"
    if instruction:
        user += f"\n\n# 정리 방향\n{instruction}"
    user += "\n\n위 내용을 문서 IR(JSON 한 객체)로 출력하라."

    # ★F14-4 (2026-08-20 14회차): oneshot_facade 관문 이관 — JSON 파싱 실패(간헐 출력
    # 잘림 실측)에 되먹임 재시도 1회 + 재실패=정직 실패. role="classify" 명시로 기존
    # 기어 축(경량) 보존 — 관문 이관이 모델 축을 조용히 바꾸면 안 된다(축 변경=판정감).
    try:
        from oneshot_facade import oneshot_json
        ir, err = oneshot_json(user, _STRUCTURE_PROMPT, role="classify")
    except Exception as e:
        return _json.dumps({"success": False, "error": f"구조화 AI 호출 실패: {e}"}, ensure_ascii=False)
    if ir is None:
        return _json.dumps({"success": False, "error": f"IR 생성 실패(재시도 1회 포함): {err}"},
                           ensure_ascii=False)
    if not isinstance(ir, dict):
        return _json.dumps({"success": False, "error": "IR 이 JSON 객체가 아닙니다.",
                            "raw": str(ir)[:300]}, ensure_ascii=False)
    blocks = ir.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return _json.dumps({"success": False, "error": "blocks가 없습니다.",
                            "raw": _json.dumps(ir, ensure_ascii=False)[:300]},
                           ensure_ascii=False)
    return _json.dumps({"success": True, "title": ir.get("title", ""), "blocks": blocks,
                        "block_count": len(blocks),
                        "message": f"{len(blocks)}블록 문서 IR로 구조화."}, ensure_ascii=False)


# records-관습 카드의 표시용 키 — office_ops._RECORDS_ONLY_KEYS 와 동일 판별(2026-08-08 ⑭).
_RECORDS_ONLY_KEYS = {"title", "meta", "summary", "url", "image", "id", "wide", "link", "link_label"}


def _rows_block(rows: list) -> dict:
    """행 dict 목록 → 렌더 가능한 블록 하나 (cards 또는 table).

    ⑭(2026-08-08, 실험 6): cards 렌더러는 title/meta/summary 를 가정한다 — 열린 dict
    (grep 의 파일/줄번호/내용, 도메인 필드 실린 items)를 cards 에 넣으면 **에러 없이
    빈 불릿**이 된다. 통화 계약은 "열린 dict"이므로: 순수 records 카드만 cards,
    그 외엔 전 키를 열로 하는 table 블록(다섯 emitter 전부 table 분기 보유).
    """
    dicts = [r for r in rows if isinstance(r, dict)]
    if dicts and "title" in dicts[0] and set(dicts[0].keys()) <= _RECORDS_ONLY_KEYS:
        return {"type": "cards", "columns": 2, "items": rows}
    if dicts:
        cols = list(dicts[0].keys())
        return {"type": "table", "columns": cols,
                "rows": [[r.get(c) for c in cols] for r in dicts]}
    return {"type": "cards", "columns": 2, "items": rows}


def _items_to_blocks(rows: list, group_by: str = None) -> list:
    """단일 통화 items → 문서 IR 블록. group_by 있으면 그 필드로 섹션(heading+표/카드) 분할.
    이미 문서 IR(type+text) 이면 그대로 반환."""
    if not rows:
        return []
    if isinstance(rows[0], dict) and "type" in rows[0] and "text" in rows[0]:
        return rows  # 이미 문서 IR(산문)
    if group_by:
        groups, order = {}, []
        for r in rows:
            key = str((r.get(group_by) if isinstance(r, dict) else "") or "")
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(r)
        blocks = []
        for key in order:
            if key:
                blocks.append({"type": "heading", "level": 2, "text": key})
            blocks.append(_rows_block(groups[key]))
        return blocks
    return [_rows_block(rows)]


_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)[^)]*\)")
# 강조는 *짝*일 때만 떼어낸다 — 무조건 떼면 snake_case 이름(ai_trend_report_…)이 뭉개진다.
_MD_EMPH = (
    # ★굵게 안에 기울임이 들어간 경우(**… *발행일* …**)도 떼어낸다 — `[^*]+` 는 안쪽 별표를
    # 만나면 짝을 못 찾고 바깥 `**` 를 그대로 흘린다(2026-08-12 실측). 비탐욕이라 짝 규율은 유지.
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__([^_]+)__"), r"\1"),
    (re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])"), r"\1"),
    (re.compile(r"(?<![\w_])_([^_\n]+)_(?![\w_])"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
)


def _md_plain(s: str) -> str:
    """인라인 마크다운 → 평문(링크는 라벨만, 강조 기호 제거). 블록 IR 은 전부 이스케이프된다."""
    text = _MD_LINK.sub(lambda x: x.group(1), s or "")
    for pat, rep in _MD_EMPH:
        text = pat.sub(rep, text)
    return text.strip()


def _md_inline(s: str) -> tuple:
    """인라인 마크다운 한 줄 → (평문, 첫 링크 url)."""
    m = _MD_LINK.search(s or "")
    return _md_plain(s), (m.group(2) if m else "")


def _md_list_item(s: str):
    """목록 한 줄 → 항목. 링크가 있으면 {text, url, note}.

    링크는 *제목에만* 걸고 뒤따르는 설명은 평문 note 로 남긴다 — 줄 전체를 링크로 만들면
    뉴스 한 줄이 통째로 파랗게 되어 읽기 나쁘다(원본 마크다운도 제목만 링크다).
    """
    m = _MD_LINK.search(s or "")
    if not m:
        return _md_plain(s)
    text = _md_plain((s[:m.start()] or "") + m.group(1))
    note = _md_plain(s[m.end():])
    item = {"text": text, "url": m.group(2)}
    if note:
        item["note"] = note
    return item


def _apply_frontmatter(fm: dict, tool_input: dict) -> None:
    """벗겨낸 YAML frontmatter 를 문서 제목·부제로 올린다(호출자가 명시한 값이 이긴다).

    Obsidian vault 의 .md 가 전부 frontmatter 를 이고 있어서, 안 올리면 날짜·출처 같은
    쓸모 있는 메타가 통째로 버려진다(벗기기만 하면 손실). meta 는 'YYYY-MM-DD · 분류' 꼴로 조립.
    """
    if not fm:
        return
    if not (tool_input.get("title") or "").strip():
        t = (fm.get("title") or "").strip()
        if t:
            tool_input["title"] = t
    if not (tool_input.get("meta") or "").strip():
        bits = [b for b in ((fm.get("pub_date") or fm.get("date") or "").strip(),
                            (fm.get("category") or "").strip()) if b]
        if bits:
            tool_input["meta"] = " · ".join(bits)


def _lift_doc_title(blocks: list, tool_input: dict) -> list:
    """글이 스스로 단 첫 제목(# …)을 문서 제목으로 올리고 본문에서 뺀다.

    문서 제목은 마스트헤드 h1 과 <title> 로 렌더되므로, 본문에 그대로 두면 같은 제목이
    두 번 보인다. 호출자가 title 을 명시했으면 그쪽이 이긴다(본문 제목은 그때만 남긴다).
    """
    if not blocks or blocks[0].get("type") != "heading" or int(blocks[0].get("level") or 2) != 1:
        return blocks
    head = blocks[0].get("text") or ""
    given = (tool_input.get("title") or "").strip()
    if not given:
        tool_input["title"] = head
        return blocks[1:]
    if given == head.strip():
        return blocks[1:]
    return blocks


def _markdown_to_blocks(md: str, meta_out: dict = None) -> list:
    """마크다운 텍스트 → 문서 IR 블록. `_doc_blocks_to_markdown` 의 역방향.

    문서를 이미 마크다운으로 갖고 있을 때(보고서·신문·블로그 글) emitter 로 넘기는 입구.
    지원: 제목·목록(순서 유무)·인용·코드펜스·구분선·이미지·표·문단 + YAML frontmatter 제거.

    meta_out: 주면 frontmatter 파싱 결과가 담긴다(본문에서는 빠진다).
    """
    blocks, para, lst = [], [], None
    indents: list = []          # 현재 목록 블록의 들여쓰기 스택 (항목 level 산출용)

    def flush():
        nonlocal para, lst
        if lst:
            blocks.append(lst)
            lst = None
        if para:
            text = " ".join(para).strip()
            if text:
                t, u = _md_inline(text)
                blocks.append({"type": "paragraph", "text": t, **({"url": u} if u else {})})
            para = []

    lines = (md or "").replace("\r\n", "\n").split("\n")

    # YAML frontmatter(`---` … `---`)는 메타지 본문이 아니다 — 벗겨서 meta 로 올린다.
    # 안 벗기면 `post_id: "…" title: "…"` 이 글 맨 위에 그대로 보인다(2026-07-18 블로그
    # 발행에서 실측). Obsidian vault 의 .md 가 전부 이 형식이라 vault→발행 경로 전반에 해당.
    # ★첫 `---` 만 frontmatter 로 본다(본문 중간의 `---` 는 divider 로 남는다).
    # 호출자가 meta_out 을 주면 파싱한 키를 거기 담는다(제목·날짜를 문서 meta 로 쓸 수 있게).
    if lines and lines[0].strip() == "---":
        for _end in range(1, len(lines)):
            if lines[_end].strip() == "---":
                if meta_out is not None:
                    for _fl in lines[1:_end]:
                        if ":" in _fl:
                            _k, _v = _fl.split(":", 1)
                            meta_out[_k.strip()] = _v.strip().strip('"').strip("'")
                lines = lines[_end + 1:]
                break

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if line.startswith("```"):                       # 코드 펜스 — 안쪽은 날것 그대로
            flush()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            blocks.append({"type": "code", "text": "\n".join(buf)})
            i += 1
            continue
        if not line:
            flush()
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", line):
            flush()
            blocks.append({"type": "divider"})
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            t, _u = _md_inline(m.group(2))
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": t})
            i += 1
            continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)\s]+)[^)]*\)$", line)
        if m:
            flush()
            blocks.append({"type": "image", "src": m.group(2), "caption": m.group(1)})
            i += 1
            continue
        if line.startswith(">"):
            flush()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            cite = ""
            if buf and buf[-1].startswith("—"):
                cite = buf.pop().lstrip("—").strip()
            t, _u = _md_inline(" ".join(buf))
            blocks.append({"type": "quote", "text": t, **({"cite": cite} if cite else {})})
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(
                r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            flush()
            # ★셀도 인라인 마크다운을 벗긴다 — 안 벗기면 `**6,345.53**` 이 별표째 렌더된다
            # (2026-08-12 실측: AI 동향 보고서 시세표·추이표. 문단·목록·제목은 _md_inline 을
            #  타는데 표만 날것이라 강조하려던 숫자가 오히려 지저분해졌다. IR 은 평문 계약이다.)
            cells = lambda s: [_md_plain(c.strip()) for c in s.strip().strip("|").split("|")]
            cols = cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            blocks.append({"type": "table", "columns": cols, "rows": rows})
            continue
        m = re.match(r"^(\s*)(?:[-*+]|(\d+)\.)\s+(.*)$", raw)
        if m:
            if para:
                flush()
            ordered = bool(m.group(2))
            if lst is None or bool(lst.get("ordered")) != ordered:
                if lst:
                    blocks.append(lst)
                lst = {"type": "list", "ordered": ordered, "items": []}
                indents = []
            # 들여쓰기 → 항목 level(0=최상위). 안 재면 하위 불릿이 형제로 평평해져
            # 종속 관계가 사라진다(2026-08-12 실측: "부수 발견 둘:" 아래 두 항목).
            # 들여쓰기 폭은 문서마다 2·4칸이 섞이므로 절대 폭이 아니라 *등장 순서*로 센다.
            ind = len(m.group(1).expandtabs(4))
            while indents and ind < indents[-1]:
                indents.pop()
            if not indents or ind > indents[-1]:
                indents.append(ind)
            level = len(indents) - 1
            item = _md_list_item(m.group(3))
            if level:
                item = {"text": item} if not isinstance(item, dict) else item
                item["level"] = level
            lst["items"].append(item)
            i += 1
            continue
        if lst:                                          # 목록 뒤 들여쓴 줄 = 앞 항목의 이어짐
            if raw.startswith(("  ", "\t")) and lst["items"]:
                t = _md_plain(line)
                last = lst["items"][-1]
                if isinstance(last, dict):
                    last["note"] = f"{last.get('note','')} {t}".strip()
                else:
                    lst["items"][-1] = f"{last} {t}".strip()
                i += 1
                continue
            blocks.append(lst)
            lst = None
        para.append(line)
        i += 1
    flush()
    return blocks


class _PlacementRefused(Exception):
    """산출 경로 해소기가 범위를 이유로 거절 — 사용자 봉투로 그대로 올린다."""


def _apply_when(blocks):
    """블록 조건부 절 `when` (언어 개정 2026-08-28, 사용자 판정 "언어의 한계는 다 고쳐").

    블록에 when 이 있으면 그 값(치환 후 도착)이 **비어 있을 때 블록을 떨군다** —
    "함의 없으면 섹션 자체를 생략(빈 줄도 남기지 않는다)" 류의 가이드 규약을 blocks 로
    쓸 수 있게. 빈 값 = null / 빈 문자열·공백뿐 / 빈 배열·객체 / JSON 문자열로 온 그것들.
    when 키는 렌더 전에 벗긴다(문서에 배관을 남기지 않음). 반환: (blocks, 떨군 수) —
    떨궜으면 호출자가 blocks_omitted 로 신고한다(침묵 클램프 금지).
    """
    from common.currency import coerce_json_param as _coerce
    if not (isinstance(blocks, list) and any(isinstance(b, dict) and "when" in b for b in blocks)):
        return blocks, 0
    kept, omitted = [], 0
    for b in blocks:
        if isinstance(b, dict) and "when" in b:
            w = _coerce(b.get("when"))
            empty = (w is None or (isinstance(w, str) and not w.strip())
                     or (isinstance(w, (list, dict)) and not w))
            if empty:
                omitted += 1
                continue
            b = {k: v for k, v in b.items() if k != "when"}
        kept.append(b)
    return kept, omitted


def render_document(tool_input, output_base=".", context=None):
    """[table:document] 진입점. 경로 거절만 여기서 봉투로 바꾸고 나머지는 본체가 한다."""
    import json as _json
    try:
        return _render_document(tool_input, output_base, context)
    except _PlacementRefused as e:
        return _json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _render_document(tool_input, output_base=".", context=None):
    """문서 IR → 산출물. emitter: html/pdf/png/docx/pptx/typst/markdown.

    파라미터: blocks 또는 items(단일 통화 — group_by로 섹션 분할) · title · meta ·
    format(기본 html) · group_by(선택, items 섹션 필드) · filename(선택).
    반환: {success, path, format, blocks, (markdown 시)markdown}.
    """
    import os
    import html as _html
    import json as _json

    def _table_block_of(src):
        """봉투/입력의 표 통화({table:{columns,rows}} 또는 최상위 columns/rows) → table 블록.

        ⑭(2026-08-08): 이 입구가 없어 select 가 만든 표가 통째로 버려지고 빈 문서가
        success 로 나갔다.
        """
        if not isinstance(src, dict):
            return None
        t = src.get("table") if isinstance(src.get("table"), dict) else None
        holder = t if t is not None else src
        cols, rows = holder.get("columns"), holder.get("rows")
        if isinstance(cols, list) and isinstance(rows, list) and rows:
            return {"type": "table", "columns": cols, "rows": rows}
        return None

    group_by = (tool_input.get("group_by") or "").strip() or None
    blocks = tool_input.get("blocks")
    # ★blocks 의 `$변수` 주입 되읽기 (2026-08-27, B19-2 부류의 blocks 판): 변수 치환은
    #   JSON 문자열을 넣는다. blocks 전체("$구조.blocks")와 블록 안 구조 필드
    #   (table 의 columns/rows, list/cards 의 items)가 문자열로 오면 원형으로 되읽는다 —
    #   실측: `columns: "$표.columns"` 가 문자열로 들어가 표 헤더가 문자 단위로 쪼개졌다.
    #   text 류 필드는 건드리지 않는다(산문을 뺏지 않는다) — 구조 필드만.
    from common.currency import coerce_json_param as _coerce_param
    blocks = _coerce_param(blocks)
    if isinstance(blocks, list):
        blocks = [
            ({**b, **{k: _coerce_param(b[k]) for k in ("columns", "rows", "items") if k in b}}
             if isinstance(b, dict) else b)
            for b in blocks
        ]
    # 통화 도착 여부/기수 기록 (29회차 B29-1) — "입력이 아예 없다"와 "통화는 왔는데 0행"은
    # 다른 사건이다. 뒤엣것을 "blocks 가 필요합니다"로 보고하면 사용자는 자기가 줄 필요도
    # 없는 파라미터를 찾아 헤맨다(같은 파이프가 행이 있을 땐 blocks 없이 잘 흐른다).
    _arrived_rows = None
    # 직접 items 파라미터 (조립된 단일 통화 items 전달 — >> 파이프 밖 호출, 예: 데스크탑 신문)
    # ★2026-08-27: list 만 보던 탓에 `[table:document]{items: "$변수"}` 가 죽었다 —
    #   변수 치환은 통화를 **JSON 문자열**로 넣는다(B19-2 가 each·reduce·ai·brief 에 대해
    #   이미 세운 정본을 emitter 가 안 쓰고 있었다). 되읽기는 몸의 정본 하나로.
    from common.currency import coerce_items_payload as _coerce_items
    _inline = _coerce_items(tool_input.get("items"))
    if isinstance(_inline, list):
        _arrived_rows = len(_inline)
    if not blocks and _inline:
        blocks = _items_to_blocks(_inline, group_by)
    # 직접 표 통화 (인라인 table/columns+rows — spreadsheet 인라인 items 와 같은 부류)
    if not blocks:
        _tb = _table_block_of(tool_input)
        if _tb:
            blocks = [_tb]
    # 마크다운 텍스트 입구 — 이미 글로 존재하는 문서(보고서·신문·블로그)를 emitter 로.
    if not blocks and isinstance(tool_input.get("markdown"), str) and tool_input["markdown"].strip():
        _fm = {}
        blocks = _markdown_to_blocks(tool_input["markdown"], meta_out=_fm)
        _apply_frontmatter(_fm, tool_input)
        blocks = _lift_doc_title(blocks, tool_input)
    if not blocks:
        # >> 파이프: 이전 생산자 결과(_prev_result)의 blocks·items·title·meta·theme 자동 수용
        pr = tool_input.get("_prev_result")
        if pr:
            try:
                po = pr
                if isinstance(pr, str):
                    try:
                        po = _json.loads(pr)
                    except Exception:
                        po = None
                    # JSON 이 아닌 앞 단계 문자열 = 글 그대로(예: [self:read] 가 읽은 .md)
                    if not isinstance(po, dict):
                        _fm = {}
                        _b = _markdown_to_blocks(pr, meta_out=_fm)
                        _apply_frontmatter(_fm, tool_input)
                        blocks = _lift_doc_title(_b, tool_input)
                        po = None
                if isinstance(po, dict):
                    if isinstance(po.get("items"), list):
                        _arrived_rows = len(po["items"])
                    if po.get("blocks"):
                        blocks = po["blocks"]
                    elif isinstance(po.get("items"), list) and po["items"]:
                        # 단일 통화 items → 표/카드(또는 group_by 섹션) 블록. IR(type+text)이면 그대로.
                        blocks = _items_to_blocks(po["items"], group_by)
                    else:
                        # 표 통화(columns/rows) 입구 — select/groupby 산출이 items 없이 표만 나를 때(⑭)
                        _tb = _table_block_of(po)
                        if _tb:
                            blocks = [_tb]
                    # 원천 절단 신고(⑥′ 연동) — 절단된 표본을 문서가 전량인 척 싣지 않게
                    if blocks and isinstance(blocks, list) and po.get("truncated"):
                        tot = po.get("total")
                        blocks = list(blocks) + [{"type": "paragraph", "text":
                            "※ 원 데이터가 절단된 표본입니다"
                            + (f" (총 {tot}건 중 일부만 수집됨)" if tot else "") + "."}]
                    for k in ("title", "meta", "theme"):
                        if not tool_input.get(k) and po.get(k):
                            tool_input[k] = po[k]
            except Exception:
                pass
    if isinstance(blocks, str):
        try:
            blocks = _json.loads(blocks)
        except Exception:
            blocks = None
    if not isinstance(blocks, list) or not blocks:
        if _arrived_rows == 0:
            return _json.dumps({"success": False, "rows_in": 0,
                                "error": ("입력 0행 — 문서로 렌더할 내용이 없습니다. 앞 단계가 통화를 "
                                          "넘겼지만 행이 하나도 없습니다(blocks 를 직접 줄 필요는 "
                                          "없습니다 — 앞 단계의 필터·검침을 보세요).")},
                               ensure_ascii=False)
        return _json.dumps({"success": False, "error": "blocks(문서 IR 블록 배열)가 필요합니다."},
                           ensure_ascii=False)

    # 조건부 절 — 모든 입구(직접 blocks·파이프 유입·markdown 파싱)를 지난 뒤 한 자리에서.
    blocks, _omitted_when = _apply_when(blocks)
    if not blocks:
        return _json.dumps({"success": True, "blocks": 0, "blocks_omitted": _omitted_when,
                            "message": f"when 조건으로 전 블록({_omitted_when})이 생략돼 "
                                       "렌더할 내용이 없습니다 — 파일을 만들지 않았습니다."},
                           ensure_ascii=False)

    title = tool_input.get("title") or ""
    meta = tool_input.get("meta") or ""
    theme = (tool_input.get("theme") or "default").strip().lower()
    fmt = (tool_input.get("format") or "html").strip().lower()
    if fmt == "md":
        fmt = "markdown"
    note = ""
    if fmt not in ("html", "pdf", "png", "docx", "pptx", "typst", "markdown"):
        note = f" (format '{fmt}' 미지원 — html로 산출)"
        fmt = "html"

    os.makedirs(output_base, exist_ok=True)
    _raw_name = str(tool_input.get("filename") or "document")
    base = os.path.splitext(os.path.basename(_raw_name))[0] or "document"
    # 산출 위치 — 형제 emitter 와 같은 해소기 하나(ToolContext.resolve_output_path, J29-1).
    # 옛 동작은 filename 의 경로 부분을 *버리고* note 로 고지했다. 고지는 정직했지만
    # 사용자가 준 경로를 지키지 않는 것 자체가 규약 불일치였다(spreadsheet 는 지켰다).
    # 이제 준 경로를 지킨다 — bare 파일명은 여전히 outputs/ 로 간다(가장 흔한 경우 무변화).
    # 확장자는 format 이 정하므로 여기서 붙이고, 배치만 해소기에 맡긴다.
    _dirpart = os.path.dirname(_raw_name)
    _outdir = output_base   # 확장자별 out_path 조립의 기준 — 아래에서 해소 결과로 덮인다

    def _place(ext: str) -> str:
        """base+ext 를 몸의 단일 규약으로 배치한 절대경로. 해소 실패는 예외로 올린다.

        ★2026-08-27: 기본 이름(`document.*`)은 두 번 부르면 **앞 산출물을 말없이 덮어썼다**
        (23·24회차 원장이 '보고만' 으로 남긴 항목 — 매일 보고서를 두 번 뽑으면 아침 판이
        사라지고 봉투는 아무 말도 안 했다). 위치 규약은 그대로 둔다(파일이 어디 생기는지를
        바꾸는 것은 사용자 판정 사안 — F29-2). 대신 **덮어썼다는 사실을 말한다**:
        `note` 는 모든 format 분기의 message 에 실리므로 한 자리로 전 분기가 정직해진다.
        """
        nonlocal note
        _name = f"{base}{ext}"
        if context is None or not hasattr(context, "resolve_output_path"):
            # 구 호출자(context 없음) — 옛 동작 유지. 있는 척하지 않는다.
            _p = os.path.join(output_base, _name)
        else:
            _r = context.resolve_output_path(
                os.path.join(_dirpart, _name) if _dirpart else _name)
            if _r.get("error"):
                raise _PlacementRefused(_r["error"])
            _p = _r["path"]
        if os.path.exists(_p):
            note += (f" ★기존 파일을 덮어썼습니다: {_p}"
                     " — 앞 산출물을 남기려면 filename 으로 다른 이름을 주세요.")
        return _p

    # markdown emitter — 문서 IR → md 텍스트(+.md 파일). NIP-23 발행 등 텍스트 파이프.
    if fmt == "markdown":
        md_text = _doc_blocks_to_markdown(blocks, title, meta)
        out_path = _place(".md")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md_text)
        except Exception:
            out_path = ""
        return _json.dumps({"success": True, "path": out_path, "file": out_path,
                            "title": title, "format": "markdown", "markdown": md_text,
                            "blocks": len(blocks), **({"blocks_omitted": _omitted_when} if _omitted_when else {}),
                            "message": f"문서 {len(blocks)}블록을 마크다운으로 렌더했습니다.{note}"},
                           ensure_ascii=False)

    # typst emitter — 책 품질 조판 PDF(산문·보고서). HTML theme/cards 그리드는 무시(조판 모델 상이).
    if fmt == "typst":
        try:
            out_path = _place(".pdf")
            _doc_blocks_to_typst(blocks, title, meta, out_path)
            return _json.dumps({"success": True, "path": out_path, "file": out_path,
                                "title": title, "format": "typst_pdf", "blocks": len(blocks), **({"blocks_omitted": _omitted_when} if _omitted_when else {}),
                                "message": f"문서 {len(blocks)}블록을 typst 책 품질 PDF로 조판했습니다."},
                               ensure_ascii=False)
        except Exception as e:
            note = f" (typst 조판 실패 → 브라우저 PDF 폴백: {e})"
            fmt = "pdf"

    # docx/pptx emitter — 같은 문서 IR을 사무 포맷으로. pptx는 문서 IR을 슬라이드로 *투영*(종류 경계 주의).
    if fmt in ("docx", "pptx"):
        try:
            out_path = _place(f".{fmt}")
            if fmt == "docx":
                _doc_blocks_to_docx(blocks, title, out_path)
            else:
                _doc_blocks_to_pptx(blocks, title, out_path)
            return _json.dumps({"success": True, "path": out_path, "file": out_path,
                                "title": title, "format": fmt, "blocks": len(blocks), **({"blocks_omitted": _omitted_when} if _omitted_when else {}),
                                "message": f"문서 {len(blocks)}블록을 {fmt.upper()}로 렌더했습니다."},
                               ensure_ascii=False)
        except Exception as e:
            note = f" ({fmt} 렌더 실패 → HTML 폴백: {e})"
            fmt = "html"

    body = _doc_blocks_to_html(blocks)
    title_h = f"<h1>{_html.escape(str(title))}</h1>" if title else ""
    meta_h = f'<div class="doc-meta">{_html.escape(str(meta))}</div>' if meta else ""
    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>{_html.escape(str(title))}</title><style>{_doc_css(theme)}</style></head><body>
<div class="docwrap">
{title_h}
{meta_h}
{body}
</div>
</body></html>"""

    # 같은 문서 IR을 여러 emitter로 — html/pdf/png. pdf·png는 Playwright로 동일 HTML 렌더.
    if fmt in ("pdf", "png"):
        try:
            from playwright.sync_api import sync_playwright
            out_path = _place(f".{fmt}")
            with sync_playwright() as pw:
                br = pw.chromium.launch()
                pg = br.new_page(viewport={"width": 900, "height": 1200})
                pg.set_content(doc, wait_until="networkidle")
                pg.wait_for_timeout(300)
                if fmt == "pdf":
                    pg.pdf(path=out_path, format="A4", print_background=True,
                           margin={"top": "20mm", "bottom": "20mm", "left": "16mm", "right": "16mm"})
                else:
                    pg.screenshot(path=out_path, full_page=True)
                br.close()
            return _json.dumps({"success": True, "path": out_path, "file": out_path,
                                "title": title, "format": fmt, "blocks": len(blocks), **({"blocks_omitted": _omitted_when} if _omitted_when else {}),
                                "message": f"문서 {len(blocks)}블록을 {fmt.upper()}로 렌더했습니다."},
                               ensure_ascii=False)
        except Exception as e:
            # emitter 실패 시 HTML로 폴백(산출 보존)
            note = f" ({fmt} 렌더 실패 → HTML 폴백: {e})"

    out_path = _place(".html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return _json.dumps({"success": True, "path": out_path, "file": out_path,
                        "title": title, "format": "html", "blocks": len(blocks), **({"blocks_omitted": _omitted_when} if _omitted_when else {}),
                        # 렌더된 HTML을 결과에 동봉 — 액션이 다른 몸(맥)으로 포워드돼 파일이
                        # 거기 생겨도, 호출한 몸(폰)이 파일 위치 의존 없이 콘텐츠로 바로 띄운다.
                        "html": doc,
                        "message": f"문서 {len(blocks)}블록을 HTML로 렌더했습니다.{note}"},
                       ensure_ascii=False)

