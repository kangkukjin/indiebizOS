"""비즈니스 카탈로그 HTML — 공유창고에 진열되는 '한 장짜리 카탈로그'의 디자인 단일 소스.

왜 파일 하나인가: 창고의 불변식은 '색인 없음 · 파일시스템이 진실'이다. 카탈로그도 특권
페이지가 아니라 **그냥 파일 하나**여야 이웃 폴러가 집어가고, 리트윗되고, 내려받아 열어도
그대로 산다. 그래서 사진을 data URI 로 심어 자족(self-contained)으로 만든다 — 받아간 쪽이
우리 서버에 다시 물을 필요가 없다(asker-pays 의 반대편: 주는 쪽이 완결해서 준다).

원본 사진은 여전히 `<비즈니스 이름>/` 폴더에 개별 파일로 있고(내려받기·EXIF 제거 서빙),
카탈로그 안의 사진은 그 원본으로 가는 링크를 걸친 축소판이다.

warehouse_items.sync() 가 부른다. 여기는 렌더만 — 파일 배치·청소는 그쪽 책임.
"""
import base64
import html as _h
from datetime import datetime

# 임베드 축소판 한 변(px)과 JPEG 품질 — 문서 크기와 눈맛의 절충(720/78 ≈ 장당 60~90KB).
_EMBED_PX = 720
_EMBED_Q = 78
# 한 카탈로그가 심을 수 있는 사진 바이트 총량. 넘으면 그 뒤 사진은 링크만 남긴다
# (조용히 자르지 않고 "사진 N장은 원본 링크로" 라고 문서에 적는다).
_EMBED_BUDGET = 12 * 1024 * 1024

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin:0; padding:0 20px 64px;
  font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",
    "Noto Sans KR",system-ui,sans-serif;
  line-height:1.65; color:#1c1917; background:#fafaf9; }
.wrap { max-width:900px; margin:0 auto; }
header { padding:40px 0 22px; border-bottom:2px solid #d6d3d1; margin-bottom:28px; }
.house { font-size:13px; letter-spacing:.02em; color:#a8a29e; margin:0 0 6px; }
h1 { font-size:30px; line-height:1.25; margin:0 0 10px; font-weight:700; letter-spacing:-.01em; }
.desc { margin:0; color:#57534e; font-size:15px; }
.meta { margin:14px 0 0; font-size:12.5px; color:#a8a29e; }
.item { padding:26px 0; border-bottom:1px solid #e7e5e4; }
.item:last-of-type { border-bottom:0; }
h2 { font-size:19px; margin:0 0 8px; font-weight:650; }
.body { margin:0; color:#44403c; font-size:14.5px; white-space:pre-wrap; word-break:break-word; }
.shots { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr));
  gap:10px; margin:14px 0 0; }
.shots a { display:block; border-radius:10px; overflow:hidden; background:#f5f5f4;
  border:1px solid #e7e5e4; }
.shots img { display:block; width:100%; height:100%; aspect-ratio:4/3; object-fit:cover; }
.links { margin:12px 0 0; font-size:13px; }
.links a { color:#b45309; }
.empty { color:#a8a29e; font-size:14px; }
footer { margin-top:34px; padding-top:20px; border-top:1px solid #e7e5e4;
  font-size:13.5px; color:#57534e; }
footer h3 { font-size:14px; margin:0 0 8px; color:#1c1917; }
footer ul { margin:0; padding-left:18px; }
footer li { margin:2px 0; word-break:break-all; }
.made { margin-top:18px; font-size:12px; color:#a8a29e; }
@media print { body { background:#fff; } .shots { grid-template-columns:repeat(3,1fr); } }
@media (prefers-color-scheme: dark) {
  body { color:#e7e5e4; background:#1c1917; }
  header { border-bottom-color:#44403c; }
  h1, footer h3 { color:#fafaf9; }
  .desc, .body, footer { color:#d6d3d1; }
  .item { border-bottom-color:#292524; }
  .shots a { background:#292524; border-color:#44403c; }
  footer { border-top-color:#292524; }
}
"""


def _embed(src, budget: list) -> str:
    """원본 사진 → data URI 축소판. 예산을 넘거나 실패하면 빈 문자열."""
    if budget[0] <= 0:
        return ""
    try:
        import thumbnails
        data = thumbnails.image_thumbnail_bytes(str(src), size=_EMBED_PX, quality=_EMBED_Q)
    except Exception:
        data = None
    if not data:
        return ""
    budget[0] -= len(data)
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _photo_url(rel: str) -> str:
    """창고 상대경로 → 공개면 서빙 주소. 사진 원본(EXIF 제거판)으로 가는 문."""
    from urllib.parse import quote
    return "/f?path=" + quote(rel)


def render(spec: dict) -> str:
    """spec → 자족 HTML 한 장.

    spec = {warehouse_title, business:{name,description}, contacts:[(라벨,값)],
            items:[{title, details, photos:[{rel, src}]}]}
    """
    biz = spec.get("business") or {}
    items = spec.get("items") or []
    budget = [_EMBED_BUDGET]
    linked_only = 0

    blocks = []
    for it in items:
        shots, links = [], []
        for ph in it.get("photos") or []:
            url = _photo_url(ph["rel"])
            uri = _embed(ph["src"], budget)
            if uri:
                shots.append(f'<a href="{_h.escape(url)}" title="원본 사진 보기">'
                             f'<img src="{uri}" alt="" loading="lazy"></a>')
            else:
                linked_only += 1
                links.append(f'<a href="{_h.escape(url)}">사진 {len(links) + 1}</a>')
        title = _h.escape((it.get("title") or "").strip() or "제목 없음")
        details = _h.escape((it.get("details") or "").strip())
        parts = [f"<h2>{title}</h2>"]
        if details:
            parts.append(f'<p class="body">{details}</p>')
        if shots:
            parts.append(f'<div class="shots">{"".join(shots)}</div>')
        if links:
            parts.append(f'<p class="links">사진: {" · ".join(links)}</p>')
        blocks.append(f'<article class="item">{"".join(parts)}</article>')

    body = "".join(blocks) or '<p class="empty">아직 올린 품목이 없습니다.</p>'

    contacts = spec.get("contacts") or []
    if contacts:
        lis = "".join(f"<li>{_h.escape(str(k))}: {_h.escape(str(v))}</li>" for k, v in contacts)
        foot = f"<h3>연락처</h3><ul>{lis}</ul>"
    else:
        foot = ""

    name = _h.escape((biz.get("name") or "카탈로그").strip())
    house = _h.escape((spec.get("warehouse_title") or "").strip())
    desc = _h.escape((biz.get("description") or "").strip())
    n = len(items)
    shot_n = sum(len(it.get("photos") or []) for it in items)
    meta = f"품목 {n}개" + (f" · 사진 {shot_n}장" if shot_n else "")
    meta += " · " + datetime.now().strftime("%Y-%m-%d") + " 기준"
    if linked_only:
        meta += f" · 사진 {linked_only}장은 원본 링크로"

    house_el = f'<p class="house">{house}</p>' if house else ""
    desc_el = f'<p class="desc">{desc}</p>' if desc else ""
    doc_title = f"{name} · {house}" if house else name

    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{doc_title}</title>"
        f"<style>{_CSS}</style></head><body><div class=\"wrap\">"
        f"<header>{house_el}<h1>{name}</h1>{desc_el}"
        f'<p class="meta">{_h.escape(meta)}</p></header>'
        f"<main>{body}</main>"
        f"<footer>{foot}"
        '<p class="made">이 카탈로그는 창고 주인의 비즈니스 목록에서 자동으로 만들어집니다. '
        "사진을 누르면 원본을 볼 수 있습니다.</p></footer>"
        "</div></body></html>"
    )
