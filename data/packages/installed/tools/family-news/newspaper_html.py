"""family-news/newspaper_html.py — 가족신문 정적 HTML 렌더러 (단일 디자인 소스).

handler(판 생성 시 index.html)와 backend/api_family_news.py(아카이브 홈 동적 렌더)가
같은 함수를 쓴다. 외부 리소스 0 (폰트·CDN 없음) — 공개 페이지가 어디서든 뜬다.

경로 규약 (상대 URL — 정적 HTML 이 slug 를 몰라도 되게):
  판 페이지  /n/<slug>/e/<eid>/          → 사진 src="media/<파일명>"
  아카이브 홈 /n/<slug>/                  → 표지 src="e/<eid>/media/<파일명>"
  방명록·업로드 JS 는 location 에서 /n/<slug> 베이스를 파싱 (미리보기에선 비활성 안내).
"""

import re as _re
import html as _html


def _esc(s) -> str:
    return _html.escape(str(s or ""), quote=True)


def _ver(ed: dict) -> str:
    """캐시 버전키 — 판 생성 시각 숫자. 같은 eid 가 재탄생해도 공개 캐시가 안 섞이게."""
    return _re.sub(r"\D", "", str(ed.get("created_at", ""))) or "0"


# ── 공통 껍데기 ──────────────────────────────────────────────────────────

_CSS = """
:root { --paper:#faf7f0; --ink:#2b2620; --dim:#8a8073; --line:#d9d2c4; --accent:#a84e38; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--paper); color:var(--ink); -webkit-text-size-adjust:100%;
  font-family:'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif; line-height:1.65; }
.sheet { max-width:860px; margin:0 auto; padding:20px 16px 60px; }
.masthead { text-align:center; border-bottom:4px double var(--ink); padding:26px 0 18px; margin-bottom:8px; }
.masthead .title { font-family:Georgia,'Times New Roman','Apple SD Gothic Neo',serif;
  font-size:clamp(2rem,7vw,3.2rem); letter-spacing:.12em; font-weight:700; }
.masthead .sub { margin-top:10px; color:var(--dim); font-size:.9rem; display:flex; gap:14px; justify-content:center; flex-wrap:wrap; }
.masthead .sub b { color:var(--accent); font-weight:700; }
.topnav { text-align:center; font-size:.85rem; color:var(--dim); padding:10px 0; border-bottom:1px solid var(--line); margin-bottom:26px; }
.topnav a { color:var(--accent); text-decoration:none; }
.day { margin:34px 0; }
.day-head { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap;
  border-left:5px solid var(--ink); padding:2px 0 2px 12px; margin-bottom:14px; }
.day-head h2 { font-size:1.15rem; font-weight:800; }
.pill { background:#efe9dc; color:#6b6152; border-radius:99px; padding:2px 10px; font-size:.78rem; white-space:nowrap; }
.grid { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }
@media(min-width:640px){ .grid { grid-template-columns:repeat(3,1fr); } }
.ph { position:relative; overflow:hidden; border-radius:6px; background:#e8e2d5; cursor:pointer;
  border:1px solid var(--line); }
.ph.lead { grid-column:1/-1; }
.ph img { width:100%; height:100%; object-fit:cover; display:block; aspect-ratio:4/3; }
.ph.lead img { aspect-ratio:16/10; }
.cap { position:absolute; left:0; right:0; bottom:0; padding:14px 10px 6px; font-size:.72rem; color:#fff;
  background:linear-gradient(transparent,rgba(0,0,0,.55)); opacity:0; transition:opacity .15s; }
.ph:hover .cap, .ph:active .cap { opacity:1; }
.section-head { border-left:5px solid var(--accent); padding-left:12px; margin:44px 0 14px;
  font-size:1.15rem; font-weight:800; }
.fam-note { color:var(--dim); font-size:.85rem; margin:-8px 0 14px 17px; }
.gb-list { display:flex; flex-direction:column; gap:10px; margin-bottom:16px; }
.gb-item { background:#fff; border:1px solid var(--line); border-radius:8px; padding:10px 14px; }
.gb-item .who { font-weight:700; font-size:.9rem; }
.gb-item .who span { color:var(--dim); font-weight:400; font-size:.78rem; margin-left:8px; }
.gb-item .msg { font-size:.95rem; margin-top:2px; white-space:pre-wrap; word-break:break-word; }
.panel { background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px; }
.panel .row { display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap; }
.panel input[type=text], .panel textarea { border:1px solid var(--line); border-radius:6px; padding:8px 10px;
  font:inherit; background:var(--paper); flex:1; min-width:120px; }
.panel textarea { width:100%; min-height:64px; resize:vertical; }
.btn { background:var(--ink); color:#faf7f0; border:0; border-radius:6px; padding:9px 18px;
  font:inherit; font-weight:700; cursor:pointer; }
.btn.acc { background:var(--accent); }
.btn:disabled { opacity:.5; cursor:default; }
.hint { color:var(--dim); font-size:.8rem; margin-top:6px; }
.arch-list { display:flex; flex-direction:column; gap:14px; }
.arch { display:flex; gap:14px; background:#fff; border:1px solid var(--line); border-radius:10px;
  overflow:hidden; text-decoration:none; color:inherit; }
.arch img { width:132px; height:100px; object-fit:cover; background:#e8e2d5; flex:none; }
.arch .bd { padding:12px 14px 12px 2px; }
.arch .no { font-weight:800; font-size:1.05rem; }
.arch .mt { color:var(--dim); font-size:.83rem; margin-top:3px; }
footer { text-align:center; color:var(--dim); font-size:.78rem; border-top:1px solid var(--line);
  margin-top:56px; padding-top:18px; }
#lb { position:fixed; inset:0; background:rgba(20,16,12,.92); display:none;
  align-items:center; justify-content:center; z-index:50; flex-direction:column; }
#lb.on { display:flex; }
#lb img { max-width:96vw; max-height:86vh; object-fit:contain; border-radius:4px; }
#lb .lb-cap { color:#cfc7b8; font-size:.85rem; margin-top:10px; }
"""

_JS = """
(function(){
  // /n/<slug>/... 에서만 방명록·업로드 활성. 그 외(로컬 미리보기)는 안내만.
  var m = location.pathname.match(/^\\/n\\/[A-Za-z0-9]+/);
  var base = m ? m[0] : null;
  var edition = document.body.getAttribute('data-edition') || '';

  // 라이트박스
  var lb = document.getElementById('lb');
  if (lb) {
    document.querySelectorAll('.ph').forEach(function(p){
      p.addEventListener('click', function(){
        var img = p.querySelector('img');
        lb.querySelector('img').src = img.getAttribute('data-full') || img.src;
        lb.querySelector('.lb-cap').textContent = p.getAttribute('data-cap') || '';
        lb.classList.add('on');
      });
    });
    lb.addEventListener('click', function(){ lb.classList.remove('on'); });
  }

  var gbList = document.getElementById('gb-list');
  var gbForm = document.getElementById('gb-form');
  var upForm = document.getElementById('up-form');
  if (!base) {
    if (gbForm) gbForm.innerHTML = '<div class="hint">미리보기에서는 방명록·사진 보내기가 비활성화됩니다. 발행 후 공개 주소에서 열립니다.</div>';
    if (upForm) upForm.innerHTML = '';
    return;
  }

  function esc(s){ var d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
  function loadGb(){
    if (!gbList) return;
    fetch(base + '/gb' + (edition ? ('?edition=' + encodeURIComponent(edition)) : ''))
      .then(function(r){ return r.json(); })
      .then(function(d){
        var es = (d && d.entries) || [];
        if (!es.length) { gbList.innerHTML = '<div class="hint">아직 글이 없습니다. 첫 글을 남겨 주세요!</div>'; return; }
        gbList.innerHTML = es.map(function(e){
          return '<div class="gb-item"><div class="who">' + esc(e.name) +
                 '<span>' + esc(e.at || '') + (e.edition && !edition ? (' · ' + esc(e.edition) + '호') : '') + '</span></div>' +
                 '<div class="msg">' + esc(e.msg) + '</div></div>';
        }).join('');
      }).catch(function(){ gbList.innerHTML = '<div class="hint">방명록을 불러오지 못했습니다.</div>'; });
  }
  loadGb();

  if (gbForm) gbForm.addEventListener('submit', function(ev){
    ev.preventDefault();
    var name = document.getElementById('gb-name').value.trim();
    var msg = document.getElementById('gb-msg').value.trim();
    if (!name || !msg) return;
    var btn = gbForm.querySelector('button'); btn.disabled = true;
    fetch(base + '/gb', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ name:name, msg:msg, edition:edition }) })
      .then(function(r){ if(!r.ok) throw 0; document.getElementById('gb-msg').value=''; loadGb(); })
      .catch(function(){ alert('등록에 실패했습니다. 잠시 후 다시 시도해 주세요.'); })
      .then(function(){ btn.disabled = false; });
  });

  if (upForm) upForm.addEventListener('submit', function(ev){
    ev.preventDefault();
    var name = document.getElementById('up-name').value.trim();
    var files = document.getElementById('up-file').files;
    var st = document.getElementById('up-status');
    if (!name || !files.length) { st.textContent = '이름과 사진을 선택해 주세요.'; return; }
    var btn = upForm.querySelector('button'); btn.disabled = true;
    var i = 0, ok = 0;
    function next(){
      if (i >= files.length) {
        st.textContent = ok + '장을 보냈습니다. 다음 신문에 실릴 수 있어요. 고맙습니다!';
        btn.disabled = false; document.getElementById('up-file').value = '';
        return;
      }
      var f = files[i++];
      st.textContent = '보내는 중… (' + i + '/' + files.length + ')';
      fetch(base + '/upload?name=' + encodeURIComponent(name) +
            '&filename=' + encodeURIComponent(f.name) + '&edition=' + encodeURIComponent(edition),
            { method:'POST', headers:{'Content-Type': f.type || 'application/octet-stream'}, body: f })
        .then(function(r){ if (r.ok) ok++; next(); })
        .catch(function(){ next(); });
    }
    next();
  });
})();
"""


def _shell(title: str, body: str, edition_id: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>{_esc(title)}</title>
<style>{_CSS}</style>
</head>
<body data-edition="{_esc(edition_id)}">
<div class="sheet">
{body}
<footer>가족만 보는 신문입니다 · 주소를 아는 사람만 볼 수 있어요<br>IndieBiz OS 가족신문</footer>
</div>
<div id="lb"><img alt=""><div class="lb-cap"></div></div>
<script>{_JS}</script>
</body>
</html>"""


def _guestbook_html() -> str:
    return """
<div class="section-head">방명록</div>
<div id="gb-list" class="gb-list"><div class="hint">불러오는 중…</div></div>
<form id="gb-form" class="panel">
  <div class="row"><input type="text" id="gb-name" placeholder="이름" maxlength="24" required></div>
  <textarea id="gb-msg" placeholder="한마디 남겨 주세요" maxlength="500" required></textarea>
  <div class="row" style="margin-top:8px"><button class="btn" type="submit">글 남기기</button></div>
</form>
"""


def _upload_html() -> str:
    return """
<div class="section-head">사진 보내기</div>
<form id="up-form" class="panel">
  <div class="row">
    <input type="text" id="up-name" placeholder="보내는 사람" maxlength="24" required>
    <input type="file" id="up-file" accept="image/*" multiple>
  </div>
  <div class="row"><button class="btn acc" type="submit">사진 보내기</button></div>
  <div class="hint" id="up-status">보낸 사진은 다음 신문에 실릴 수 있습니다.</div>
</form>
"""


def render_edition(edition: dict, paper_title: str) -> str:
    """판(edition.json dict) → 정적 신문 HTML."""
    no = edition.get("no", "?")
    rng = f"{edition.get('range_from','')} ~ {edition.get('range_to','')}"
    parts = [f"""
<div class="masthead">
  <div class="title">{_esc(paper_title)}</div>
  <div class="sub"><span>제 <b>{_esc(no)}</b> 호</span><span>{_esc(rng)}</span><span>발행 {_esc(edition.get('created_at',''))}</span></div>
</div>
<div class="topnav"><a href="../../">지난 신문 보기 ↗</a></div>
"""]

    for day in edition.get("days", []):
        places = day.get("places") or []
        pills = "".join(f'<span class="pill">📍 {_esc(p)}</span>' for p in places[:3])
        parts.append(f'<div class="day"><div class="day-head"><h2>{_esc(day.get("label",""))}</h2>{pills}</div><div class="grid">')
        for i, ph in enumerate(day.get("photos", [])):
            cap_bits = [b for b in (ph.get("time"), ph.get("place")) if b]
            cap = " · ".join(cap_bits)
            lead = " lead" if (i == 0 and len(day.get("photos", [])) >= 3) else ""
            src = f"media/{_esc(ph.get('file',''))}?v={_ver(edition)}"
            parts.append(
                f'<figure class="ph{lead}" data-cap="{_esc(cap)}">'
                f'<img src="{src}" loading="lazy" alt="{_esc(cap)}">'
                f'<figcaption class="cap">{_esc(cap)}</figcaption></figure>'
            )
        parts.append("</div></div>")

    fam = edition.get("family") or []
    if fam:
        parts.append('<div class="section-head">가족이 보내온 사진</div>'
                     '<div class="fam-note">지난 신문을 보고 가족들이 보내 준 사진입니다.</div><div class="grid">')
        for ph in fam:
            cap = " · ".join(b for b in (ph.get("name"), ph.get("at")) if b)
            parts.append(
                f'<figure class="ph" data-cap="{_esc(cap)}">'
                f'<img src="media/{_esc(ph.get("file",""))}?v={_ver(edition)}" loading="lazy" alt="{_esc(cap)}">'
                f'<figcaption class="cap">{_esc(cap)}</figcaption></figure>'
            )
        parts.append("</div>")

    parts.append(_guestbook_html())
    parts.append(_upload_html())
    title = f"{paper_title} 제{no}호"
    return _shell(title, "\n".join(parts), edition_id=str(edition.get("id", "")))


def render_home(paper_title: str, editions: list) -> str:
    """아카이브 홈 — 발행된 판 목록(최신 먼저). editions: state.json 의 발행판 dict 목록."""
    parts = [f"""
<div class="masthead">
  <div class="title">{_esc(paper_title)}</div>
  <div class="sub"><span>지금까지 <b>{len(editions)}</b>개 판이 발행되었습니다</span></div>
</div>
"""]
    if editions:
        parts.append('<div class="section-head">신문 보기</div><div class="arch-list">')
        for ed in editions:
            cover = ed.get("cover") or ""
            img = (f'<img src="e/{_esc(ed["id"])}/media/{_esc(cover)}?v={_ver(ed)}" loading="lazy" alt="">'
                   if cover else '<img alt="">')
            rng = f"{ed.get('range_from','')} ~ {ed.get('range_to','')}"
            parts.append(
                f'<a class="arch" href="e/{_esc(ed["id"])}/">{img}<div class="bd">'
                f'<div class="no">제 {_esc(ed.get("no","?"))} 호</div>'
                f'<div class="mt">{_esc(rng)}</div>'
                f'<div class="mt">사진 {_esc(ed.get("photo_count", 0))}장 · 발행 {_esc(ed.get("published_at",""))}</div>'
                f"</div></a>"
            )
        parts.append("</div>")
    else:
        parts.append('<div class="hint" style="text-align:center;margin:40px 0">아직 발행된 신문이 없습니다.</div>')

    parts.append(_guestbook_html())
    parts.append(_upload_html())
    return _shell(paper_title, "\n".join(parts))
