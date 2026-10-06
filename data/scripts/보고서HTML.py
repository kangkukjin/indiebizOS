#!/usr/bin/env python3
"""마크다운 보고서 → 공유창고용 자족 HTML(스타일 인라인·다크모드 대응).

/tmp 고아로 매번 다시 써지던 두 변환기(md2html_tips·render_housing_html)를 흡수한 것이다.
공유판에서 빼야 하는 줄(개인 시스템 맥락 등)은 사람 손이 아니라 이 변환기가 보장한다.

args 예:
  {"src":"outputs/x/보고서.md", "dst":"공유창고/0/폴더/이름.html",
   "subtitle":"머리 한 줄", "theme":"card", "drop_lines":["우리 시스템 함의"]}
"""
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# theme=plain: 본문형(넓은 표는 가로 스크롤) / theme=card: h2 단위 카드
_THEMES = {"plain": "#0b6b4f", "card": "#b3541e", "briefing": "#17665f"}

_CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--acc:%(acc)s;--card:#f7f8f7}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e8e8e6;--mut:#9aa0a6;--line:#2c3036;--acc:%(acc_d)s;--card:#1c1f23}}
*{box-sizing:border-box}
body{margin:0;padding:2rem 1rem 5rem;background:var(--bg);color:var(--fg);-webkit-text-size-adjust:100%%;
font:16px/1.75 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR",sans-serif}
main{max-width:760px;margin:0 auto}
.head{color:var(--mut);font-size:.9rem;margin-bottom:1.2rem}
h1{font-size:1.75rem;line-height:1.35;margin:0 0 1.5rem;letter-spacing:-.02em}
h2{font-size:1.3rem;margin:2.75rem 0 .9rem;padding-top:1.2rem;border-top:1px solid var(--line);letter-spacing:-.01em}
h3{font-size:1.08rem;margin:1.8rem 0 .6rem;color:var(--acc)}
blockquote{margin:1.2rem 0;padding:.85rem 1.1rem;background:var(--card);border-left:3px solid var(--acc);border-radius:0 6px 6px 0;color:var(--mut);font-size:.94rem}
blockquote p{margin:.3rem 0}
table{width:100%%;border-collapse:collapse;margin:1.2rem 0;font-size:.9rem;display:block;overflow-x:auto}
th,td{padding:.5rem .65rem;border-bottom:1px solid var(--line);text-align:left;white-space:normal;overflow-wrap:anywhere;vertical-align:top}
th{background:var(--card);font-weight:600}
a{color:var(--acc)}
hr{border:0;border-top:1px solid var(--line);margin:2.5rem 0}
ul,ol{padding-left:1.25rem}li{margin:.4rem 0}
code{background:var(--card);padding:.12em .4em;border-radius:4px;font-size:.88em}
pre{background:var(--card);padding:14px 16px;border-radius:10px;overflow-x:auto;font-size:.86em;line-height:1.6}
pre code{background:none;padding:0}
"""

_CSS_CARD = """
body{background:#f6f7f9}
@media(prefers-color-scheme:dark){body{background:#12151a}}
.card{background:var(--bg);border:1px solid var(--line);border-radius:14px;padding:.5rem 1.6rem 1.4rem;margin:1.1rem 0}
.card>h2:first-child,.card>h1:first-child{border-top:0;padding-top:0;margin-top:1rem}
"""

_CSS_BRIEFING = """
:root{--bg:#fbfaf6;--fg:#242d2b;--mut:#596761;--line:#dce2dc;--card:#eff3ee;--acc:#17665f}
body{padding:3rem 1.5rem 5rem;font-size:17px;line-height:1.85}
main{max-width:1120px}p,li{word-break:keep-all;overflow-wrap:anywhere}
.brief-head{border-top:5px solid var(--acc);padding:1.5rem 0 1.8rem;margin-bottom:1rem}
.brief-head h1{font-size:clamp(1.9rem,4vw,2.8rem);letter-spacing:-.045em;margin-bottom:1rem}
.brief-date{display:block;font-size:1rem;font-weight:500;letter-spacing:.03em;color:var(--mut);margin-top:.7rem;white-space:nowrap}
.brief-head>blockquote{max-width:780px;margin:0;background:none;border:0;padding:0;font-size:.94rem}
.brief-layout{display:grid;grid-template-columns:210px minmax(0,1fr);gap:3rem;align-items:start}
.brief-nav{position:sticky;top:1.5rem;font-size:.86rem;line-height:1.5;padding-top:1.5rem}
.brief-nav strong{font-size:.75rem;letter-spacing:.1em;color:var(--mut)}
.brief-nav ol{list-style:none;padding:0;margin:.8rem 0}.brief-nav li{margin:0}
.brief-nav a{display:block;padding:.65rem 0;border-bottom:1px solid var(--line);text-decoration:none;color:var(--fg)}
.brief-nav a:hover{color:var(--acc)}.brief-body{min-width:0}
.brief-section{margin:0 0 3rem;scroll-margin-top:1.5rem}
.brief-section>h2{font-size:1.5rem;color:var(--acc);margin:0 0 1.3rem;padding:1rem 0 .7rem;border-top:2px solid var(--acc)}
.brief-section:first-child{background:var(--card);border-radius:14px;padding:1.5rem 1.8rem 1rem}
.brief-section:first-child>h2{border:0;padding:0;font-size:1.1rem}
.brief-section:first-child li{margin:.8rem 0}
.brief-story{padding:0 0 1.4rem;margin-bottom:1.5rem;border-bottom:1px solid var(--line)}
.brief-story:last-child{border-bottom:0;margin-bottom:0;padding-bottom:0}
.brief-story h3{color:var(--fg);font-size:1.24rem;line-height:1.55;margin:1.1rem 0 .85rem;letter-spacing:-.02em}
.brief-story p{margin:.9rem 0}a{text-underline-offset:3px;text-decoration-thickness:1px}
strong{font-weight:700}img{max-width:100%;height:auto}
@media(prefers-color-scheme:dark){:root{--bg:#171c1b;--fg:#e5ece7;--mut:#abb9b1;--line:#35433c;--card:#222d28;--acc:#8dceba}}
@media(max-width:760px){body{padding:1.2rem 1rem 3rem;font-size:17px}.brief-layout{display:block}
.brief-head{padding:1.2rem 0}.brief-nav{position:static;padding:0;margin:0 0 1.6rem}
.brief-nav ol{display:flex;flex-wrap:wrap;gap:.4rem .8rem}.brief-nav a{padding:.4rem .1rem}
.brief-section:first-child{padding:1.1rem 1.2rem .6rem}.brief-section>h2{font-size:1.35rem}
.brief-story h3{font-size:1.17rem}.brief-section{margin-bottom:2.3rem}}
@media print{body{background:white;color:black;font-size:11pt;padding:0}.brief-nav{display:none}
.brief-layout{display:block}.brief-head{border-color:black}.brief-story{break-inside:auto}h2,h3{break-after:avoid}}
"""


def _wrap_briefing(body):
    """본문·링크를 다시 요약하지 않고 제목 계층만 읽기 구조로 배치한다."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, "html.parser")
    head = soup.new_tag("header", attrs={"class": "brief-head"})
    layout = soup.new_tag("div", attrs={"class": "brief-layout"})
    nav = soup.new_tag("nav", attrs={"class": "brief-nav", "aria-label": "보고서 목차"})
    label = soup.new_tag("strong")
    label.string = "바로 읽기"
    nav.append(label)
    toc = soup.new_tag("ol")
    nav.append(toc)
    content = soup.new_tag("div", attrs={"class": "brief-body"})
    section = story = None
    count = 0
    for node in list(soup.contents):
        node.extract()
        if getattr(node, "name", None) == "h1":
            dated = re.fullmatch(r"(.+?)\s*[—–]\s*(\d{4}-\d{2}-\d{2})", node.get_text())
            if dated:
                node.clear()
                node.append(dated[1])
                date = soup.new_tag("span", attrs={"class": "brief-date"})
                date.string = dated[2]
                node.append(date)
        if getattr(node, "name", None) == "h2":
            count += 1
            section = soup.new_tag("section", attrs={"class": "brief-section", "id": f"section-{count}"})
            section.append(node)
            content.append(section)
            item, link = soup.new_tag("li"), soup.new_tag("a", href=f"#section-{count}")
            link.string = node.get_text(" ", strip=True)
            item.append(link)
            toc.append(item)
            story = None
        elif section is None:
            head.append(node)
        elif getattr(node, "name", None) == "h3":
            story = soup.new_tag("div", attrs={"class": "brief-story"})
            section.append(story)
            story.append(node)
        else:
            (story if story is not None else section).append(node)
    layout.append(nav)
    layout.append(content)
    return str(head) + str(layout)


def _repo_path(raw, kind):
    if not raw:
        raise ValueError(f"{kind} 는 필수입니다.")
    raw = str(raw)
    if raw.startswith("~workspace/"):
        # IBL 의 저장소 상대 접두(self:read·self:ledger 와 같은 규약). 4083 후속 실측: 관용구가 ~workspace/ 경로를
        # 그대로 넘기자 "src 파일이 없습니다: …/indiebizOS/~workspace/…" 로 실패했다.
        raw = raw[len("~workspace/"):]
    path = Path(raw)
    if not path.is_absolute():
        path = _ROOT / path
    path = path.resolve()
    try:
        path.relative_to(_ROOT)
    except ValueError as exc:
        raise ValueError(f"{kind} 경로는 indiebizOS 저장소 안이어야 합니다: {path}") from exc
    return path


def _wrap_cards(body):
    """h2 를 경계로 카드로 나눈다. 첫 h2 앞(머리말)도 한 장."""
    parts = re.split(r'(?=<h2[ >])', body)
    return "\n".join(f'<div class="card">\n{p.strip()}\n</div>'
                     for p in parts if p.strip())


def render(args):
    """동일 변환기를 등록 스크립트와 보고서 관용구에서 재사용한다."""
    import markdown
    src = _repo_path(args.get("src"), "src")
    dst = _repo_path(args.get("dst"), "dst")
    if not src.exists():
        raise ValueError(f"src 파일이 없습니다: {src}")

    theme = str(args.get("theme") or "plain").lower()
    if theme not in _THEMES:
        raise ValueError(f"theme 은 {'|'.join(_THEMES)} 중 하나여야 합니다.")
    accent = str(args.get("accent") or _THEMES[theme])

    _drop_arg = args.get("drop_lines") or []
    # 문자열 하나를 주면 그대로 순회해 *글자* 하나하나가 토큰이 된다 —
    # '건'·':' 같은 흔한 글자가 문서 절반을 조용히 지운다(2026-09-01 실측: 225줄 중 71줄).
    if isinstance(_drop_arg, str):
        _drop_arg = [_drop_arg]
    drop = [str(x) for x in _drop_arg if str(x).strip()]
    lines, dropped = [], 0
    for line in io.open(src, encoding="utf-8").read().split("\n"):
        if drop and any(token in line for token in drop):
            dropped += 1
            continue
        lines.append(line)
    text = "\n".join(lines)

    title = args.get("title")
    if not title:
        head = re.search(r'^#\s+(.+)$', text, re.M)
        title = head.group(1).strip() if head else src.stem
    title = re.sub(r'[*`]', '', str(title))

    body = markdown.markdown(text, extensions=["tables", "sane_lists", "nl2br"])
    if theme == "card":
        body = _wrap_cards(body)
    elif theme == "briefing":
        body = _wrap_briefing(body)

    css = _CSS % {"acc": accent, "acc_d": accent}
    if theme == "card":
        css += _CSS_CARD
    elif theme == "briefing":
        css += _CSS_BRIEFING
    esc = lambda s: (str(s).replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace('"', "&quot;"))
    subtitle = args.get("subtitle")
    head_html = f'<div class="head">{esc(subtitle)}</div>\n' if subtitle else ""

    html = ('<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{esc(title)}</title>\n<style>{css}</style>\n</head>\n'
            f'<body>\n<main>\n{head_html}{body}\n</main>\n</body>\n</html>\n')

    # 감독 턴에서는 비공개 초안을 만든다. 하네스가 검수한 바이트를 승인 뒤 공개한다.
    sys.path.insert(0, str(_ROOT / "backend"))
    import boot_paths  # noqa: F401
    from supervision_delivery import stage_artifact
    publication = stage_artifact(dst, html.encode("utf-8"), _ROOT / "공유창고")
    if publication:
        output_path = Path(publication["staged"])
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        # 기존 공유판은 새 바이트가 완성될 때까지 보존한다.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=dst.parent, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(html.encode("utf-8"))
            os.replace(temporary, dst)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        output_path = dst

    return {"success": True,
                     **({"publication_pending": True, "publication": publication,
                         "message": "검수 대기 초안입니다. 승인 후 하네스가 공개하며 재생성할 필요 없습니다."}
                        if publication else {}), "items": [{
        "path": str(output_path), "title": title, "theme": theme,
        **({"public_target": str(dst)} if publication else {}),
        "bytes": len(html.encode("utf-8")),
        "headings": len(re.findall(r'<h[123][ >]', body)),
        "links": len(re.findall(r'<a href=', body)),
        "tables": len(re.findall(r'<table>', body)),
        "dropped_lines": dropped,
    }]}


def main():
    try:
        print(json.dumps(render(json.loads(sys.stdin.read() or "{}")), ensure_ascii=False))
    except (OSError, ValueError, TypeError, ImportError) as exc:
        # 사유는 stderr 로도 낸다 — 러너가 실패 봉투에 싣는 것은 stderr_tail 이라,
        # stdout 에만 두면 호출부가 로그 파일을 열어야 이유를 안다.
        print(str(exc), file=sys.stderr)
        print(json.dumps({"success": False, "items": [], "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
