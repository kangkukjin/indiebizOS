#!/usr/bin/env python3
"""arxiv최신피드 — arXiv 지정 카테고리의 최신 제출(신규 프리프린트)을 items 통화로.

AI 동향 보고서가 "cs.AI·cs.CL·cs.LG 최신 제출 60건"을 curl 로 직접 긁다가 PARSE FAIL 을
매일 재연하던 것을(설명형 UA·재시도 없는 단발 호출) 결정화한 등록 스크립트.
기존 [sense:paper]{source:arxiv} 는 *키워드 검색*이라 "카테고리별 최신 피드"가 없었다.

사용 ([self:script]{op:"run", id:"arxiv최신피드", args:{...}}):
  categories: ["cs.AI","cs.CL","cs.LG"] (기본) — arXiv 카테고리 코드
  limit: 60 (기본) — 반환할 최대 건수
  sort: "submitted" (기본) — submitted=최초 제출일 / updated=최종 수정일

출력: items 통화 JSON (stdout) — title·meta·summary·url + published·updated·arxiv_id·primary_category.
"""
import json
import sys
import time
import urllib.parse

import feedparser
import requests

_ARXIV_UA = "indiebizOS/1.0 (personal research agent; mailto:kangkukjin@gmail.com)"
_DEFAULT_CATS = ["cs.AI", "cs.CL", "cs.LG"]


def _fetch(query: str, sort_by: str, limit: int):
    """설명형 UA + HTTP/파싱 실패를 합쳐 총 3회만 백오프한다.

    이전 초안은 바깥 3회 × 안쪽 3회라 최악에는 같은 요청을 9번 보냈고,
    HTTP 4xx 본문도 Atom 으로 파싱했다. arXiv에 예의를 지키면서 실패 원인을 보존한다.
    """
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": query, "start": 0, "max_results": limit,
        "sortBy": sort_by, "sortOrder": "descending"})
    last_error = "빈 피드"
    for attempt in range(3):
        try:
            response = requests.get(
                url, headers={"User-Agent": _ARXIV_UA}, timeout=30)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                if feed.get("entries"):
                    return feed, None
                last_error = f"Atom 파싱 실패: {feed.get('bozo_exception') or 'entries 0건'}"
            else:
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
        except requests.RequestException as exc:
            last_error = f"요청 실패: {exc}"
        if attempt < 2:
            time.sleep(3 * (attempt + 1))
    return None, last_error


def _entry_item(e):
    aid = (e.get("id", "") or "").split("/")[-1]
    title = (e.get("title", "") or "").strip()
    authors = ", ".join(a.get("name", "") for a in e.get("authors", []) if a.get("name"))
    published = (e.get("published", "") or "")[:10]
    updated = (e.get("updated", "") or "")[:10]
    summary = (e.get("summary", "") or "").strip().replace("\n", " ")[:200]
    pc = e.get("arxiv_primary_category") or {}
    primary = pc.get("term") if isinstance(pc, dict) else None
    if not primary:
        tags = e.get("tags") or []
        if tags:
            primary = tags[0].get("term")
    return {
        "title": title,
        "meta": " · ".join(x for x in [authors, published] if x),
        "summary": summary,
        "url": f"https://arxiv.org/abs/{aid}",
        "link_label": "논문 보기",
        "arxiv_id": aid,
        "authors": authors,
        "published": published,
        "updated": updated,
        "primary_category": primary or "",
    }


def main():
    try:
        args = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        args = {}
    cats = args.get("categories") or _DEFAULT_CATS
    if isinstance(cats, str):
        cats = [c.strip() for c in cats.split(",") if c.strip()]
    limit = int(args.get("limit") or args.get("max_results") or 60)
    sort_mode = (args.get("sort") or "submitted").strip().lower()
    sort_by = "lastUpdatedDate" if sort_mode in ("updated", "revision", "lastupdateddate") else "submittedDate"

    query = " OR ".join(f"cat:{c}" for c in cats)
    feed, combined_error = _fetch(query, sort_by, limit)

    # 폴백: 결합 질의가 빈손이면 카테고리별로 나눠 잡는다(한 카테고리 장애 격리)
    if feed is None:
        items = []
        errors = [f"결합 질의: {combined_error}"]
        for c in cats:
            f, error = _fetch(f"cat:{c}", sort_by, limit)
            if f:
                items.extend(_entry_item(e) for e in f.get("entries", []))
            elif error:
                errors.append(f"{c}: {error}")
    else:
        items = [_entry_item(e) for e in feed.get("entries", [])]
        errors = []

    # 폴백 경로에서 같은 논문이 여러 카테고리에 걸려 중복될 수 있다
    seen = set()
    dedup = []
    for it in items:
        if not it["arxiv_id"] or it["arxiv_id"] in seen:
            continue
        seen.add(it["arxiv_id"])
        dedup.append(it)

    sort_field = "updated" if sort_by == "lastUpdatedDate" else "published"
    dedup.sort(key=lambda x: x.get(sort_field) or "", reverse=True)
    dedup = dedup[:limit]

    result = {
        "success": bool(dedup),
        "count": len(dedup),
        "categories": cats,
        "sort": sort_by,
        "items": dedup,
    }
    if errors:
        result["errors"] = errors
    if not dedup:
        result["error"] = "arXiv 최신 피드를 가져오지 못했습니다."
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
