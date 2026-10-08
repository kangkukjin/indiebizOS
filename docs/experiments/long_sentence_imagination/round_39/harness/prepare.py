"""39회차 합성 문서 묶음·변형·독립 oracle. IBL 과제 계산은 하지 않는다(oracle 은 대조용, AI 입력 사본에서 제외).

사용: prepare.py generate   — source/docs 에 36 파일 생성, trainer/docs·agent/docs 사본, *_bad 변형(guide_07.md 무효 UTF-8)
      prepare.py oracle     — oracle/expected_docs(기대 산출 파일)·oracle/report.json(기대 보고 값) 기록
"""
import hashlib
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_39회차'
TERMS = [("구독 플랜", "요금제"), ("워크스페이스", "작업 공간")]
SLUG_STRIP = ".,:()!?`"


def slug(text):
    t = text.strip().lower()
    for ch in SLUG_STRIP:
        t = t.replace(ch, "")
    return t.strip().replace(" ", "-")


# ---------- 생성 ----------
FILES = ["index.md"] + [f"guide_{i:02d}.md" for i in range(1, 21)] + [f"api_{i:02d}.md" for i in range(1, 11)] \
    + ["faq.md", "glossary.md", "changelog.md", "plans.md", "workspace.md"]

HEAD_POOL = [
    "구독 플랜 변경하기", "구독 플랜 비교", "워크스페이스 만들기", "워크스페이스 초대", "결제 수단",
    "요청 형식", "응답 코드", "오류 처리", "한도와 제한", "모범 사례", "문제 해결", "예제: 구독 플랜 조회",
    "워크스페이스 설정 (고급)", "자주 묻는 질문", "용어", "버전 이력", "플랜 갱신 주기", "팀 관리",
]
PARA_POOL = [
    "{T0}을 바꾸면 다음 결제일부터 새 금액이 적용된다.",
    "각 {T1}는 독립된 권한 경계를 가진다. {T1}들 사이의 자료 이동은 내보내기로만 가능하다.",
    "플랜 이름은 대소문자를 구분하지 않는다. 다만 `{T0}` 필드는 원문 그대로 저장된다.",
    "이 절차는 관리자만 수행할 수 있다. 자세한 조건은 아래 표를 참고한다.",
    "응답에는 `workspace_id`와 `plan` 두 필드가 포함된다.",
    "{T1} 이름은 생성 뒤 바꿀 수 있지만 식별자는 바뀌지 않는다.",
    "현재 {T0}의 남은 기간은 일 단위로 내려온다.",
    "오류가 반복되면 재시도 간격을 두 배로 늘린다.",
]
CODE_POOL = [
    "```json\n{\"plan\": \"구독 플랜\", \"workspace\": \"워크스페이스\"}\n```",
    "```bash\ncurl -X GET https://api.example.test/v1/plans  # 구독 플랜 조회\n```",
    "```python\n# 워크스페이스 목록\nfor ws in client.workspaces():\n    print(ws.name)  # [구독 플랜](plans.md#구독-플랜-비교)\n```",
]


def generate():
    rng = random.Random(39)
    src = OUT / 'source' / 'docs'
    if OUT.exists():
        shutil.rmtree(OUT)
    src.mkdir(parents=True)
    headings = {}  # file -> list of heading texts
    for f in FILES:
        hs = rng.sample(HEAD_POOL, 4)
        if f == "api_03.md":
            hs[1] = "`구독 플랜` 객체"       # 인라인 코드 제목: 앵커는 그대로여야 함
        if f == "plans.md":
            hs[0] = "구독 플랜 비교"
        if f == "workspace.md":
            hs[0] = "워크스페이스 만들기"
        headings[f] = hs
    broken_plan = {"guide_02.md": ("missing.md", None), "guide_11.md": ("missing.md", "구독-플랜-비교"),
                   "api_05.md": ("plans.md", "없는-절"), "faq.md": ("workspace.md", "없는-절"), "changelog.md": ("old_notes.md", None)}
    for f in FILES:
        lines = [f"# {f[:-3].replace('_', ' ').title()} 안내", ""]
        for hi, h in enumerate(headings[f]):
            lines.append(("## " if hi % 2 == 0 else "### ") + h)
            lines.append("")
            for _ in range(2):
                p = rng.choice(PARA_POOL).replace("{T0}", "구독 플랜").replace("{T1}", "워크스페이스")
                lines.append(p)
            # 링크 2개: 다른 파일의 제목 앵커 1 + 파일만 1
            other = rng.choice([x for x in FILES if x != f])
            oh = rng.choice(headings[other])
            lines.append(f"자세한 내용은 [{oh}]({other}#{slug(oh)})과 [{other[:-3]} 문서]({other})를 본다.")
            if hi == 1:
                lines.append(rng.choice(CODE_POOL))
            if hi == 2:
                # 같은 파일 앵커
                lines.append(f"- 위 [{headings[f][0]}](#{slug(headings[f][0])}) 절 참고")
                lines.append("- 두 번째 항목: 워크스페이스 전환은 상단 메뉴에서 한다")
            lines.append("")
        if f in broken_plan:
            tgt, anc = broken_plan[f]
            lines.append(f"참고: [옛 문서]({tgt}{'#' + anc if anc else ''})는 이전 판이다.")
            lines.append("")
        (src / f).write_text("\n".join(lines) + "\n", encoding="utf-8")
    for who in ("trainer", "agent"):
        shutil.copytree(src, OUT / who / 'docs')
        bad = OUT / who / 'docs_bad'
        shutil.copytree(src, bad)
        (bad / 'guide_07.md').write_bytes(b"# \xff\xfe \xea\xb5\xac\xeb\x8f\x85 \xed\x94\x8c\xeb\x9e\x9c\n\n\xc7\xd1\xb1\xdb cp949 \xbf\xf8\xb9\xae\n")
        (OUT / who / 'out').mkdir(parents=True, exist_ok=True)
        (OUT / who / 'out_bad').mkdir(parents=True, exist_ok=True)
    print("generated", len(FILES), "files ->", src)


# ---------- oracle (독립 구현) ----------
def convert_line_prose(seg, anchor_map, cur_file):
    """prose 조각: 링크 대상은 용어 치환 없이 앵커만 재매핑, 나머지 텍스트는 용어 치환."""
    parts = seg.split("](")
    out = [replace_terms(parts[0])]
    for part in parts[1:]:
        if ")" in part:
            target, rest = part.split(")", 1)
            out.append(remap_target(target, anchor_map, cur_file) + ")" + replace_terms(rest))
        else:
            out.append(replace_terms(part))
    return "](".join(out)


def replace_terms(text):
    for old, new in TERMS:
        text = text.replace(old, new)
    return text


def remap_target(target, anchor_map, cur_file):
    if "#" not in target:
        return target
    fpart, anc = target.split("#", 1)
    key = ((fpart or cur_file), anc)
    if key in anchor_map:
        return fpart + "#" + anchor_map[key]
    return target


def convert_line(line, anchor_map, cur_file):
    segs = line.split("`")
    return "`".join(convert_line_prose(s, anchor_map, cur_file) if i % 2 == 0 else s for i, s in enumerate(segs))


def count_terms(text):
    return sum(text.count(old) for old, _ in TERMS)


def heading_text(line):
    return line.lstrip("#").strip()


def oracle():
    src = OUT / 'source' / 'docs'
    files = sorted(p.name for p in src.glob("*.md"))
    texts = {f: (src / f).read_text(encoding="utf-8") for f in files}
    # 1) 제목 수집 → 앵커 맵
    old_slugs, anchor_map, headings_changed = {}, {}, []
    for f in files:
        old_slugs[f] = set()
        in_fence = False
        for line in texts[f].split("\n"):
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not line.startswith("#"):
                continue
            ht = heading_text(line)
            new_ht = heading_text(convert_line(line, {}, f))
            old_slugs[f].add(slug(ht))
            if slug(ht) != slug(new_ht):
                anchor_map[(f, slug(ht))] = slug(new_ht)
                headings_changed.append({"file": f, "old": slug(ht), "new": slug(new_ht)})
    # 2) 변환 + 보고
    exp = OUT / 'oracle' / 'expected_docs'
    if exp.exists():
        shutil.rmtree(exp)
    exp.mkdir(parents=True)
    per_file, broken_before, replacements, anchors_remapped = {}, [], 0, 0
    for f in files:
        out_lines, in_fence = [], False
        for ln, line in enumerate(texts[f].split("\n"), 1):
            if line.startswith("```"):
                in_fence = not in_fence
                out_lines.append(line)
                continue
            if in_fence:
                out_lines.append(line)
                continue
            # 링크 검사(인라인 코드 밖)
            segs = line.split("`")
            for i, s in enumerate(segs):
                if i % 2:
                    continue
                for part in s.split("](")[1:]:
                    if ")" not in part:
                        continue
                    target = part.split(")", 1)[0]
                    fpart, _, anc = target.partition("#")
                    tf = fpart or f
                    ok = tf in old_slugs and (not anc or anc in old_slugs[tf])
                    if not ok:
                        broken_before.append({"file": f, "line": ln, "target": target})
                    elif anc and (tf, anc) in anchor_map:
                        anchors_remapped += 1
            new = convert_line(line, anchor_map, f)
            out_lines.append(new)
        new_text = "\n".join(out_lines)
        (exp / f).write_text(new_text, encoding="utf-8")
        if new_text != texts[f]:
            per_file[f] = sum(1 for a, b in zip(texts[f].split("\n"), out_lines) if a != b)
    # 치환 수: 산문 조각(코드 펜스·인라인 코드·링크 대상 제외)의 용어 출현 수
    for f in files:
        in_fence = False
        for line in texts[f].split("\n"):
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for i, s in enumerate(line.split("`")):
                if i % 2:
                    continue
                parts = s.split("](")
                prose = parts[0] + "".join(p.split(")", 1)[1] if ")" in p else p for p in parts[1:])
                replacements += count_terms(prose)
    report = {
        "files_total": len(files),
        "files_changed": sorted(per_file),
        "lines_changed_by_file": per_file,
        "replacements": replacements,
        "headings_changed": sorted(headings_changed, key=lambda h: (h["file"], h["old"])),
        "anchors_remapped": anchors_remapped,
        "broken_links": sorted(broken_before, key=lambda b: (b["file"], b["line"])),
        "sha256_expected": {f: hashlib.sha256((exp / f).read_bytes()).hexdigest() for f in files},
        "sha256_source": {f: hashlib.sha256((src / f).read_bytes()).hexdigest() for f in files},
    }
    (OUT / 'oracle' / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in report.items() if not k.startswith("sha") and k != "lines_changed_by_file"}, ensure_ascii=False)[:1500])


if __name__ == '__main__':
    {"generate": generate, "oracle": oracle}[sys.argv[1]]()
