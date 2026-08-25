#!/usr/bin/env python3
"""GitHub 저장소 탐색·메타 다건 조회를 items 통화로 반환한다.

args 예:
  {"repos": ["owner/repo", "https://github.com/owner/repo"]}
  {"query": "topic:ai created:>2026-08-01", "limit": 15, "sort": "stars"}
"""
import concurrent.futures
import json
import os
import re
import sys
import time

import requests

_API = "https://api.github.com"
_UA = "indiebizOS/1.0 (personal research agent)"
_RETRYABLE = {429, 500, 502, 503, 504}


def _headers():
    headers = {"Accept": "application/vnd.github+json", "User-Agent": _UA,
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(url, params=None):
    last_error = "응답 없음"
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, headers=_headers(), timeout=25)
            if response.status_code == 200:
                return response.json(), None
            try:
                detail = (response.json() or {}).get("message")
            except ValueError:
                detail = response.text[:160]
            last_error = f"HTTP {response.status_code}: {detail or '오류'}"
            if response.status_code not in _RETRYABLE:
                break
        except (requests.RequestException, ValueError) as exc:
            last_error = f"요청 실패: {exc}"
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
    return None, last_error


def _repo_name(raw):
    value = str(raw or "").strip().rstrip("/")
    value = re.sub(r"^https?://github\.com/", "", value, flags=re.I)
    value = value.removesuffix(".git")
    parts = value.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 and all(parts[:2]) else ""


def _item(repo):
    license_data = repo.get("license") or {}
    return {
        "title": repo.get("full_name") or repo.get("name") or "",
        "full_name": repo.get("full_name") or "",
        "summary": repo.get("description") or "",
        "url": repo.get("html_url") or "",
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "open_issues": repo.get("open_issues_count", 0),
        "language": repo.get("language"),
        "license": license_data.get("spdx_id") if isinstance(license_data, dict) else None,
        "created": repo.get("created_at"),
        "updated": repo.get("updated_at"),
        "pushed": repo.get("pushed_at"),
        "archived": bool(repo.get("archived")),
        "fork": bool(repo.get("fork")),
        "topics": repo.get("topics") or [],
    }


def _one(name):
    data, error = _get(f"{_API}/repos/{name}")
    return (_item(data), None) if data else (None, f"{name}: {error}")


def main():
    try:
        args = json.loads(sys.stdin.read() or "{}")
    except (TypeError, ValueError):
        args = {}

    repos = args.get("repos") or args.get("repositories") or []
    if isinstance(repos, str):
        repos = [x.strip() for x in repos.split(",") if x.strip()]
    names = list(dict.fromkeys(filter(None, (_repo_name(x) for x in repos))))
    errors = []

    if names:
        workers = min(8, len(names))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            pairs = list(pool.map(_one, names))
        items = [item for item, _ in pairs if item]
        errors.extend(error for _, error in pairs if error)
    else:
        query = str(args.get("query") or "").strip()
        if not query:
            print(json.dumps({"success": False, "error": "repos 또는 query가 필요합니다.",
                              "items": []}, ensure_ascii=False))
            return
        limit = max(1, min(int(args.get("limit") or 15), 100))
        sort = str(args.get("sort") or "stars")
        order = str(args.get("order") or "desc")
        data, error = _get(f"{_API}/search/repositories",
                           {"q": query, "sort": sort, "order": order, "per_page": limit})
        items = [_item(x) for x in (data or {}).get("items", [])]
        if error:
            errors.append(error)

    result = {"success": bool(items), "count": len(items), "items": items}
    if errors:
        result["errors"] = errors
    if not items:
        result["error"] = "GitHub 저장소 메타를 가져오지 못했습니다."
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
