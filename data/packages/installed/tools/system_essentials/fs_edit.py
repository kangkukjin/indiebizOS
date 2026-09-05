"""[self:edit] 근접 실패 진단 — old_string 이 왜 안 맞았는지 말한다.

handler.py 에서 2026-08-22 분리(1500줄 규칙 — handler 는 부채 파일이라 더 못 자란다).

배경: ep1395·ep1393 의 "교체할 문자열을 찾을 수 없습니다" 두 건은 파서 결함이
아니라 **근접 실패**였다 — 내용은 맞는데 들여쓰기·공백이 달랐다(ep1395 는 압축
JSON 으로 썼는데 파일은 6칸 들여쓰기 pretty JSON). 옛 신고는 사유가 없어 매번
grep 한 번을 더 쓰게 했다. 어디가 어떻게 다른지 말해주면 그 왕복이 사라진다.
"""
import re


def _squash(t: str) -> str:
    """공백을 *전부* 뺀다.

    뭉치기(`\\s+` → ' ')로는 부족하다 — 압축 JSON 은 콜론 뒤 공백이 아예 없어서
    pretty 판과 뭉쳐도 안 맞는다(ep1395 실측).
    """
    return re.sub(r"\s+", "", t)


def miss_diagnosis(content: str, old_string: str, new_string: str) -> str:
    """old_string 이 안 맞았을 때 *왜* 안 맞았는지 말한다 (2026-08-22).

    실측한 실패 둘이 전부 근접 실패였다 — 내용은 맞는데 공백·들여쓰기가 달랐다
    (ep1395: 압축 JSON 으로 썼는데 파일은 6칸 들여쓰기). 옛 신고는 사유가 없어
    매번 grep 한 번을 더 쓰게 했다. 확신할 수 없으면 옛 문구 그대로 둔다 —
    추측으로 오도하느니 모른다고 하는 편이 낫다.
    """
    head = "교체할 문자열을 찾을 수 없습니다."

    # ① 이미 적용됨 — 재시도·중복 호출에서 흔하다
    if new_string and new_string in content and new_string != old_string:
        return (f"{head} 다만 new_string 이 이미 파일에 있습니다 — "
                f"앞선 편집이 이미 적용된 것 같습니다. 편집 전에 읽어 확인하세요.")

    # ② 공백 빼면 같음 = 들여쓰기·줄바꿈만 다르다. 파일의 *실제* 모양을 돌려준다
    #    — 그대로 복사하면 다음 시도가 맞는다. 위치를 짚기 위해 공백 뺀 인덱스와
    #    원문 인덱스의 대응표를 들고 다닌다.
    sq_old = _squash(old_string)
    if sq_old:
        sq_content, idx_map = [], []
        for i, ch in enumerate(content):
            if not ch.isspace():
                sq_content.append(ch)
                idx_map.append(i)
        sq_content = "".join(sq_content)
        at = sq_content.find(sq_old)
        if at >= 0:
            start = idx_map[at]
            end = idx_map[min(at + len(sq_old) - 1, len(idx_map) - 1)] + 1
            line_no = content[:start].count("\n") + 1
            actual = content[start:end]
            if len(actual) > 400:
                actual = actual[:400] + "…"
            return (f"{head} 공백·들여쓰기만 다릅니다 — 파일의 실제 모양은 "
                    f"{line_no}행부터 다음과 같습니다(그대로 쓰세요):\n{actual}")

    # ③ 첫 줄은 있는데 뒤가 어긋남 — 어디서 갈렸는지 짚어 준다
    first_line = next((l for l in old_string.split("\n") if l.strip()), "")
    if first_line and first_line in content:
        ln_no = content[:content.index(first_line)].count("\n") + 1
        return (f"{head} 첫 줄은 {ln_no}행에 있으나 그 뒤가 다릅니다 — "
                f"그 자리를 읽어 확인하세요.")

    return f"{head} 파일 내용을 다시 확인하세요."


def replace_line_range(content: str, start_line, end_line, new_string: str, old_string=None) -> dict:
    """[start_line, end_line](1-기반 양끝 포함) 을 new_string 으로 교체 — ""=삭제 (2026-09-05).

    old_string 이 함께 오면 그 범위 안에 있어야 한다(자리 확인 — 줄번호가 옛 읽기의 것일 때 엉뚱한 줄을
    지우는 사고 방지). 반환 {"content", "note"} 또는 {"error"} — 오류문은 범위의 실제 첫 줄을 보여 준다."""
    lines = content.splitlines(keepends=True)
    total = len(lines)
    try:
        s = int(start_line)
        e = int(end_line) if end_line is not None else s
    except (TypeError, ValueError):
        return {"error": "start_line/end_line 은 정수여야 합니다."}
    if s < 1 or e < s or s > total:
        return {"error": f"줄 범위가 파일 밖입니다: {s}~{e} (전체 {total}줄). [self:read]{{numbered: true}} 로 줄번호를 다시 확인하세요."}
    e = min(e, total)
    block = "".join(lines[s - 1:e])
    if old_string and old_string not in block:
        first = lines[s - 1].rstrip("\n")
        if len(first) > 200:
            first = first[:200] + "…"
        return {"error": f"old_string 이 {s}~{e}행 안에 없습니다 — {s}행의 실제 내용: {first!r}. 줄번호가 옛 읽기의 것이면 다시 읽고 고치세요."}
    new = new_string or ""
    if new and not new.endswith("\n") and (e < total or block.endswith("\n")):
        new += "\n"
    out = "".join(lines[:s - 1]) + new + "".join(lines[e:])
    n_new = new.count("\n") if new else 0
    note = f"줄 {s}~{e}({e - s + 1}줄) {'삭제' if not new else f'→ {n_new}줄로 교체'}"
    return {"content": out, "note": note}


