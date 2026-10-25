"""Privacy checks for reusable current programs."""
import re
from typing import Optional

def _phrase_private_reason(code: str) -> Optional[str]:
    """관용구 본문의 개인 명사 — 슬롯으로 비우지 못한 홈 경로·개인 명사 목록(data/private_nouns.txt, gitignore) 적발."""
    m = re.search(r'(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^/\\"\'\s]+', code or "")
    if m:
        return f"홈 경로가 남아 있음(슬롯으로 비울 것): {m.group(0)}"
    try:
        from pathlib import Path as _P
        lst = _P(__file__).parent.parent.parent / "data" / "private_nouns.txt"
        if lst.exists():
            for raw in lst.read_text(encoding="utf-8").splitlines():
                t = raw.strip()
                if not t or t.startswith("#") or t.lower().startswith("allow:"):
                    continue
                try:
                    if re.search(t, code, re.IGNORECASE):
                        return "개인 명사 목록에 걸림(슬롯으로 비울 것)"
                except re.error:
                    continue
    except Exception:
        pass
    return None
