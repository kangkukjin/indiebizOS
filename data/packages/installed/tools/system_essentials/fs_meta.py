"""[self:file_find] 메타 검색 모드 — OS 색인(backend/file_index) 위임.

handler.py 에서 2026-08-05 분리 (1500줄 규칙). 구 pc-manager query_storage([self:fs_query])
흡수 — 파일 찾기는 한 개념, glob/색인은 기제. mdfind 어댑터 재구현 금지(단일 출처).
"""
import os
import json
from datetime import datetime


_META_KEYS = ("search_term", "q", "query", "name", "extension", "kind",
              "min_size_mb", "sort", "path", "root_path")


def meta_query_or_error(tool_input: dict) -> str:
    """pattern 없는 glob_files 호출의 처리 — 메타 파라미터(path/sort 만도 유효:
    {path:"~/Desktop", sort:"mtime"}=그 폴더 최근 파일, 구 fs_query 실사용 형태)면
    색인 질의, 아무것도 없으면 안내 오류."""
    if any(tool_input.get(k) for k in _META_KEYS):
        return _fs_meta_query(tool_input)
    return json.dumps({"success": False,
                       "error": "pattern(glob) 또는 메타 파라미터(search_term/extension/kind/min_size_mb/path)가 필요합니다."},
                      ensure_ascii=False)


def _fs_parse_min_size_mb(raw):
    """min_size_mb 가 "10MB"/"1.5gb"/"500kb" 문자열로 와도 숫자(MB)로 파싱."""
    if not isinstance(raw, str):
        return raw
    m = re.match(r"\s*([\d.]+)\s*([kmgt]?b?)\s*$", raw.strip(), re.I)
    if not m:
        return None
    _factor = {"kb": 1/1024, "k": 1/1024, "mb": 1, "m": 1,
               "gb": 1024, "g": 1024, "tb": 1024*1024, "t": 1024*1024,
               "b": 1/(1024*1024), "": 1}.get((m.group(2) or "mb").lower(), 1)
    return float(m.group(1)) * _factor


def _fs_epoch_to_iso(mtime) -> str:
    """epoch(float/int) → 'YYYY-MM-DD HH:MM' (file_index mtime 표시용)."""
    try:
        return datetime.fromtimestamp(float(mtime)).strftime("%Y-%m-%d %H:%M") if mtime else ""
    except (TypeError, ValueError, OSError):
        return ""


def _fs_meta_query(tool_input: dict) -> str:
    """[self:file_find] 메타 검색 모드 — OS 색인(backend/file_index) 직접. 선스캔 불요·항상 최신.

    구 pc-manager _query_storage 이식 (2026-08-05 어휘 압축: fs_query 흡수 —
    파일 찾기는 한 개념, glob/색인은 기제). mdfind 어댑터를 재구현하지 않는다 —
    보편 질의는 단일 출처(backend/file_index.query)에서 한 번만.
    """
    import file_index  # 핸들러는 backend 모듈 경로 확보됨 (runtime_utils 선례)

    min_size_mb = _fs_parse_min_size_mb(tool_input.get("min_size_mb"))
    min_size_bytes = int(min_size_mb * 1024 * 1024) if min_size_mb else None
    try:
        limit = max(1, int(tool_input.get("limit") or 100))
    except (TypeError, ValueError):
        limit = 100

    # search_term 동의어 흡수 — LLM 이 query/name/pattern 등으로 자연스레 부른다.
    #   (param명 불일치는 q=None → mdfind 전체매칭 → 타임아웃 → 거짓 '0'을 낳던 침묵실패.)
    search_term = (tool_input.get("search_term") or tool_input.get("q")
                   or tool_input.get("query") or tool_input.get("name"))
    res = file_index.query(
        kind=tool_input.get("kind") or "any",
        q=search_term,
        ext=tool_input.get("extension"),
        path=tool_input.get("root_path") or tool_input.get("path") or tool_input.get("volume_name"),
        min_size=min_size_bytes,
        limit=limit,
        sort=tool_input.get("sort") or "mtime",
    )
    if not res.get("success"):
        return json.dumps(res, ensure_ascii=False)

    items = res.get("items", [])
    records, rows = [], []
    for it in items:
        path = it.get("path") or ""
        size = it.get("size") or 0
        size_mb = round(size / 1048576, 2)
        mtime = _fs_epoch_to_iso(it.get("mtime"))
        meta_bits = [f"{size_mb} MB", it.get("kind") or "", mtime]
        records.append({
            "title": it.get("name") or os.path.basename(path),
            "meta": " · ".join(b for b in meta_bits if b),
            "summary": "", "url": path,
            "path": path, "size": size, "size_mb": size_mb,
            "mtime": mtime, "kind": it.get("kind"), "ext": it.get("ext"),
        })
        rows.append([it.get("name") or "", size_mb, path, mtime])

    out = {
        "success": True,
        "count": res.get("count"),
        "shown": len(records),
        "scope": res.get("scope"),
        "items": records,
        # table 통화(비파괴) — file_find >> [table:spreadsheet/document] 호환 유지.
        "table": {"columns": ["이름", "크기(MB)", "경로", "수정일"], "rows": rows},
    }
    if res.get("fallback"):
        out["fallback"] = res["fallback"]
    return json.dumps(out, ensure_ascii=False)
