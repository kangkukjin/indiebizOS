#!/usr/bin/env python3
"""AI 동향 원문을 공유창고의 고정 주소에 발행. 작성 직후와 예약 작업의 공통 경로.

HTML 이 완성되면 바로 공개한다(보고서HTML publish 기본 direct) — 감독 턴에서도 검수 대기 초안을 만들지
않는다(2026-10-07 사용자 결정). published 는 공개 완료 여부 그대로다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from common.pkg_utils import load_sibling  # noqa: E402

renderer = load_sibling(__file__, "보고서HTML")


def publish(args):
    folder = ROOT / "outputs/ai_trend_reports"
    if args.get("src"):
        source = renderer._repo_path(args["src"], "src")
    else:
        candidates = sorted(p for p in folder.glob("ai_trend_report_*.md")
                            if re.fullmatch(r"ai_trend_report_\d{4}-\d{2}-\d{2}\.md", p.name))
        if not candidates:
            raise ValueError("발행할 AI 동향 보고서가 없습니다. 기존 공유판은 보존합니다.")
        source = candidates[-1]
    result = renderer.render({"src": str(source),
                              "dst": "공유창고/0/오늘의 AI 보고서.html", "theme": "briefing"})
    result["source"] = str(source)
    result["published"] = not result.get("publication_pending", False)
    return result


def main():
    try:
        print(json.dumps(publish(json.loads(sys.stdin.read() or "{}")), ensure_ascii=False))
    except (OSError, ValueError, TypeError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
