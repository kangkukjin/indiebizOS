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

    try:
        from consciousness_agent import lightweight_ai_call
        resp = lightweight_ai_call(user, system_prompt=_STRUCTURE_PROMPT)
    except Exception as e:
        return _json.dumps({"success": False, "error": f"구조화 AI 호출 실패: {e}"}, ensure_ascii=False)
    if not resp or not resp.strip():
        return _json.dumps({"success": False, "error": "구조화 AI 응답 없음"}, ensure_ascii=False)

    txt = resp.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
        txt = txt.split("```")[0].strip()
    try:
        a, b = txt.find("{"), txt.rfind("}")
        ir = _json.loads(txt[a:b + 1])
    except Exception as e:
        return _json.dumps({"success": False, "error": f"IR JSON 파싱 실패: {e}", "raw": resp[:300]},
                           ensure_ascii=False)
    blocks = ir.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return _json.dumps({"success": False, "error": "blocks가 없습니다.", "raw": resp[:300]},
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
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
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
            cells = lambda s: [c.strip() for c in s.strip().strip("|").split("|")]
            cols = cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            blocks.append({"type": "table", "columns": cols, "rows": rows})
            continue
        m = re.match(r"^\s*(?:[-*+]|(\d+)\.)\s+(.*)$", raw)
        if m:
            if para:
                flush()
            ordered = bool(m.group(1))
            if lst is None or bool(lst.get("ordered")) != ordered:
                if lst:
                    blocks.append(lst)
                lst = {"type": "list", "ordered": ordered, "items": []}
            lst["items"].append(_md_list_item(m.group(2)))
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


def render_document(tool_input, output_base="."):
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
    # 직접 items 파라미터 (조립된 단일 통화 items 전달 — >> 파이프 밖 호출, 예: 데스크탑 신문)
    if not blocks and isinstance(tool_input.get("items"), list) and tool_input["items"]:
        blocks = _items_to_blocks(tool_input["items"], group_by)
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
        return _json.dumps({"success": False, "error": "blocks(문서 IR 블록 배열)가 필요합니다."},
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
    # 산출 위치는 output_base 가 정한다(프로젝트 outputs). filename 에 경로를 적어도 파일명만
    # 취하는데, 예전엔 그걸 말없이 했다 → "원하는 위치에 썼다"고 착각하기 쉬웠다(침묵 실패).
    # 자르는 동작은 유지하되 note 로 소리를 낸다. 원하는 위치로 옮기려면 `>> [self:copy]`.
    if os.path.dirname(_raw_name):
        note += (f" (filename 의 경로 부분은 무시하고 '{base}' 만 씁니다 — 산출 위치는 "
                 f"{output_base}. 다른 곳에 두려면 >> [self:copy]{{destination: ...}})")

    # markdown emitter — 문서 IR → md 텍스트(+.md 파일). NIP-23 발행 등 텍스트 파이프.
    if fmt == "markdown":
        md_text = _doc_blocks_to_markdown(blocks, title, meta)
        out_path = os.path.join(output_base, f"{base}.md")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md_text)
        except Exception:
            out_path = ""
        return _json.dumps({"success": True, "path": out_path, "file": out_path,
                            "title": title, "format": "markdown", "markdown": md_text,
                            "blocks": len(blocks),
                            "message": f"문서 {len(blocks)}블록을 마크다운으로 렌더했습니다.{note}"},
                           ensure_ascii=False)

    # typst emitter — 책 품질 조판 PDF(산문·보고서). HTML theme/cards 그리드는 무시(조판 모델 상이).
    if fmt == "typst":
        try:
            out_path = os.path.join(output_base, f"{base}.pdf")
            _doc_blocks_to_typst(blocks, title, meta, out_path)
            return _json.dumps({"success": True, "path": out_path, "file": out_path,
                                "title": title, "format": "typst_pdf", "blocks": len(blocks),
                                "message": f"문서 {len(blocks)}블록을 typst 책 품질 PDF로 조판했습니다."},
                               ensure_ascii=False)
        except Exception as e:
            note = f" (typst 조판 실패 → 브라우저 PDF 폴백: {e})"
            fmt = "pdf"

    # docx/pptx emitter — 같은 문서 IR을 사무 포맷으로. pptx는 문서 IR을 슬라이드로 *투영*(종류 경계 주의).
    if fmt in ("docx", "pptx"):
        try:
            out_path = os.path.join(output_base, f"{base}.{fmt}")
            if fmt == "docx":
                _doc_blocks_to_docx(blocks, title, out_path)
            else:
                _doc_blocks_to_pptx(blocks, title, out_path)
            return _json.dumps({"success": True, "path": out_path, "file": out_path,
                                "title": title, "format": fmt, "blocks": len(blocks),
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
            out_path = os.path.join(output_base, f"{base}.{fmt}")
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
                                "title": title, "format": fmt, "blocks": len(blocks),
                                "message": f"문서 {len(blocks)}블록을 {fmt.upper()}로 렌더했습니다."},
                               ensure_ascii=False)
        except Exception as e:
            # emitter 실패 시 HTML로 폴백(산출 보존)
            note = f" ({fmt} 렌더 실패 → HTML 폴백: {e})"

    out_path = os.path.join(output_base, f"{base}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return _json.dumps({"success": True, "path": out_path, "file": out_path,
                        "title": title, "format": "html", "blocks": len(blocks),
                        # 렌더된 HTML을 결과에 동봉 — 액션이 다른 몸(맥)으로 포워드돼 파일이
                        # 거기 생겨도, 호출한 몸(폰)이 파일 위치 의존 없이 콘텐츠로 바로 띄운다.
                        "html": doc,
                        "message": f"문서 {len(blocks)}블록을 HTML로 렌더했습니다.{note}"},
                       ensure_ascii=False)

