"""집중 관심 폴더(focus folders) — 몸 독립 개념, 몸별 바인딩.

always-on 거친 디스크 지도("어디에")의 *범위*를 정한다. system_structure.md 가 indiebizOS
한 폴더의 큐레이션된 자기상이듯, 이건 사용자 콘텐츠 루트(들) 아래의 거친 골격이다. 모든
하드웨어(맥/윈도우/리눅스/폰)가 *같은 어휘*로 *자기* focus 루트 아래를 돈다 — 개념·생성기는
몸 독립(상부구조), focus 루트·잡음만 몸별(하부구조). 헌법1조 substrate/superstructure 이음매.

해소 = (사용자 선언 OR 몸별 기본값) ∪ forager territory 제안
  - 몸별 기본값: 콜드스타트 없이 첫날부터 동작.
  - 사용자 선언(data/focus_folders.json): "무엇이 나에게 중요한가"는 주관 → 사용자가 좁히거나
    넓힌다(augmentation-over-autonomy). 선언이 있으면 기본값을 *대체*.
  - territory 제안: 자주 되돌아온 루트(forage territory 승격)를 발견해 *보탠다*.

깊은 상세·큐레이션(어느 가지가 죽었나·내 것인가·관습)은 forager(territory/owner/map) 몫.
골격은 거칠게·짧게 — 상시 주입이라 길어지면 분업이 깨진다.
"""
import os
import time
from pathlib import Path
from typing import List, Optional

import file_index
from runtime_utils import get_base_path

_MAXDEPTH = 3              # 선언 루트 거친 깊이(측정: Desktop depth3 ≈ 1.3k tok)
_TERRITORY_DEPTH = 1      # territory 제안 루트는 얕게(루트+직속 = "여기도 자주 감" 포인터)
_BUDGET_CHARS = 6000     # 전역 상한(백스톱) — 큰 territory 가 상시 예산을 날리지 않게.
_CACHE_TTL = 600.0        # 골격 캐시 수명(초). walk 는 ~15ms 라 비용은 무시 가능, 신선도용.
_CONFIG_NAME = "focus_folders.json"

# 모듈 캐시 — 상시-on 이라 매 메시지 walk 를 피한다(TTL 내 재사용).
_cache = {"text": None, "at": 0.0, "key": None}


def _profile() -> str:
    try:
        from runtime_utils import detect_body
        return detect_body().get("profile") or "mac"
    except Exception:
        return "mac"


def _default_focus_folders(profile: str) -> List[str]:
    """몸별 합리적 기본값(데스크탑) — 콜드스타트 방지. 존재 필터는 get_focus_folders 에서.

    ★폰은 의도적으로 제외 — os.walk 가 안드로이드 스코프드 스토리지에 안 먹히고(파일 접근은
    MediaStore 경유), 폰에선 거친 디스크 지도 실익이 작다. 폰 게이트는 인지층
    agent_cognitive._build_disk_skeleton 에 있어 focus_map 은 폰에서 호출되지 않는다.
    """
    home = Path.home()
    if profile == "windows":
        return [str(home / "Desktop"), str(home / "Documents")]
    if profile == "linux":
        return [str(home / "Desktop"), str(home)]
    # mac (기본) — 측정으로 검증된 핫존. Documents·기타는 선언/territory 로 보탬.
    return [str(home / "Desktop")]


def _user_focus_folders(profile: str) -> Optional[List[str]]:
    """data/focus_folders.json 사용자 선언(있으면 기본값 대체). 리스트 또는 {profile: [...]}.

    없거나 비면 None(=기본값 사용). 형식 오류는 무시(파이프라인 불변).
    """
    try:
        import json
        path = get_base_path() / "data" / _CONFIG_NAME
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # profile 키 또는 "_all"
            folders = data.get(profile) or data.get("_all")
        elif isinstance(data, list):
            folders = data
        else:
            folders = None
        if folders and isinstance(folders, list):
            return [str(f) for f in folders if f]
        return None
    except Exception:
        return None


def _territory_suggestions(profile: str) -> List[str]:
    """forager territory 승격 루트를 focus 후보로 — '자주 되돌아온 곳'. best-effort.

    ★이 하드웨어의 디스크 *공간*(body=profile)으로 한정 — territory 는 포식 공간별이라
    맥 territory 가 폰 골격에 새면 안 된다(forage body=mac/phone/… 이 디스크 자아). 코드/웹
    공간(code:*/web)은 디스크 walk 대상이 아니므로 자연 배제.
    """
    try:
        import forage_memory
        out = []
        for loc in forage_memory.territory_loci(body=profile):
            p = os.path.abspath(os.path.expanduser(loc))
            if os.path.isfile(p):
                p = os.path.dirname(p)  # 파일 앵커면 그 폴더를
            if os.path.isdir(p):
                out.append(p)
        return out
    except Exception:
        return []


def _covered(path: str, roots: List[str]) -> bool:
    """path 가 이미 어느 root 의 (자기 또는 하위)면 True — 중복 깊이 walk 방지."""
    ap = os.path.abspath(path).rstrip(os.sep)
    for r in roots:
        ar = os.path.abspath(r).rstrip(os.sep)
        if ap == ar or ap.startswith(ar + os.sep):
            return True
    return False


def _resolve(profile: str) -> tuple:
    """(declared, territory) 두 묶음 — 둘 다 존재·정규화·중복 제거, territory 는 declared 미커버만.

    declared = 사용자 선언 OR 몸별 기본(주 관심 — depth-3 상세). territory = forager 가 발견한
    추가 루트(얕은 포인터 depth-1). 분리하는 이유: 큰 territory(예: Obsidian 볼트)를 depth-3 로
    펴면 상시 예산이 폭발 → territory 는 '여기도 자주 감' 정도의 얕은 냄새만.
    """
    base = _user_focus_folders(profile)
    if base is None:
        base = _default_focus_folders(profile)
    declared: List[str] = []
    for f in base:
        p = os.path.abspath(os.path.expanduser(f))
        if os.path.isdir(p) and p not in declared:
            declared.append(p)
    territory: List[str] = []
    for s in _territory_suggestions(profile):
        if s not in declared and s not in territory and not _covered(s, declared):
            territory.append(s)
    return declared, territory


def get_focus_folders(profile: Optional[str] = None) -> List[str]:
    """집중 관심 폴더 최종 해소 — 존재하는 절대경로 목록(declared + territory 제안)."""
    declared, territory = _resolve(profile or _profile())
    return declared + territory


def _budget_join(blocks: List[str], budget: int = _BUDGET_CHARS) -> str:
    """블록들을 전역 char 예산까지 이어붙이고, 넘으면 줄 경계에서 자르고 표식.

    declared 가 앞이라 우선 포함되고, territory 꼬리가 예산 초과 시 잘린다(상시 바운드 보장).
    """
    out, used, truncated = [], 0, False
    for blk in blocks:
        if not blk:
            continue
        for ln in blk.split("\n"):
            if used + len(ln) + 1 > budget:
                truncated = True
                break
            out.append(ln)
            used += len(ln) + 1
        if truncated:
            break
    if truncated:
        out.append(f"… (생략 — 상시 골격 {budget}자 상한; 상세는 포식 기억 회상으로)")
    return "\n".join(out)


def build_coarse_map(*, maxdepth: int = _MAXDEPTH, profile: Optional[str] = None,
                     force: bool = False) -> str:
    """집중 관심 폴더 아래 거친 골격 — declared=depth-3 / territory=depth-1 + 전역 예산. 캐시(TTL)."""
    profile = profile or _profile()
    declared, territory = _resolve(profile)
    key = (tuple(declared), tuple(territory), maxdepth)
    now = time.monotonic()
    if (not force and _cache["text"] is not None and _cache["key"] == key
            and (now - _cache["at"]) < _CACHE_TTL):
        return _cache["text"]
    if not declared and not territory:
        _cache.update({"text": "", "at": now, "key": key})
        return ""
    blocks = []
    if declared:
        blocks.append(file_index.disk_skeleton(declared, maxdepth=maxdepth))
    if territory:
        blocks.append(file_index.disk_skeleton(territory, maxdepth=_TERRITORY_DEPTH))
    skeleton = _budget_join(blocks)
    _cache.update({"text": skeleton, "at": now, "key": key})
    return skeleton


def build_coarse_map_xml(*, maxdepth: int = _MAXDEPTH,
                         profile: Optional[str] = None) -> str:
    """<disk_skeleton> 블록 — 인지 파이프라인 주입용(execution/forage 옆, 상시-on)."""
    skel = build_coarse_map(maxdepth=maxdepth, profile=profile)
    if not skel:
        return ""
    note = "집중 관심 폴더 아래 거친 디렉토리 골격(어디에). 상세·큐레이션은 포식 기억 회상으로."
    return f'<disk_skeleton note="{note}">\n{skel}\n</disk_skeleton>'
