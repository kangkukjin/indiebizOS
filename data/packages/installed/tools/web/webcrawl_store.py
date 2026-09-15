"""크롤 원문 스냅샷과 URL 캐시. 표시량은 저장 키·수집량에 관여하지 않는다."""
import hashlib
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone

_LOCKS = [threading.RLock() for _ in range(32)]


def _policy():
    from ibl_retyping import load_policy_block
    return load_policy_block("webcrawl_cache", {"reuse_seconds": 900})


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _scope(project_path):
    from thread_context import get_current_agent_id
    return f"{os.path.abspath(project_path) if project_path else ''}|{get_current_agent_id() or ''}"


def text_to_blocks(title, text):
    """원문을 문단 items로. 표시를 위해 자르지 않는다."""
    blocks = [{"type": "heading", "level": 1, "text": str(title)}] if title else []
    blocks.extend({"type": "paragraph", "text": para.strip()}
                  for para in str(text or "").split("\n\n") if para.strip())
    return blocks or [{"type": "paragraph", "text": str(text or "")}]


def fetch_once(url, fetch, *, refresh=False, project_path=None, op="content"):
    """같은 소유 범위·URL은 짧게 재사용, 원문 파일은 spill의 24h 수명을 따른다.

    스냅샷은 불변 파일이다. refresh는 새 파일을 만들므로 이전 ref를 덮지 않는다.
    실패·불완전 진단 응답은 재사용하지 않는다. 원문 보관 실패도 호출자에게 알린다.
    """
    from common.spill import spill_dir, spill_write
    ttl = max(0, int(_policy()["reuse_seconds"]))
    key = hashlib.sha256(f"v3|{_scope(project_path)}|{url}".encode()).hexdigest()
    index = os.path.join(spill_dir(), f"crawl_cache_{key}.json")
    with _LOCKS[int(key[:8], 16) % len(_LOCKS)]:
        now = time.time()
        if not refresh and ttl:
            try:
                with open(index, encoding="utf-8") as f:
                    saved = json.load(f)
                if 0 <= now - saved["fetched_at"] < ttl:
                    with open(saved["ref"]["path"], encoding="utf-8") as f:
                        result = json.load(f)
                    if not isinstance(result, dict) or not result.get("success") \
                            or not isinstance(result.get("text"), str) or not isinstance(result.get("items"), list):
                        raise ValueError("크롤 원문 캐시 형식 손상")
                    if op == "content" and result.get("_structure_only"):
                        raise ValueError("구조 전용 수집은 본문 완전성을 보장하지 않습니다")
                    if op != "content" and result.get("_page_structure", {}).get("errors"):
                        raise ValueError("불완전한 구조 정보는 다시 수집합니다")
                    return _decorate(result, saved, True, ttl)
            except (OSError, ValueError, KeyError, TypeError):
                pass  # 만료·소실 캐시만 재수집 — 원문을 미리보기로 대체하지 않는다
        result = fetch()
        if not isinstance(result, dict) or not result.get("success"):
            return result
        result = dict(result)
        result["items"] = text_to_blocks(result.get("title"), result.get("text"))
        # 문단 위치와 출처는 여러 URL을 합쳐도 살아 있어야 한다.
        for paragraph_index, row in enumerate(result["items"], 1):
            row.update(url=result.get("resolved_url") or url,
                       paragraph_index=paragraph_index)
        if op != "content" and result.get("length", 0) < 200:
            result["_structure_only"] = True
        ref = spill_write(json.dumps(result, ensure_ascii=False), tag="crawl_source")["ref"]
        saved = {"fetched_at": time.time(), "ref": ref}
        if not result.get("reason") and not result.get("truncated"):
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=spill_dir(),
                                                 prefix="crawl_index_", suffix=".json", delete=False) as f:
                    tmp = f.name
                    json.dump(saved, f)
                os.replace(tmp, index)
            finally:
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)
        return _decorate(result, saved, False, ttl)


def _decorate(result, saved, hit, ttl):
    result = dict(result)
    result["source_ref"] = dict(saved["ref"])
    result["cache"] = {"hit": hit, "fetched_at": _iso(saved["fetched_at"]),
                       "reuse_until": _iso(saved["fetched_at"] + ttl)}
    return result
