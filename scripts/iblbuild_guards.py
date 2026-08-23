"""build_ibl_nodes 소스-스캔 가드 (2026-07-18 모듈화 — 1500줄 규칙).

build_ibl_nodes.py 에서 verbatim 이동: 포크-가드(INDIEBIZ_PROFILE)·OS-가드·
launcher-가드·교재-가드. 전부 (root[, data]) → issues 리스트 계약.
"""
from __future__ import annotations
import re
from pathlib import Path

# === 포크-가드: INDIEBIZ_PROFILE 분기 위치 통제 (2026-06-13, 폰-자아 호스팅) ===
# 무포크 규율(docs/PHONE_SELF_HOSTING_HANDOFF.md §3): "폰전용" 분기는 *이음매 아래*
# (핸들러·프로토콜/채널 바인딩·센서 바인딩·라우팅 substrate·capability 감지)에만 허용.
# 이음매 *위*(하네스·인지·어휘: agent_cognitive/consciousness_agent/prompt_builder/
# agent_runner/goal_evaluator/ibl_nodes_src/common_prompts)의 INDIEBIZ_PROFILE 분기 = 포크냄새 → 0.
# 판별: "반대편 HW가 같은 능력을 잃으면 같은 경로를 타나?" 그렇다면 capability-gate(detect_body)로,
# 진짜 HW 바인딩이면 이 allowlist의 이음매-아래 파일에.
# allowlist에 파일을 추가하려면 "이게 정말 이음매 아래인가?"를 의식적으로 답할 것 (추세 하향 못박기).
PROFILE_BRANCH_ALLOWLIST = {
    "backend/base/runtime_utils.py",       # detect_body — capability 감지 본체(정당한 거처)
    "backend/ibl/ibl_engine.py",          # chokepoint 라우팅(_forward_to_mac/forward_to_phone)
    "backend/datastore/ibl_registry.py",        # 몸-사전 설치 필터(_phone_runnable — ibl_engine 에서
                                      # 이동, 2026-08-05 ⑦. 로드=설치라 프로파일이 곧 사전)
    "backend/surface/api_launcher_web.py",    # phone_manifest runnable 필터(라우팅/렌더 substrate)
    "backend/ibl/channel_engine.py",      # nostr 채널 프로토콜 바인딩(드라이버)
    "backend/services/indienet_common.py",     # nostr 통합 바인딩 — _ON_PHONE(프로파일 감지) 정의처
                                      # (2026-07-18 모듈화: indienet.py 의 분기가 여기로 이주,
                                      #  본체·믹스인은 _ON_PHONE 이름만 참조)
    "backend/services/nostr_phone_bridge.py",  # 폰 네이티브 nostr 브리지(HW 바인딩)
    "backend/services/phone_notifications.py", # 폰 알림 센서 바인딩
    "backend/services/calendar_actions.py",    # 스케줄 발화 실행 substrate — 맥=GUI창+WS '보이는 실행' /
                                      # 폰=창·WS 없어 헤드리스 폰-로컬 execute_pipeline. "무엇을 실행"(어휘)이
                                      # 아니라 "어떤 몸 메커니즘으로 실행"(바인딩)이라 이음매 아래.
    "data/packages/installed/tools/radio/tool_radio.py",     # 핸들러(이음매 아래)
    "data/packages/installed/tools/android/handler.py",      # 핸들러(이음매 아래)
}
# 스캔 대상 루트(이음매 위/아래 모두) — allowlist 밖에서 분기가 나타나면 적발.
PROFILE_SCAN_DIRS = ["backend", "data/packages/installed"]


def check_profile_branches(root: Path) -> list[str]:
    """이음매 위 모듈에 INDIEBIZ_PROFILE 분기가 침투했는지 적발(포크-가드).
    allowlist(이음매 아래) 밖의 .py 파일이 INDIEBIZ_PROFILE 를 참조하면 위반."""
    issues: list[str] = []
    seen_allowed: set[str] = set()
    for rel in PROFILE_SCAN_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "INDIEBIZ_PROFILE" not in text:
                continue
            rel_path = path.relative_to(root).as_posix()
            if rel_path in PROFILE_BRANCH_ALLOWLIST:
                seen_allowed.add(rel_path)
                continue
            issues.append(
                f"{rel_path}: 이음매 위 모듈에 INDIEBIZ_PROFILE 분기 — "
                f"capability-gate(detect_body)로 바꾸거나, 진짜 이음매-아래면 "
                f"PROFILE_BRANCH_ALLOWLIST 에 의식적으로 추가"
            )
    # allowlist에 등록됐지만 더 이상 분기를 안 쓰는(또는 못 읽은) 파일 = stale 후보.
    # 부재-패키지 관용(Phase 4): 파일이 안 읽힌 이유가 "그 패키지가 지금 not_installed로
    # 옮겨져 있을 뿐"이면 진짜 stale이 아니다(재설치하면 다시 보인다) — 조용히 관용.
    # 그 외(파일은 있는데 분기가 사라짐, 또는 패키지 자체가 어디에도 없음)만 stale로 적발.
    stale = PROFILE_BRANCH_ALLOWLIST - seen_allowed
    for rel_path in sorted(stale):
        if _is_dormant_package_path(root, rel_path):
            continue
        issues.append(
            f"(stale) {rel_path}: allowlist에 있으나 INDIEBIZ_PROFILE 분기 없음 — "
            f"PROFILE_BRANCH_ALLOWLIST 에서 제거 권장"
        )
    return issues


def _is_dormant_package_path(root: Path, rel_path: str) -> bool:
    """rel_path가 `data/packages/installed/<tools|extensions>/<pkg>/...` 형태이고,
    그 <pkg>가 지금 not_installed 쪽에 존재하면 True(일시 철거, 관용 대상)."""
    parts = Path(rel_path).parts
    try:
        idx = parts.index("installed")
    except ValueError:
        return False
    if idx + 2 >= len(parts) or parts[:idx] != ("data", "packages"):
        return False
    pkg_type, pkg_name = parts[idx + 1], parts[idx + 2]
    return (root / "data" / "packages" / "not_installed" / pkg_type / pkg_name).is_dir()


# === OS-가드: platform/유닉스-바이너리 의존 위치 통제 (2026-06-21, OS 이식성) ===
# INDIEBIZ_PROFILE 가드(폰 vs 데스크탑)의 형제 — 이쪽은 맥 vs 윈도우 vs 리눅스를 본다.
# 목적: 몸 독립(superstructure) backend 코어에 OS 특정 코드(platform.system 분기, 맥/유닉스
# 전용 바이너리·경로)가 침투하는 걸 막는다. 선언된 이음매 파일(OS_SEAM_ALLOWLIST)만 OS 코드를
# 담을 수 있고, **그 목록이 곧 "윈도우/리눅스 이식 시 점검 대상" 체크리스트**다(잊혀짐을 사람의
# 주의력이 아니라 실패하는 빌드로 막는다 — IBL --check 삼각검증과 같은 철학).
# 패키지 핸들러는 이음매-아래(이미 OS 터치 전제)라 이 가드 범위 밖 — docs/OS_PORTABILITY_SEAM.md 가 tier-2 추적.
OS_SEAM_ALLOWLIST = {
    "backend/base/runtime_utils.py",   # detect_body + 번들 런타임 경로(Win/Unix 분기)
    "backend/ibl/ibl_exec_output.py",   # 파일 열기·클립보드·탐색기(Darwin/Windows/Linux 3분기)
    "backend/surface/api_pcmanager.py",   # 드라이브/볼륨 열거·열기(3 OS)
    "backend/datastore/file_index.py",      # 파일 검색(맥=Spotlight mdfind/mdls·폰=MediaStore)
    "backend/surface/api_nas.py",         # ffmpeg/ffprobe 경로 해석
    "backend/api.py",             # 부팅: Windows stdout 인코딩 + PATH 보강
    "backend/services/calendar_html.py",   # 브라우저 열기(open/start)
    "backend/surface/api_photo.py",       # 사진 파일 OS 열기(open/startfile/xdg-open) — tier-2: ibl_executors 열기와 통합 후보
    "backend/surface/api_tunnel.py",      # cloudflared 바이너리 위치 탐색(외부 바이너리 finder) — tier-2: 공유 find_binary 후보
    "backend/providers/claude_code.py",  # claude CLI 바이너리 탐색(Win %APPDATA%\\...\\claude.exe vs 맥 .app 번들) — 외부 바이너리 finder, api_tunnel 과 동류
    "backend/common/platform_utils.py",  # 크로스플랫폼 이음매 그 자체(find_binary/spawn_detached/open_url/install_hint — os.name·sys.platform 분기가 존재 이유)
    "backend/services/ffmpeg_provision.py",  # ffmpeg 자동 공급(윈도우 첫 실행 시 BtbN 정적 빌드 다운로드 — os.name 분기)
    "backend/base/desktop_notify.py",  # OS 네이티브 데스크탑 알림(osascript/PowerShell 토스트/notify-send — 3 OS 분기가 존재 이유)
}
OS_SCAN_DIRS = ["backend"]
# 강한 OS 신호만 — 일반 'open'/'start' 같은 건 오탐이라 제외.
OS_MARKERS = [
    "platform.system(", "sys.platform", 'os.name ==', "os.name==",
    "mdfind", "mdls", "osascript", "pbcopy", "pbpaste",
    "lsappinfo", "screencapture", "caffeinate",
    "/opt/homebrew", "/usr/local/bin",
]


def check_os_branches(root: Path) -> list[str]:
    """몸 독립 backend 코어에 OS 특정 코드가 샜는지 적발(OS-가드).
    allowlist(선언된 OS 이음매) 밖의 .py 가 OS 마커를 쓰면 위반."""
    issues: list[str] = []
    seen_allowed: set[str] = set()
    for rel in OS_SCAN_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            hits = sorted({m for m in OS_MARKERS if m in text})
            if not hits:
                continue
            rel_path = path.relative_to(root).as_posix()
            if rel_path in OS_SEAM_ALLOWLIST:
                seen_allowed.add(rel_path)
                continue
            issues.append(
                f"{rel_path}: 몸 독립 코어에 OS 의존 {hits} — 이음매"
                f"(runtime_utils/ibl_executors 등)로 옮기거나, 진짜 이음매면 "
                f"OS_SEAM_ALLOWLIST 에 의식적으로 추가"
            )
    stale = OS_SEAM_ALLOWLIST - seen_allowed
    for rel_path in sorted(stale):
        issues.append(
            f"(stale) {rel_path}: OS_SEAM_ALLOWLIST 에 있으나 OS 마커 없음 — 제거 권장"
        )
    return issues


def check_launcher_handlers(root: Path) -> list[str]:
    """launcher 창 명령(어휘=계약)이 Electron main.js에 실제 핸들러를 갖는지 적발(launcher-가드).

    어휘(open_window app) → ibl_routing.command_map 값(open_X_window) → main.js switch case 의
    계약이 *효과 계층*까지 닿는지 검증. 이전 indienet 좀비처럼 어휘·라우터는 약속하나
    main.js 핸들러가 없어 success:true 인데 창이 안 뜨는 침묵 실패를 빌드 단계에서 막는다.
    (--check 가 백엔드 핸들러에서 멈추던 한계를 효과 계층으로 한 칸 더 확장.)
    소스 일부 부재(폰/헤드리스 체크아웃)거나 패턴 불검출이면 graceful skip(거짓양성 방지)."""
    import re as _re
    issues: list[str] = []
    from iblbuild_common import backend_module_path
    routing = backend_module_path(root, "ibl_routing")
    main_js = root / "frontend" / "electron" / "main.js"
    if not routing.is_file() or not main_js.is_file():
        return issues
    try:
        rtext = routing.read_text(encoding="utf-8")
        mtext = main_js.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues
    routed = set(_re.findall(r'"(open_\w+_window)"', rtext))   # command_map 값
    cases = set(_re.findall(r"case\s+['\"](open_\w+_window)['\"]", mtext))  # switch case
    if not routed or not cases:
        return issues  # 형식 변경 — graceful skip
    for cmd in sorted(routed - cases):
        issues.append(
            f"backend/ibl_routing.py 가 '{cmd}' 로 라우팅하나 "
            f"frontend/electron/main.js switch 에 case 없음 — 침묵 실패(좀비 창). "
            f"main.js 에 핸들러 추가하거나 command_map 에서 제거."
        )
    return issues


def check_textbook(root: Path, data: dict | None) -> list[str]:
    """교재-가드: 12_ibl_only.md ↔ 카탈로그 정합 검증.

    산문 교재는 삼각검증 밖이라 어휘 이동 시 조용히 낡는다 (실사례: 2026-06-30
    engines→table 분리 때 코드 예시는 갱신됐지만 노드 선택표·변환자 귀속 산문이
    낡은 채 남아 에이전트를 [engines:filter] 오경로로 안내). 두 가지를 커밋
    게이트로 잡는다:
      1) 교재 안 모든 [node:action] 스니펫이 카탈로그에 실존
         (WRONG: 표기가 있는 줄은 반례 교보재이므로 면제)
      2) 노드 선택표('## N Nodes' 절)의 노드 집합·개수가 카탈로그와 정확히 일치
    """
    issues: list[str] = []
    path = root / "data" / "common_prompts" / "fragments" / "12_ibl_only.md"
    if not path.is_file():
        return [f"교재 부재: {path}"]
    if data is None:
        return issues
    nodes = data.get("nodes") or {}
    text = path.read_text(encoding="utf-8")

    # 1) 스니펫 실존 (제어 블록 어휘와 [node:action] 플레이스홀더는 제외)
    _control = {"goal", "if", "else", "case"}
    for line in text.splitlines():
        if "WRONG" in line:
            continue
        for m in re.finditer(r"\[(\w+):(\w+)\]", line):
            n, a = m.group(1), m.group(2)
            if n in _control or (n, a) == ("node", "action"):
                continue
            if n not in nodes:
                issues.append(f"교재 스니펫의 노드 미실존: [{n}:{a}]")
            elif a not in (nodes[n].get("actions") or {}):
                issues.append(f"교재 스니펫의 액션 미실존: [{n}:{a}]")

    # 2) 노드 선택표 ↔ 카탈로그 노드 집합
    sec = re.search(r"^## (\d+) Nodes\b.*?\n(.*?)(?=^## )", text, re.M | re.S)
    if not sec:
        issues.append("교재에 '## N Nodes' 절이 없음 (노드 선택표 실종)")
    else:
        count = int(sec.group(1))
        listed = set(re.findall(r"^\| `(\w+)`", sec.group(2), re.M))
        catalog = set(nodes.keys())
        for n in sorted(catalog - listed):
            issues.append(f"교재 노드 선택표에 카탈로그 노드 누락: {n}")
        for n in sorted(listed - catalog):
            issues.append(f"교재 노드 선택표에 카탈로그 밖 노드: {n}")
        if count != len(catalog):
            issues.append(f"교재 제목의 노드 수({count}) ≠ 카탈로그({len(catalog)})")

    return list(dict.fromkeys(issues))


# === 자기상 가드: system_structure.md 의 액션 수 ↔ 레지스트리 (2026-08-15) ===
# 왜 필요한가: 이 파일의 '현 상태' 줄은 prompt_builder.get_system_structure_core() 를 타고
# 실행·의식·평가 세 에이전트에 **항상 주입**된다. 즉 시스템이 자기 몸 크기를 아는 유일한
# 창구인데, 어휘를 바꿔도 아무도 이 줄을 안 고쳐서 조용히 낡는다.
#
# ★두 번 재발했다: 2026-08-06 에 "시스템이 자기 액션 수를 163+ 로 잘못 말함(에피소드 935)"
#   을 손으로 고쳤는데, 9일 만에 다시 6개 노드 수가 전부 틀어졌다(150 vs 실제 142).
#   손으로 고치는 것은 답이 아니다 — 뷰-어휘 문서-동기 가드와 같은 수로 빌드가 대조한다.
#
# 마커로 감싼 한 줄만 본다(<!-- SELF_IMAGE:START/END -->). 문서 꼬리에는 옛 "현 상태: …"
# 기록이 여럿 남아 있는데 그건 *그때의 기록*이라 건드리면 안 되기 때문이다.
_SELF_IMAGE_DOC = "data/system_docs/system_structure.md"
_SELF_IMAGE_START = "<!-- SELF_IMAGE:START -->"
_SELF_IMAGE_END = "<!-- SELF_IMAGE:END -->"


def check_self_image(root: Path, data: dict | None) -> list[str]:
    """'현 상태 = N노드 M 액션(노드별…)·P 도구 패키지 + Q extensions' ↔ 실측 대조."""
    import re as _re

    if not isinstance(data, dict):
        return []
    nodes = data.get("nodes") or {}
    if not nodes:
        return []

    fp = root / _SELF_IMAGE_DOC
    if not fp.is_file():
        return [f"{_SELF_IMAGE_DOC}: 문서 부재"]
    text = fp.read_text(encoding="utf-8")
    if _SELF_IMAGE_START not in text or _SELF_IMAGE_END not in text:
        return [f"{_SELF_IMAGE_DOC}: SELF_IMAGE 마커 부재 — 자기상 줄을 "
                f"{_SELF_IMAGE_START}…{_SELF_IMAGE_END} 로 감쌀 것"]
    seg = text.split(_SELF_IMAGE_START, 1)[1].split(_SELF_IMAGE_END, 1)[0]

    issues: list[str] = []
    m = _re.search(r"(\d+)\s*노드\s*(\d+)\s*액션\(([^)]*)\)", seg)
    if not m:
        return [f"{_SELF_IMAGE_DOC}: 마커 안에 'N노드 M 액션(…)' 정형 줄 없음 — 받은 것: {seg[:80]!r}"]

    doc_nodes, doc_total, per = int(m.group(1)), int(m.group(2)), m.group(3)
    real_per = {n: len(b.get("actions") or {}) for n, b in nodes.items() if isinstance(b, dict)}
    real_total = sum(real_per.values())

    if doc_nodes != len(real_per):
        issues.append(f"{_SELF_IMAGE_DOC}: 노드 수 {doc_nodes} ≠ 실제 {len(real_per)}")
    if doc_total != real_total:
        issues.append(f"{_SELF_IMAGE_DOC}: 총 액션 {doc_total} ≠ 실제 {real_total}")

    doc_per = {}
    for part in _re.split(r"[·,]", per):
        pm = _re.match(r"\s*([a-z_]+)\s*(\d+)\s*$", part)
        if pm:
            doc_per[pm.group(1)] = int(pm.group(2))
    for node, real_n in sorted(real_per.items()):
        if node not in doc_per:
            issues.append(f"{_SELF_IMAGE_DOC}: 노드 '{node}' 가 자기상 줄에 없음(실제 {real_n})")
        elif doc_per[node] != real_n:
            issues.append(f"{_SELF_IMAGE_DOC}: {node} {doc_per[node]} ≠ 실제 {real_n}")
    for node in sorted(set(doc_per) - set(real_per)):
        issues.append(f"{_SELF_IMAGE_DOC}: 자기상 줄의 노드 '{node}' 는 레지스트리에 없음")

    # 패키지·extensions 수 (설치 디렉토리 실측)
    pm = _re.search(r"(\d+)\s*도구 패키지\s*\+\s*(\d+)\s*extensions", seg)
    if pm:
        for label, rel, doc_n in (("도구 패키지", "data/packages/installed/tools", int(pm.group(1))),
                                  ("extensions", "data/packages/installed/extensions", int(pm.group(2)))):
            d = root / rel
            if not d.is_dir():
                continue
            real_n = len([p for p in d.iterdir() if p.is_dir() and not p.name.startswith("__")])
            if doc_n != real_n:
                issues.append(f"{_SELF_IMAGE_DOC}: {label} {doc_n} ≠ 실제 {real_n}")
    return issues
