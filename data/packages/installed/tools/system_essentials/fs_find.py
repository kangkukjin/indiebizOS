"""파일 찾기 하부 — 바운드 walk + 중괄호 확장. handler.execute 의 file_find 가 쓴다.

2026-08-29 분리: handler.py 가 1500줄 규칙을 넘겨(1526줄) 게이트가 커밋을 막았다.
파일 계열 형제(fs_grep·fs_edit·fs_meta)와 같은 자리에 찾기의 하부를 둔다 —
handler 에는 분기와 봉투만 남기고, "어떻게 훑는가"는 여기가 안다.
"""
import fnmatch
import os
import re
import time
import unicodedata

# 무경계 재귀 glob 방지 — 매 호출 홈 전체(node_modules·캐시)를 색인 없이 stat 하던 게
# 타임아웃 원인. 절대-dead 가지치기 + 시간 예산으로 바운드.
# ★ 절대-dead 목록은 file_index(포식 substrate)와 *공유* — fs_query 와 같은 단일 출처라
#   드리프트 없음. path-substring 판정이라 ~/Library 통째가 아니라 캐시류만 쳐냄(iCloud 보존).
try:
    from file_index import ABSOLUTE_DEAD_SUBSTR as DEAD_SUBSTR
except Exception:  # import 경로 미확보 시 폴백(동일 내용)
    DEAD_SUBSTR = (
        "/System/", "/Applications/", "/Library/Caches/",
        "/Library/Application Support/", "/Library/Containers/",
        "/Library/Group Containers/", "/node_modules/", "/.Trash", ".app/",
        "/__pycache__/", "/site-packages/", "/.venv/", "/venv/",
        "/.git/", "/DerivedData/", "/.gradle/", "/.cargo/", "/.npm/",
    )
FIND_DEADLINE_S = 25.0  # 엔진 타임아웃 전에 부분결과라도 반환


def is_dead_dir(path):
    """절대-dead(설치트리·캐시) 디렉토리면 True — walk 가 안 들어감(의도 불문 제외)."""
    p = path.rstrip("/") + "/"
    return any(n in p for n in DEAD_SUBSTR)


def expand_braces(pat: str) -> list:
    """`**/*.{tsx,css}` → [`**/*.tsx`, `**/*.css`]. 중첩·복수 그룹은 재귀로 푼다.

    glob/fnmatch 는 중괄호를 리터럴로 취급해 0건이 됐다(2026-08-29 마찰 ①).
    """
    m = re.search(r"\{([^{}]*)\}", pat)
    if not m or "," not in m.group(1):
        return [pat]
    head, tail = pat[:m.start()], pat[m.end():]
    out = []
    for alt in m.group(1).split(","):
        out.extend(expand_braces(head + alt + tail))
    return out


def bounded_find(root, basename_pat, max_results):
    """root 하위를 바운드 재귀 순회 — 정크 가지치기 + dot-dir 스킵(glob ** 와 동일) + 시간 예산.

    무한정 walk 로 시스템을 멈추지 않는다. 시간 초과/상한 도달 시 partial=True 로 알린다.
    """
    deadline = time.time() + FIND_DEADLINE_S
    # macOS 한글 파일명=NFD(자모분해), 패턴은 보통 NFC → fnmatch 바이트비교가 침묵 누락.
    # 양쪽을 NFC 로 정규화해 비교(mdfind 는 정규화하지만 fnmatch 는 안 함. forage_map #33).
    pat = unicodedata.normalize("NFC", basename_pat)
    pat_lower = pat.lower()
    matches, partial = [], False
    for dirpath, dirs, files in os.walk(root, topdown=True):
        if time.time() > deadline:
            partial = True
            break
        # 가지치기: 절대-dead(공유 목록, path-substring) + dot-dir. 제자리 수정으로 walk 가 안 들어감.
        #   ~/Library 통째가 아니라 캐시류만 → ~/Library/Mobile Documents(iCloud) 는 보존.
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and not is_dead_dir(os.path.join(dirpath, d))]
        # 매칭: 파일 + 디렉토리 둘 다 (glob.glob 은 둘 다 매칭했음 — 예: .epub 번들·iCloud 책은 디렉토리).
        # macOS 파일시스템은 대소문자 무시 → 소문자 비교로 맞춤.
        for name in files + dirs:
            nfc = unicodedata.normalize("NFC", name)
            if fnmatch.fnmatch(nfc.lower(), pat_lower):
                matches.append(os.path.join(dirpath, name))
                if len(matches) >= max_results:
                    return matches, True
    return matches, partial
