#!/usr/bin/env python3
"""미등록 디스패처 도구 일괄 tool.json 등록 (2026-05-28).

라운드 2 통합 작업에서 ibl_actions.yaml은 새 디스패처 이름을 가리키게 했고
핸들러에도 분기를 추가했지만, 일부 패키지의 tool.json에 도구 정의를 추가하지
않아 tool_loader가 핸들러를 못 찾는 케이스 15개.

증상: `{"error": "도구 핸들러를 찾을 수 없습니다: <tool_name>"}`
원인: tool_loader._tool_to_package_map은 tool.json의 tools 배열만 보고 매핑.
처방: 각 패키지 tool.json의 tools 배열에 디스패처 도구 정의 추가.

input_schema는 보수적으로 `additionalProperties: true`로 두어 모든 파라미터를
핸들러로 그대로 전달. description은 ibl_nodes.yaml의 description+
target_description을 합쳐서 system_ai가 호출 시 충분한 가이드가 되도록.
"""
from __future__ import annotations
import json
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_ROOT = ROOT / "data" / "packages" / "installed" / "tools"
IBL_NODES = ROOT / "data" / "ibl_nodes.yaml"

# (tool_name, package_dir, node, action) — ibl_nodes 위치
ADDITIONS = [
    ("library_book",   "culture",          "sense",   "book"),
    ("realty_price",   "real-estate",      "sense",   "realty"),
    ("startup_search", "startup",          "sense",   "startup"),
    ("kosis_lookup",   "kosis",            "sense",   "kosis"),
    ("photo_op",       "photo-manager",    "self",    "photo"),
    ("blog_search_op", "blog",             "self",    "blog_search"),
    ("health_op",      "health-record",    "self",    "health"),
    ("read_op",        "system_essentials","self",    "read"),
    ("html_video",     "media_producer",   "engines", "html_video"),
    ("remotion",       "remotion-video",   "engines", "remotion"),
    ("web_site",       "web-builder",      "engines", "web_site"),
    ("web_catalog",    "web-builder",      "engines", "web_catalog"),
    ("web_create",     "web-builder",      "engines", "web_create"),
    ("web_component",  "web-builder",      "engines", "web_component"),
]


def main() -> int:
    with IBL_NODES.open(encoding="utf-8") as f:
        nodes = yaml.safe_load(f)["nodes"]

    added, skipped, errors = 0, 0, []
    for tool_name, pkg, node, action in ADDITIONS:
        try:
            action_def = nodes[node]["actions"][action]
        except KeyError:
            errors.append(f"ibl_nodes에 [{node}:{action}] 없음")
            continue

        desc = action_def.get("description", "").strip()
        target_desc = action_def.get("target_description", "").strip()
        full_desc = f"{desc}\n\n파라미터: {target_desc}" if target_desc else desc

        pkg_tj = PKG_ROOT / pkg / "tool.json"
        if not pkg_tj.exists():
            errors.append(f"{pkg}/tool.json 없음")
            continue

        try:
            data = json.loads(pkg_tj.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"{pkg}/tool.json 파싱 실패: {e}")
            continue

        tools = data.setdefault("tools", [])
        existing = {t.get("name") for t in tools}
        if tool_name in existing:
            print(f"[SKIP] {pkg}/{tool_name} 이미 등록")
            skipped += 1
            continue

        new_tool = {
            "name": tool_name,
            "description": full_desc,
            "input_schema": {
                "type": "object",
                "properties": {
                    "op": {
                        "type": "string",
                        "description": "동작 분기 — target_description 참조"
                    }
                },
                "additionalProperties": True,
            },
        }
        tools.append(new_tool)
        pkg_tj.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[ADDED] {pkg}/{tool_name} → [{node}:{action}]")
        added += 1

    print()
    print(f"결과: {added}개 추가 / {skipped}개 skip / {len(errors)}개 에러")
    for e in errors:
        print(f"  ! {e}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
