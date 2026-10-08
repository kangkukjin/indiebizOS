#!/usr/bin/env python3
"""AI 동향 원문을 공유창고의 고정 주소에 발행. 작성 직후와 예약 작업의 공통 경로.

HTML 이 완성되면 바로 공개한다(보고서HTML publish 기본 direct) — 감독 턴에서도 검수 대기 초안을 만들지
않는다(2026-10-07 사용자 결정). published 는 공개 완료 여부 그대로다.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from common.pkg_utils import load_sibling  # noqa: E402
from portal_base import _core  # noqa: E402

renderer = load_sibling(__file__, "보고서HTML")


def publication_link():
    """공개면과 같은 설정·파일 관문을 사용한다. 주소 생성은 접속 검증이 아니다."""
    link = {"public_url": None, "public_url_status": "unconfigured",
            "public_url_checked": False}
    try:
        base = (_core().load_state().get("public_base") or "").strip().rstrip("/")
        if not base:
            return link
        parsed = urlsplit(base)
        if (parsed.scheme not in ("http", "https") or not parsed.netloc
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            return {**link, "public_url_status": "invalid_configuration"}
        # /f?path는 레벨 폴더를 제외한 상대경로를 받는다(portal_warehouse).
        return {**link, "public_url": f"{base}/f?path={quote('오늘의 AI 보고서.html')}",
                "public_url_status": "configured"}
    except Exception:
        # 공개면 부품이 없어도 이미 완료한 로컬 발행은 성공으로 보존한다.
        return {**link, "public_url_status": "unavailable"}


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
    result.update(publication_link())
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
