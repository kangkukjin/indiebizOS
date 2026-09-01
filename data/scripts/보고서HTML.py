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
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# theme=plain: 본문형(넓은 표는 가로 스크롤) / theme=card: h2 단위 카드
_THEMES = {"plain": "#0b6b4f", "card": "#b3541e"}

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
th,td{padding:.5rem .65rem;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
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


def _repo_path(raw, kind):
    if not raw:
        raise ValueError(f"{kind} 는 필수입니다.")
    path = Path(str(raw))
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


def main():
    try:
        import markdown
    except ImportError:
        msg = "python-markdown 이 없습니다 — pip install markdown"
        print(msg, file=sys.stderr)
        print(json.dumps({"success": False, "items": [], "error": msg}, ensure_ascii=False))
        raise SystemExit(1)
    try:
        args = json.loads(sys.stdin.read() or "{}")
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

        css = _CSS % {"acc": accent, "acc_d": accent}
        if theme == "card":
            css += _CSS_CARD
        esc = lambda s: (str(s).replace("&", "&amp;").replace("<", "&lt;")
                         .replace(">", "&gt;").replace('"', "&quot;"))
        subtitle = args.get("subtitle")
        head_html = f'<div class="head">{esc(subtitle)}</div>\n' if subtitle else ""

        html = ('<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                f'<title>{esc(title)}</title>\n<style>{css}</style>\n</head>\n'
                f'<body>\n<main>\n{head_html}{body}\n</main>\n</body>\n</html>\n')

        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(html, encoding="utf-8")

        print(json.dumps({"success": True, "items": [{
            "path": str(dst), "title": title, "theme": theme,
            "bytes": len(html.encode("utf-8")),
            "headings": len(re.findall(r'<h[123][ >]', body)),
            "links": len(re.findall(r'<a href=', body)),
            "tables": len(re.findall(r'<table>', body)),
            "dropped_lines": dropped,
        }]}, ensure_ascii=False))
    except (OSError, ValueError, TypeError) as exc:
        # 사유는 stderr 로도 낸다 — 러너가 실패 봉투에 싣는 것은 stderr_tail 이라,
        # stdout 에만 두면 호출부가 로그 파일을 열어야 이유를 안다.
        print(str(exc), file=sys.stderr)
        print(json.dumps({"success": False, "items": [], "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
