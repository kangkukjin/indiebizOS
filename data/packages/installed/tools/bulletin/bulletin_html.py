"""bulletin_html.py — 자유게시판 공개 페이지 렌더러 (단일 디자인 소스).

backend/api_bulletin.py 가 /b/<slug>/ 요청에 이 함수로 HTML 을 만든다. 외부 리소스 0
(폰트·CDN 없음) — 어디서든 뜬다. 글쓰기·이미지는 location 에서 /b/<slug> 베이스를 파싱해
FormData 로 POST 하고 성공 시 새로고침(동적 페이지, Worker no-cache).
"""

import html as _html


def _esc(s) -> str:
    return _html.escape(str(s or ""), quote=True)


_CSS = """
:root { --bg:#f4f6f8; --card:#fff; --ink:#1c2530; --dim:#71808f; --line:#dde3ea; --accent:#2f6df6; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--ink); -webkit-text-size-adjust:100%;
  font-family:'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif; line-height:1.6; }
.wrap { max-width:720px; margin:0 auto; padding:20px 14px 72px; }
.head { padding:18px 0 14px; border-bottom:2px solid var(--ink); margin-bottom:18px; }
.head h1 { font-size:clamp(1.4rem,5vw,2rem); font-weight:800; letter-spacing:-.01em; }
.head .sub { color:var(--dim); font-size:.85rem; margin-top:6px; }
.panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; margin-bottom:22px; }
.panel .row { display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap; }
.panel input[type=text], .panel textarea { border:1px solid var(--line); border-radius:8px; padding:9px 11px;
  font:inherit; background:var(--bg); flex:1; min-width:120px; color:var(--ink); }
.panel textarea { width:100%; min-height:88px; resize:vertical; }
.panel .file { font-size:.85rem; color:var(--dim); }
.hp { position:absolute; left:-9999px; width:1px; height:1px; opacity:0; }
.btn { background:var(--accent); color:#fff; border:0; border-radius:8px; padding:10px 20px;
  font:inherit; font-weight:700; cursor:pointer; }
.btn:disabled { opacity:.5; cursor:default; }
.hint { color:var(--dim); font-size:.8rem; margin-top:6px; }
.posts { display:flex; flex-direction:column; gap:12px; }
.post { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:13px 15px; }
.post .who { font-weight:700; font-size:.92rem; }
.post .who span { color:var(--dim); font-weight:400; font-size:.78rem; margin-left:8px; }
.post .body { font-size:.98rem; margin-top:4px; white-space:pre-wrap; word-break:break-word; }
.post img { margin-top:10px; max-width:100%; border-radius:8px; display:block; border:1px solid var(--line); }
.empty { color:var(--dim); text-align:center; padding:32px 0; }
footer { text-align:center; color:var(--dim); font-size:.76rem; border-top:1px solid var(--line);
  margin-top:40px; padding-top:16px; }
"""

_JS = """
(function(){
  var m = location.pathname.match(/^\\/b\\/[A-Za-z0-9]+/);
  var base = m ? m[0] : null;
  var form = document.getElementById('pf');
  if (!base || !form) return;
  form.addEventListener('submit', function(ev){
    ev.preventDefault();
    var name = document.getElementById('pf-name').value.trim();
    var body = document.getElementById('pf-body').value.trim();
    if (!name || !body) { return; }
    var btn = form.querySelector('button'); btn.disabled = true;
    var fd = new FormData(form);
    fetch(base + '/post', { method:'POST', body: fd })
      .then(function(r){
        if (r.status === 429) { throw '너무 빠릅니다. 잠시 후 다시 시도해 주세요.'; }
        if (!r.ok) { throw '등록에 실패했습니다.'; }
        location.reload();
      })
      .catch(function(e){ alert(typeof e === 'string' ? e : '등록에 실패했습니다.'); btn.disabled = false; });
  });
})();
"""


def _post_html(base_rel_ok: bool, p: dict) -> str:
    img = ""
    if p.get("image"):
        img = f'<img src="media/{_esc(p.get("id"))}" loading="lazy" alt="첨부 이미지">'
    return (
        f'<div class="post"><div class="who">{_esc(p.get("name"))}'
        f'<span>{_esc(p.get("at", ""))}</span></div>'
        f'<div class="body">{_esc(p.get("body"))}</div>{img}</div>'
    )


def render_board(board: dict, posts: list) -> str:
    """게시판 dict + 글 목록(최신 먼저) → 공개 HTML."""
    title = board.get("title") or "자유게시판"
    allow_images = bool(board.get("allow_images", True))
    n = len(posts)

    file_field = (
        '<div class="row"><input class="file" type="file" name="image" accept="image/*"></div>'
        if allow_images else ""
    )
    write = f"""
<form id="pf" class="panel" enctype="multipart/form-data">
  <div class="row"><input type="text" id="pf-name" name="name" placeholder="이름" maxlength="24" required></div>
  <textarea id="pf-body" name="body" placeholder="자유롭게 글을 남겨 주세요" maxlength="4000" required></textarea>
  {file_field}
  <input class="hp" type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
  <div class="row" style="margin-top:8px"><button class="btn" type="submit">글쓰기</button></div>
  <div class="hint">로그인 없이 누구나 글을 쓸 수 있는 게시판입니다.{" 사진 1장을 함께 올릴 수 있어요." if allow_images else ""}</div>
</form>
"""

    if posts:
        body_posts = '<div class="posts">' + "\n".join(_post_html(allow_images, p) for p in posts) + "</div>"
    else:
        body_posts = '<div class="empty">아직 글이 없습니다. 첫 글을 남겨 주세요!</div>'

    body = f"""
<div class="head"><h1>{_esc(title)}</h1><div class="sub">글 {n}개 · 주소를 아는 사람은 누구나 글을 남길 수 있어요</div></div>
{write}
{body_posts}
<footer>IndieBiz OS 게시판 · 주소를 아는 사람만 볼 수 있어요</footer>
"""
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
{body}
</div>
<script>{_JS}</script>
</body>
</html>"""
