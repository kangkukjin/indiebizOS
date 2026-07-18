#!/usr/bin/env python3
"""블로그 본문을 평문 → 마크다운으로 되살린다 (RSS 창 = 최근 50편).

## 왜
RSS 는 문단(`<p>`)과 이미지를 **이미 다 준다.** 그런데 수집기가 `clean_html` 로 평문화해
3,990자가 한 덩어리가 되어 있었다(2026-07-18 공유창고 발행에서 드러남). 수집기는 고쳤으므로
*앞으로 올라오는 글*은 정상이고, 이 스크립트는 **이미 받아둔 글**만 되살린다.

## 안전장치 (vault = 사용자의 Obsidian 저장소)
- `관련 글`(`<!-- related-links -->`) 블록은 떼어뒀다가 **다시 붙인다**. 기계가 만든
  시맨틱 연결이라 덮어쓰면 24편에서 사라진다.
- frontmatter 의 summary·keywords 도 보존한다.
- 본문이 이미 마크다운이면(문단 2개 이상) **건너뛴다** — 두 번 돌려도 안전(멱등).
- `--dry-run` 이 기본. 실제 쓰기는 `--apply` 를 줘야 한다.
- RSS 창 밖(50편보다 오래된 글)은 원본이 없으므로 손대지 않는다.

사용:
    python3 scripts/migrate_blog_markdown.py             # 미리보기
    python3 scripts/migrate_blog_markdown.py --apply     # 실제 적용
"""
import os
import sys
import argparse

_BLOG = os.path.join(os.path.dirname(__file__), "..", "data", "packages",
                     "installed", "tools", "blog")
sys.path.insert(0, os.path.abspath(_BLOG))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 미리보기)")
    args = ap.parse_args()

    import requests
    from bs4 import BeautifulSoup
    import tool_blog_insight as T
    from tool_blog_vault import find_post_md, parse_post_md, render_post_md

    r = requests.get(f"{T.RSS_URL}?size={T.RSS_SIZE}", timeout=30)
    r.raise_for_status()
    items = BeautifulSoup(r.content, "xml").find_all("item")
    print(f"RSS 창: {len(items)}편")

    conn = T.get_db()
    changed = skipped = missing = 0
    for it in items:
        link = it.find("link").text if it.find("link") else ""
        import re as _re
        m = _re.search(r"/(\d+)$", link)
        post_id = m.group(1) if m else link
        title = it.find("title").text if it.find("title") else ""
        new_md = T.html_to_markdown(it.find("description").text)

        row = conn.execute("SELECT content FROM posts WHERE post_id = ?", (post_id,)).fetchone()
        if not row:
            missing += 1
            continue
        cur = row["content"] or ""
        # 이미 마크다운이면 건너뛴다(멱등) — 문단 경계가 있으면 되살릴 게 없다.
        if cur.count("\n\n") >= 1:
            skipped += 1
            continue

        paras = new_md.count("\n\n") + 1
        print(f"  [{post_id}] {title[:34]:36} {len(cur):5}자 → {len(new_md):5}자 (문단 {paras})")
        if not args.apply:
            changed += 1
            continue

        conn.execute("UPDATE posts SET content = ?, char_count = ? WHERE post_id = ?",
                     (new_md, len(new_md), post_id))

        # vault .md — 관련 글·요약을 보존한 채 본문만 교체
        path = find_post_md(post_id)
        if path and os.path.exists(path):
            parsed = parse_post_md(open(path, encoding="utf-8").read()) or {}
            parsed.update({"post_id": post_id, "content": new_md})
            with open(path, "w", encoding="utf-8") as f:
                f.write(render_post_md(parsed))
        changed += 1

    if args.apply:
        conn.commit()
    conn.close()

    print(f"\n{'적용' if args.apply else '미리보기'}: 되살림 {changed} / 이미 마크다운 {skipped} / DB에 없음 {missing}")
    if args.apply and changed:
        print("→ RAG 재인덱싱 권장: [self:blog]{op: \"rebuild_index\"}")
    elif changed:
        print("→ 실제 적용하려면 --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
