#!/usr/bin/env python3
"""코퍼스 재라벨 마이그레이션 (2026-06-04, IBL 사용성 감사 🟡 배치).

오라벨된 코퍼스 엔트리의 ibl_code를 의도에 맞는 액션으로 교정/제거한다.

1) navigate_route{query:X} (목적지 to/origin/destination 없음 = 오라벨):
   - 음식 의도 → [sense:restaurant]{query:"X 맛집"}
   - 그 외     → [sense:weather]{city:"X"}
   - 진짜 내비(to/origin/destination)는 유지.
2) local_save{path:X} (파일 저장 의도 오라벨; 실제 local_save=가게DB 저장):
   → [self:write]{path:X}.  무인자 [self:local_save](가게DB)는 유지.
3) html_video{topic:X} (주제만으론 영상 불가 — topic→영상 파이프라인 미구현, 모달리티상 slide와도 다름):
   → 엔트리 제거.  scenes 기반 html_video는 유지.

사용: python3 scripts/migrate_corpus_relabel.py [--write]   (기본 dry-run)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    ROOT / "data/training/ibl_training_balanced_20260516.json",
    ROOT / "data/training/ibl_distilled.json",
]
FOOD_TOKENS = ["밥", "식당", "맛집", "맛있", "맛난", "먹", "점심", "저녁", "먹거리", "음식", "카페", "분식", "술집", "디저트"]

NAV_QUERY_RE = re.compile(r'\[sense:navigate_route\]\{query:\s*"([^"]*)"\}')
LOCAL_SAVE_PATH_RE = re.compile(r'\[self:local_save\]\{path:\s*"([^"]*)"\}')
# html_video 가 있고 topic 파라미터를 쓰며 scenes 가 없으면 = 실현 불가 → 제거 대상.
HTMLVIDEO_TOPIC_RE = re.compile(r'\[engines:html_video\]\{topic:')


def transform(intent: str, code: str):
    """(new_code, drop) 반환. new_code=None & drop=False 면 변경 없음."""
    # 3) html_video topic-only → 제거
    if "html_video" in code and HTMLVIDEO_TOPIC_RE.search(code) and "scenes" not in code:
        return None, True

    new = code
    # 1) navigate_route{query} (목적지 없음) → weather/restaurant
    if "navigate_route" in new and not re.search(
        r'\[sense:navigate_route\]\{[^}]*(to|origin|destination)\s*:', new
    ):
        is_food = any(t in intent for t in FOOD_TOKENS)

        def nav_repl(m):
            place = m.group(1)
            if is_food:
                return f'[sense:restaurant]{{query: "{place} 맛집"}}'
            return f'[sense:weather]{{city: "{place}"}}'

        new = NAV_QUERY_RE.sub(nav_repl, new)

    # 2) local_save{path} → self:write
    new = LOCAL_SAVE_PATH_RE.sub(r'[self:write]{path: "\1"}', new)

    if new != code:
        return new, False
    return None, False


def main():
    write = "--write" in sys.argv
    total_changed = total_dropped = 0
    for f in FILES:
        if not f.is_file():
            continue
        data = json.load(open(f, encoding="utf-8"))
        out = []
        changed = dropped = 0
        for e in data:
            code = e.get("ibl_code", "")
            intent = e.get("intent", "")
            new, drop = transform(intent, code)
            if drop:
                print(f"  DROP {intent[:36]!r:38} -- {code[:55]}")
                dropped += 1
                continue
            if new and new != code:
                print(f"  {intent[:32]!r:34} {code[:42]}  =>  {new[:56]}")
                e["ibl_code"] = new
                changed += 1
            out.append(e)
        print(f"### {f.name}: {changed}건 변경, {dropped}건 제거 (총 {len(data)}→{len(out)})\n")
        total_changed += changed
        total_dropped += dropped
        if write and (changed or dropped):
            json.dump(out, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    tag = "(WRITE 완료)" if write else "(dry-run)"
    print(f"=== 변경 {total_changed} · 제거 {total_dropped} {tag} ===")


if __name__ == "__main__":
    main()
