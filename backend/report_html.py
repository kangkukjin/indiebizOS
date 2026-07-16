"""report_html.py — 정기보고(AI 동향 보고서 등) 공개 페이지 렌더러 (단일 디자인 소스).

backend/api_report.py 가 /r/<slug>/ 요청에 이 함수로 최신 보고서(마크다운)를 HTML 로 렌더한다.
외부 리소스 0(폰트·CDN 없음) — 어디서든 뜬다. 정기보고 앱의 산출물을 내주는 '발행 면'.

보고서는 순수 마크다운(outputs/ai_trend_reports/*.md). python-markdown 으로 본문을 변환하고
읽기 좋은 문서 레이아웃으로 감싼다. 콘텐츠(읽기 전용)라 쓰기·업로드·이미지 배관은 없다.
"""

import html as _html

try:
    import markdown as _md
except Exception:  # pragma: no cover
    _md = None


def _esc(s) -> str:
    return _html.escape(str(s or ""), quote=True)


def _md_to_html(text: str) -> str:
    """마크다운 → HTML. python-markdown 없으면 안전하게 <pre> 폴백."""
    if _md is None:
        return "<pre class='raw'>" + _esc(text) + "</pre>"
    return _md.markdown(
        text or "",
        extensions=["extra", "sane_lists", "nl2br", "toc"],
        output_format="html5",
    )


_CSS = """
:root { --bg:#f6f7f9; --card:#fff; --ink:#1b2330; --dim:#6b7683; --line:#e2e6ec; --accent:#2f5fd0;
  --code:#eef1f6; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); -webkit-text-size-adjust:100%;
  font-family:'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif; line-height:1.72; }
.wrap { max-width:760px; margin:0 auto; padding:22px 16px 80px; }
.masthead { border-bottom:3px double var(--ink); padding:10px 0 16px; margin-bottom:20px; }
.masthead .kicker { color:var(--accent); font-weight:800; font-size:.82rem; letter-spacing:.06em; }
.masthead h1 { font-size:clamp(1.5rem,5vw,2.1rem); font-weight:800; margin:6px 0 2px; letter-spacing:-.01em; }
.masthead .meta { color:var(--dim); font-size:.85rem; }
.doc { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:22px 22px 28px; }
.doc h1 { font-size:1.5rem; margin:.2em 0 .5em; padding-bottom:.25em; border-bottom:2px solid var(--line); }
.doc h2 { font-size:1.22rem; margin:1.5em 0 .5em; padding-left:11px; border-left:5px solid var(--accent); }
.doc h3 { font-size:1.05rem; margin:1.3em 0 .4em; color:#33404f; }
.doc p { margin:.7em 0; word-break:break-word; }
.doc ul, .doc ol { margin:.6em 0 .9em; padding-left:1.4em; }
.doc li { margin:.28em 0; }
.doc blockquote { margin:.9em 0; padding:.5em 14px; border-left:4px solid var(--line);
  background:#fafbfd; color:#4a5563; border-radius:0 8px 8px 0; }
.doc blockquote p { margin:.3em 0; }
.doc a { color:var(--accent); text-decoration:none; word-break:break-all; }
.doc a:hover { text-decoration:underline; }
.doc code { background:var(--code); border-radius:5px; padding:.1em .38em; font-size:.9em;
  font-family:'SF Mono',ui-monospace,Menlo,Consolas,monospace; }
.doc pre { background:var(--code); border-radius:10px; padding:14px; overflow-x:auto; }
.doc pre code { background:none; padding:0; }
.doc pre.raw { white-space:pre-wrap; word-break:break-word; }
.doc hr { border:0; border-top:1px solid var(--line); margin:1.6em 0; }
.doc table { border-collapse:collapse; width:100%; margin:1em 0; font-size:.92rem; display:block; overflow-x:auto; }
.doc th, .doc td { border:1px solid var(--line); padding:7px 10px; text-align:left; }
.doc th { background:#f2f5f9; }
.doc img { max-width:100%; border-radius:8px; }
footer { text-align:center; color:var(--dim); font-size:.78rem; border-top:1px solid var(--line);
  margin-top:40px; padding-top:16px; }
"""


def render_report(title: str, md_text: str, date_label: str = "", total: int = 0) -> str:
    """제목 + 최신 보고서 마크다운 → 공개 HTML 한 장."""
    body = _md_to_html(md_text)
    sub_bits = []
    if date_label:
        sub_bits.append(_esc(date_label))
    if total:
        sub_bits.append(f"누적 {total}호")
    sub = " · ".join(sub_bits)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>{_esc(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
<div class="masthead">
  <div class="kicker">정기보고</div>
  <h1>{_esc(title)}</h1>
  <div class="meta">{sub}</div>
</div>
<article class="doc">
{body}
</article>
<footer>IndieBiz OS 정기보고 · 주소를 아는 사람만 볼 수 있어요</footer>
</div>
</body>
</html>"""
