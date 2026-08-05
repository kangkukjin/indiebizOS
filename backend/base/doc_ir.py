"""doc_ir — 문서 IR(공유 문서 모델) 변환 유틸.

문서 IR = {title?, blocks:[{type, ...}]}. 블록 타입:
  heading{level,text} · paragraph{text} · list{ordered?,items[]} · image{src,caption?}
  · table{columns,rows}(데이터 통화 재사용) · quote{text,cite?} · code{text,lang?} · divider

ibl.md '표현 언어의 층위' 조항의 규율 — 문서 IR은 표준 외부 언어(Markdown)와
동형인 구간을 변환자로 왕복 가능하게 유지한다 — 의 Markdown→IR 방향이 이 모듈.
(IR→산출물 방향은 data-ops 의 render_document emitter 들.)

소비자:
  - system_essentials read(blocks:true) — md/텍스트 파일을 타입 있는 IR items 로
    (docx·pdf 읽기는 이미 자체 IR 방출 — 이 모듈로 md 경로가 합류해 3경로 정렬)
  - blocks 뷰 프리미티브(표면 언어) — 표면 렌더러(TSX/JS)는 IR만 소비, md 파싱 없음

stdlib 전용(re) — 폰 import-safe.
"""

import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
_IMAGE_RE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)\s]+)[^)]*\)\s*$")


def _split_table_row(line: str) -> list:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def markdown_to_blocks(text: str) -> list:
    """Markdown 텍스트 → 문서 IR 블록 배열.

    커버: heading(#) / 펜스 코드(```) / 인용(>) / 순서·비순서 목록 / 구분선(---)
    / 파이프 표(|헤더|…| + 구분행) / 단독 이미지(![cap](src)) / 문단.
    인라인 강조(**·`·링크)는 IR 에서 원문 보존 — 렌더러의 인라인 패스 몫.
    모르는 구조는 문단으로 강등(비파괴)."""
    blocks: list = []
    lines = (text or "").splitlines()
    i, n = 0, len(lines)
    para_buf: list = []

    def flush_para():
        if para_buf:
            joined = "\n".join(para_buf).strip()
            if joined:
                blocks.append({"type": "paragraph", "text": joined})
            para_buf.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        # 펜스 코드
        if stripped.startswith("```"):
            flush_para()
            lang = stripped[3:].strip() or None
            body = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # 닫는 펜스
            blk = {"type": "code", "text": "\n".join(body)}
            if lang:
                blk["lang"] = lang
            blocks.append(blk)
            continue

        # 제목
        m = _HEADING_RE.match(stripped)
        if m:
            flush_para()
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue

        # 구분선
        if _HR_RE.match(stripped):
            flush_para()
            blocks.append({"type": "divider"})
            i += 1
            continue

        # 인용 (연속 > 줄 병합)
        if stripped.startswith(">"):
            flush_para()
            q = []
            while i < n and lines[i].strip().startswith(">"):
                q.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append({"type": "quote", "text": "\n".join(q).strip()})
            continue

        # 파이프 표 (헤더행 + 구분행)
        if stripped.startswith("|") and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]):
            flush_para()
            columns = _split_table_row(stripped)
            rows = []
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_table_row(lines[i]))
                i += 1
            blocks.append({"type": "table", "columns": columns, "rows": rows})
            continue

        # 목록 (연속 목록 줄 병합, 첫 줄 종류가 ordered 결정)
        bm, om = _BULLET_RE.match(line), _ORDERED_RE.match(line)
        if bm or om:
            flush_para()
            ordered = bool(om) and not bm
            items = []
            while i < n:
                lb, lo = _BULLET_RE.match(lines[i]), _ORDERED_RE.match(lines[i])
                lm = lb or lo
                if not lm:
                    break
                items.append(lm.group(1).strip())
                i += 1
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue

        # 단독 이미지
        m = _IMAGE_RE.match(stripped)
        if m:
            flush_para()
            blk = {"type": "image", "src": m.group(2)}
            if m.group(1):
                blk["caption"] = m.group(1)
            blocks.append(blk)
            i += 1
            continue

        para_buf.append(line)
        i += 1

    flush_para()
    return blocks
