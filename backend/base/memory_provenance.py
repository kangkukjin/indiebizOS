"""기억의 발화자·발생 범위와 검색 발췌. 관련성은 현재 사실의 증명이 아니다."""
import json


def source_summary(source_ref):
    roles, scopes = set(), []

    def visit(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if value.get("attribution") in {"quoted", "unresolved", "conveyed"}:
                roles.add("external")
            elif value.get("role") in {"user", "assistant", "tool", "external"}:
                roles.add(value["role"])
            scope = {k: value[k] for k in ("episode_id", "task", "recorded_at", "retention") if value.get(k)}
            if scope and scope not in scopes:
                scopes.append(scope)
            for key in ("evidence", "sources", "previous", "supplement"):
                if value.get(key):
                    visit(value[key])

    visit(source_ref)
    status = ("user_statement" if roles == {"user"} else
              "external_record" if roles == {"external"} else
              "assistant_record" if roles == {"assistant"} else "mixed" if roles else "unattributed")
    return {"status": status, "roles": sorted(roles), "scopes": scopes,
            "policy": "해당 발화·사건의 기록이다. 현재 대상·시점과 일치하는지 대조한다. "
                      "assistant_record·external_record는 사용자 확정 사실이 아니며 unattributed는 출처 미확인이다."}


def search_view(row, query, limit=240):
    """일치어가 모인 구간을 보여 주되 잘린 원문의 크기·읽기 ID를 보존한다."""
    result = dict(row)
    content = result.pop("content", "")
    lower = content.casefold()
    words = list(dict.fromkeys(w.casefold() for w in query.split() if w))[:20]
    positions = {max(0, lower.find(w) - 50) for w in words if w in lower}
    start = max(positions, key=lambda p: (sum(w in lower[p:p + limit] for w in words), -p)) if positions else 0
    start = min(start, max(0, len(content) - limit))
    end = min(len(content), start + limit)
    result.update(preview=("…" if start else "") + content[start:end] + ("…" if end < len(content) else ""),
                  preview_truncated=start > 0 or end < len(content), content_chars=len(content),
                  preview_offset=start, provenance=source_summary(result.pop("source_ref", None)))
    return result
