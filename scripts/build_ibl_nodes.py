#!/usr/bin/env python3
"""ibl_nodes.yaml 빌드 — 편집용 소스 6개를 단일 yaml로 병합 + 삼각 검증.

편집 워크플로:
1) `data/ibl_nodes_src/<name>.yaml` 중 하나를 편집
2) `python scripts/build_ibl_nodes.py` 실행
3) `data/ibl_nodes.yaml`이 갱신됨 (런타임이 읽는 단일 파일)

런타임 코드는 단일 ibl_nodes.yaml만 읽는다 (ibl_access / tool_loader /
tool_selector / system_tools).

병합 방식: 바이트-단위 연결. 소스 파일들의 내용은 원본 yaml의 해당 span에서
잘라낸 바이트 그대로이므로, 정상 워크플로에서는 byte-identical 라운드트립이
보장된다 (소스 편집 후엔 그 부분만 달라짐).

검증 (2026-05-28 추가) — router:handler 액션에 대해 삼각 일치 확인:
  src.tool       ↔  packages/.../tool.json 의 name
  src.ops.values ↔  tool.json input_schema.properties.op.enum
  src.ops.default ↔ tool.json input_schema.properties.op.default
  src.ops.values ↔  handler.py 의 _OP_DISPATCHERS[tool_name] 키 (AST, 정확)
                       또는 _OP_DISPATCHERS 없으면 op 문자열 substring (폴백)
  src.ops.default ↔ handler.py 의 _OP_DEFAULTS[tool_name] (AST, _OP_DISPATCHERS 있을 때만)
실패하면 `--check`는 비0 종료, 일반 빌드는 경고만 출력.

코퍼스 param 정합 (2026-06-04 추가, --check/--validate 전용):
  학습 코퍼스의 액션별 param 키 ↔ (핸들러 읽기키 ∪ ACTION_PARAM_ALIASES ∪ 보편키 ∪ target_key).
  코퍼스가 자연어로 쓰는 키를 핸들러가 조용히 무시하는 신규 불일치를 검출 (silent-ignore 회귀 방지).
  의도된 노이즈는 CORPUS_PARAM_ALLOW 에 등록. 파서/코퍼스 미가용 시 건너뜀.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path


# 순서가 중요 — 원본 yaml의 노드 순서와 동일해야 함.
NODE_ORDER = ["sense", "self", "limbs", "others", "engines", "table"]

# 패키지 탐색 경로 — installed/tools 가 표준, extensions 도 함께 스캔.
PACKAGE_DIRS = [
    "data/packages/installed/tools",
    "data/packages/installed/extensions",
]

# not_installed 미러 — 부재-패키지 관용(Phase 4)에서 "철거됐을 뿐 실존하는 패키지"와
# "진짜 좀비(정의 자체가 없어진)"를 구분하는 데 쓴다. PACKAGE_DIRS 와 폴더명만 다름.
NOT_INSTALLED_PACKAGE_DIRS = [
    "data/packages/not_installed/tools",
    "data/packages/not_installed/extensions",
]

# === runs_on 능력 태그 (2026-06-11, #3 폰 네이티브) ===
# 액션이 어디서 도는가: anywhere(기본·이식가능 로직/HTTP) / mac_only(집 PC 하드웨어·
# 무거운 의존·미검증 패키지) / phone_only(폰 하드웨어=알림·센서, 미래 M3).
VALID_RUNS_ON = {"anywhere", "mac_only", "phone_only"}
DEFAULT_RUNS_ON = "anywhere"

# 실기기(Galaxy A36)에서 import+종단 실행이 검증된 폰안전 패키지 — 폰 프로파일의 단일 진실 소스.
# (옛 build.gradle 의 하드코딩 _PHONE_PACKAGES 를 여기로 승격. phone_manifest.json 으로 파생.)
# handler 라우터 액션의 폰 실행가능성은 이 집합으로 결정(미검증 패키지=폰서 제외).
# 새 패키지를 폰서 검증하면 여기 추가.
PHONE_VERIFIED_PACKAGES = {
    "location-services",
    "investment",
    "culture",
    "radio",
    "web",
    "web-kr",     # web에서 분리된 네이버 검색(naver_search). 순수 HTTP API — web과 동일하게 폰서 동작(분리 전 web으로 검증됨).
    "real-estate",
    "android",   # M3: [sense:phone] 폰 로컬 알림. limbs:android(android_op)은 mac_only 태그로 제외.
    "business",  # 메신저(others:messages/neighbor/contact)+비즈니스 CRM(self:business*). business.db 폰 머지 토대 위. auto_response 는 mac_only 로 제외(PC 전용 폴러).
    "cctv",      # CCTV 검색(sense:cctv search) — 모듈 import importlib.util(stdlib)뿐, HLS는 WebView <video>+hls.js 재생.
    "health-record",  # 의료기록(self:health save/query) — storage 가 stdlib(sqlite)만. health_records.db 폰↔맥 합집합 머지(health_sync, business.db 선례) 토대.
    # 2026-06-13 runs_on 정직성 회복: anywhere 인데 폰 미번들이던 이식 가능 패키지(HTTP API 조회류,
    # 자원이 외부라 몸 무관). 의존성 모듈레벨 스캔=stdlib/HTTP. A36 대표 액션 실행으로 import 확정.
    "cloudflare",       # Cloudflare API(HTTP)
    "context7",         # 라이브러리 문서 검색(HTTP)
    "kosis",            # 통계청 KOSIS API(HTTP)
    "legal",            # 법령/판례 검색(HTTP)
    "startup",          # 창업 정보(HTTP + stdlib xml)
    "local-info",       # 지역 정보 검색(HTTP)
    "shopping-assistant",  # 네이버 쇼핑 검색(API). 다나와·중고(playwright)는 지연 import→폰선 graceful 미지원. arxiv 선례.
    "memory",   # 심층기억(self:memory). 자아별 사적 로컬 DB(동기화 안 함). 모듈레벨 stdlib만(numpy/sqlite_vec 지연) → 폰서 import 안전, 시맨틱 미가용 시 LIKE/FTS 키워드 폴백(기존 graceful 강등). 시맨틱-온-폰(/embed 렌트+brute-force)은 후속.
    # self 노드 = AI 자신 → file 액션은 자기 몸의 fs 에 작용(각 몸 자기 파일·시계). 둘 다 모듈레벨 stdlib,
    # 무거운 것(fitz/docx/openpyxl·api_pcmanager)은 지연 import → 폰 import 안전. read 의 PDF/docx 포맷만
    # 폰서 graceful 실패(텍스트는 됨). explorer(GUI)·spreadsheet(openpyxl write)는 액션별 mac_only 유지.
    "system_essentials",  # self:time(자기 시계)·read/write/list/grep/copy/move/delete/file_find/edit(자기 fs)
    "pc-manager",         # self:storage/fs_query/folder_note(자기 fs 인덱스·주석). limbs:explorer(GUI)는 mac_only 유지.
    "photo-manager",      # self:photo 라이브 질의 — backend/file_index 가 몸 분기(맥 Spotlight↔폰 MediaStore via PhoneActions.queryMedia). 핸들러 얇은 preset, photo_db/scanner 는 guard import(폰선 질의 경로 미사용). A36 종단 검증.

    "contest",          # AI 경진대회 검색(sense:contest, Kaggle API HTTP + stdlib). KAGGLE_API_TOKEN 폰 프로비저닝 전제.
    "study",            # 연구 검색(HTTP + stdlib; study:paper 만 arxiv 3p — A36서 안 되면 그 액션 mac_only)
    "python-exec",  # 폰 네이티브 코드 실행 탈출구 — handler 가 capability-gate 로 폰서 Chaquopy 인-프로세스 exec(맥=subprocess). stdlib만 import(서드파티 0). execute_python 은 IBL 액션 아니라 직접 도구라 runnable_actions 엔 미포함(정상).
    "data-ops",  # 통화→통화 변환자(filter/sort/take/select/dedup/groupby/join/union/merge). 순수 superstructure(IBL 문법, 몸 무관)+stdlib만(json/re, 서드파티 0). 폰-로컬 통화(sense:here 등)는 폰서 거르고 정렬해야 맞음 → anywhere 가 정직. 외부 자원 없음.
    "media_producer",  # ★순수 연산만 anywhere(document html 렌더=문자열·structure/image_critic/image_gemini=httpx+Gemini REST). 무거운 emitter(html_video·tts·slide·render_html·remotion=moviepy/edge_tts/playwright)는 액션별 mac_only 유지 → 폰선 포워드. moviepy·edge_tts 모듈레벨 import를 지연화해 폰서 모듈 import 성공(폰 시뮬 검증). 갇혀있던 문서IR 렌더 해방.
}

# === 포크-가드: INDIEBIZ_PROFILE 분기 위치 통제 (2026-06-13, 폰-자아 호스팅) ===
# 무포크 규율(docs/PHONE_SELF_HOSTING_HANDOFF.md §3): "폰전용" 분기는 *이음매 아래*
# (핸들러·프로토콜/채널 바인딩·센서 바인딩·라우팅 substrate·capability 감지)에만 허용.
# 이음매 *위*(하네스·인지·어휘: agent_cognitive/consciousness_agent/prompt_builder/
# agent_runner/goal_evaluator/ibl_nodes_src/common_prompts)의 INDIEBIZ_PROFILE 분기 = 포크냄새 → 0.
# 판별: "반대편 HW가 같은 능력을 잃으면 같은 경로를 타나?" 그렇다면 capability-gate(detect_body)로,
# 진짜 HW 바인딩이면 이 allowlist의 이음매-아래 파일에.
# allowlist에 파일을 추가하려면 "이게 정말 이음매 아래인가?"를 의식적으로 답할 것 (추세 하향 못박기).
PROFILE_BRANCH_ALLOWLIST = {
    "backend/runtime_utils.py",       # detect_body — capability 감지 본체(정당한 거처)
    "backend/ibl_engine.py",          # chokepoint 라우팅(_forward_to_mac/_forward_to_phone)
    "backend/api_launcher_web.py",    # phone_manifest runnable 필터(라우팅/렌더 substrate)
    "backend/channel_engine.py",      # nostr 채널 프로토콜 바인딩(드라이버)
    "backend/indienet.py",            # nostr 통합 바인딩
    "backend/nostr_phone_bridge.py",  # 폰 네이티브 nostr 브리지(HW 바인딩)
    "backend/phone_notifications.py", # 폰 알림 센서 바인딩
    "backend/calendar_actions.py",    # 스케줄 발화 실행 substrate — 맥=GUI창+WS '보이는 실행' /
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
    "backend/runtime_utils.py",   # detect_body + 번들 런타임 경로(Win/Unix 분기)
    "backend/ibl_executors.py",   # 파일 열기·클립보드·탐색기(Darwin/Windows/Linux 3분기)
    "backend/api_pcmanager.py",   # 드라이브/볼륨 열거·열기(3 OS)
    "backend/file_index.py",      # 파일 검색(맥=Spotlight mdfind/mdls·폰=MediaStore)
    "backend/api_nas.py",         # ffmpeg/ffprobe 경로 해석
    "backend/api.py",             # 부팅: Windows stdout 인코딩 + PATH 보강
    "backend/calendar_html.py",   # 브라우저 열기(open/start)
    "backend/api_photo.py",       # 사진 파일 OS 열기(open/startfile/xdg-open) — tier-2: ibl_executors 열기와 통합 후보
    "backend/api_tunnel.py",      # cloudflared 바이너리 위치 탐색(외부 바이너리 finder) — tier-2: 공유 find_binary 후보
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
    routing = root / "backend" / "ibl_routing.py"
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


# === 코퍼스 param 정합 검사 (2026-06-04) ===
# 모든 액션이 자연히 받는 보편 키 (op 디스패치/레거시 target).
UNIVERSAL_PARAM_KEYS = {"op", "target"}

# 코퍼스가 쓰지만 핸들러/별칭에 의도적으로 없는 키 (문서화된 예외).
# 목적: 신규 불일치만 잡고 알려진 노이즈는 통과. 코퍼스 정제/별칭으로 해소되면 여기서 제거할 것.
CORPUS_PARAM_ALLOW: dict[str, set[str]] = {
    # browser_op은 2차 selector 'mode'를 _OP_SELECTOR로 동적 pop(handler.py) —
    # 정적 리터럴이 아니라 검출 불가. 핸들러가 실제로 읽으므로 의도된 예외.
    "limbs:browser": {"mode"},
}
# 정리됨(2026-06-04): pew_research:topic / blog:sort / web_site:reference / web:font
#   (migrate_allowlist_cleanup.py — 군더더기 제거) + self:trigger:cron
#   (trigger_engine._cron_to_config 로 내부 해소 — 핸들러가 cron 직접 읽음).

# 학습 코퍼스 (param 키 추출 대상).
CORPUS_FILES = [
    "data/training/ibl_training_balanced_20260516.json",
    "data/training/ibl_distilled.json",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_tool_index(root: Path) -> dict[str, tuple[Path, dict]]:
    """모든 패키지 tool.json 을 스캔해 {tool_name: (pkg_dir, tool_def)} 사전 구축."""
    index: dict[str, tuple[Path, dict]] = {}
    for rel in PACKAGE_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for pkg_dir in sorted(base.iterdir()):
            if not pkg_dir.is_dir():
                continue
            tool_json = pkg_dir / "tool.json"
            if not tool_json.is_file():
                continue
            try:
                data = json.loads(tool_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(
                    f"[build_ibl_nodes] tool.json 파싱 실패 ({pkg_dir.name}): {e}",
                    file=sys.stderr,
                )
                continue
            for tool in data.get("tools", []) or []:
                name = tool.get("name")
                if name:
                    if name in index:
                        # 충돌 — 다른 패키지에서 같은 이름 재등록.
                        prev_pkg = index[name][0].name
                        print(
                            f"[build_ibl_nodes] WARN tool 이름 충돌: {name} "
                            f"({prev_pkg} vs {pkg_dir.name})",
                            file=sys.stderr,
                        )
                    index[name] = (pkg_dir, tool)
    return index


def _extract_op_dispatchers(handler_text: str) -> dict[str, tuple[set[str], object]] | None:
    """handler.py 본문에서 _OP_DISPATCHERS dict 를 AST 로 파싱.

    Returns:
        {tool_name: (op_key_set, raw_dict_node)} 또는 None (dict 없음).
        타입이 dict 가 아니거나 키가 문자열 상수가 아니면 None.
    """
    try:
        tree = ast.parse(handler_text)
    except SyntaxError:
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_OP_DISPATCHERS" not in names:
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        result: dict[str, tuple[set[str], object]] = {}
        for k_node, v_node in zip(node.value.keys, node.value.values):
            if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
                continue
            tool_name = k_node.value
            if not isinstance(v_node, ast.Dict):
                continue
            op_keys: set[str] = set()
            for op_k in v_node.keys:
                if isinstance(op_k, ast.Constant) and isinstance(op_k.value, str):
                    op_keys.add(op_k.value)
            result[tool_name] = (op_keys, v_node)
        return result
    return None


def _extract_op_defaults(handler_text: str) -> dict[str, str] | None:
    """handler.py 본문에서 _OP_DEFAULTS dict 를 AST 로 파싱.

    Returns:
        {tool_name: default_op_str} 또는 None.
    """
    try:
        tree = ast.parse(handler_text)
    except SyntaxError:
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_OP_DEFAULTS" not in names:
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        result: dict[str, str] = {}
        for k_node, v_node in zip(node.value.keys, node.value.values):
            if (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)
                    and isinstance(v_node, ast.Constant) and isinstance(v_node.value, str)):
                result[k_node.value] = v_node.value
        return result
    return None


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


def _check_action(
    qualified: str,
    action: dict,
    tool_index: dict[str, tuple[Path, dict]],
) -> list[str]:
    """단일 액션의 정합성을 검사하고 문제 리스트를 반환."""
    issues: list[str] = []
    router = action.get("router")
    tool_name = action.get("tool")
    target_key = action.get("target_key")
    ops = action.get("ops")

    # --- ops 스키마 자체 검증 ---
    if ops is not None:
        if target_key != "op":
            issues.append(
                f"{qualified}: ops 블록은 target_key:op 인 액션에서만 허용 "
                f"(현재 target_key={target_key!r})"
            )
        if not isinstance(ops, dict):
            issues.append(f"{qualified}: ops 는 매핑이어야 함")
            return issues
        values = ops.get("values")
        if not isinstance(values, dict) or not values:
            issues.append(f"{qualified}: ops.values 가 비어있거나 매핑이 아님")
            return issues

    # target_key:op 인데 ops 없음 — 모든 라우터에서 강제 (IBL 어휘 일관성).
    # handler 가 아닌 라우터(system/workflow_engine/trigger_engine 등)는 tool.json 삼각 검증은 못 하지만
    # ops 블록 자체는 어휘 완성을 위해 필수.
    if target_key == "op" and ops is None:
        issues.append(f"{qualified}: target_key:op 인데 ops 블록 없음 ({router or 'unknown'} 라우터)")

    # --- returns(통화 역할) 검증 — 단일 통화(items) 이행 완료(2026-06-27) ---
    # 모든 액션은 자기 통화 역할을 명시한다: 생성(items) · 변환(transform) · 종착(scalar/effect).
    # ★단일 통화: 컬렉션은 전부 items {[{…열린 필드…}]}. 옛 records/table/document/currency 는
    #   전부 items로 흡수 완료 — table(연도×지표 등)·문서IR(type+text)도 items 행dict로, 소비자가 재구성.
    #   (이행 이력: docs/SINGLE_CURRENCY_MIGRATION_HANDOFF.md / architecture_single_currency_items 메모)
    #   ※geo/지도는 통화 아님 — map_data 는 *렌더링 봉투*(파이프 변환자 없음).
    _RETURNS_ENUM = {"items", "transform", "scalar", "effect"}
    returns = action.get("returns")
    group = action.get("group")
    if returns is None:
        issues.append(f"{qualified}: returns 필드 없음 — 통화 역할 명시 필수 (items|transform|scalar|effect)")
    elif returns not in _RETURNS_ENUM:
        issues.append(f"{qualified}: returns={returns!r} 허용 안 됨 (items|transform|scalar|effect)")
    else:
        if group == "transform" and returns != "transform":
            issues.append(f"{qualified}: group:transform 인데 returns={returns!r} — transform 이어야 함")
        if returns == "transform" and group != "transform":
            issues.append(f"{qualified}: returns:transform 은 group:transform 액션에만 (현재 group={group!r})")

    # --- handler 라우터 등록 검증 ---
    if router == "handler":
        if not tool_name:
            issues.append(f"{qualified}: router:handler 인데 tool 필드 없음")
            return issues

        if tool_name not in tool_index:
            issues.append(
                f"{qualified}: tool '{tool_name}' 가 어느 패키지 tool.json 에도 미등록"
            )
            return issues

        pkg_dir, tool_def = tool_index[tool_name]
        pkg_name = pkg_dir.name

        # --- op 삼각 검증 ---
        if ops:
            tj_op_prop = (
                tool_def.get("input_schema", {})
                .get("properties", {})
                .get("op", {})
            ) or {}
            tj_enum = tj_op_prop.get("enum")
            tj_default = tj_op_prop.get("default")

            if not tj_enum:
                issues.append(
                    f"{qualified}: src.ops 선언했으나 tool.json {pkg_name}/{tool_name} "
                    f"에 input_schema.properties.op.enum 없음"
                )
            else:
                src_keys = set(ops.get("values", {}).keys())
                tj_keys = set(tj_enum)
                if src_keys != tj_keys:
                    only_src = sorted(src_keys - tj_keys)
                    only_tj = sorted(tj_keys - src_keys)
                    detail = []
                    if only_src:
                        detail.append(f"src만 있음: {only_src}")
                    if only_tj:
                        detail.append(f"tool.json만 있음: {only_tj}")
                    issues.append(
                        f"{qualified}: op 키 불일치 ({pkg_name}/{tool_name}) — "
                        f"{'; '.join(detail)}"
                    )

            src_default = ops.get("default")
            if src_default != tj_default:
                issues.append(
                    f"{qualified}: op default 불일치 ({pkg_name}/{tool_name}) — "
                    f"src={src_default!r} / tool.json={tj_default!r}"
                )

            # --- handler.py 검사 (AST 우선, substring 폴백) ---
            handler_py = pkg_dir / "handler.py"
            if handler_py.is_file():
                src_text = handler_py.read_text(encoding="utf-8")
                src_op_keys = set(ops.get("values", {}).keys())
                dispatchers = _extract_op_dispatchers(src_text)

                if dispatchers is not None and tool_name in dispatchers:
                    # AST 정확 비교 — _OP_DISPATCHERS[tool_name] 키 ↔ src.ops.values 키
                    handler_keys, _ = dispatchers[tool_name]
                    if handler_keys != src_op_keys:
                        only_src = sorted(src_op_keys - handler_keys)
                        only_handler = sorted(handler_keys - src_op_keys)
                        detail = []
                        if only_src:
                            detail.append(f"src만: {only_src}")
                        if only_handler:
                            detail.append(f"handler만: {only_handler}")
                        issues.append(
                            f"{qualified}: handler.py _OP_DISPATCHERS[{tool_name!r}] 키 불일치 "
                            f"({pkg_name}) — {'; '.join(detail)}"
                        )

                    # _OP_DEFAULTS 도 검사 (있을 때만)
                    defaults = _extract_op_defaults(src_text)
                    if defaults is not None:
                        handler_default = defaults.get(tool_name)
                        src_default = ops.get("default")
                        if handler_default != src_default:
                            issues.append(
                                f"{qualified}: _OP_DEFAULTS[{tool_name!r}] 불일치 "
                                f"({pkg_name}) — src={src_default!r} / handler={handler_default!r}"
                            )
                else:
                    # 폴백: substring 휴리스틱
                    missing = [
                        k
                        for k in src_op_keys
                        if f'"{k}"' not in src_text and f"'{k}'" not in src_text
                    ]
                    if missing:
                        issues.append(
                            f"{qualified}: handler.py {pkg_name} 에 op 문자열 미발견 — {missing} "
                            f"(_OP_DISPATCHERS 도입 권장)"
                        )

    return issues


def _file_read_keys(text: str) -> set[str]:
    """파이썬 소스에서 '핸들러가 읽는 키' 후보를 AST로 추출.
    함수 파라미터명 + .get/_arg/pop 문자열 인자 + call 키워드 인자 + 문자열 subscript."""
    keys: set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return keys
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                keys.add(arg.arg)
        elif isinstance(n, ast.Call):
            for kw in n.keywords:
                if kw.arg:
                    keys.add(kw.arg)
            func = n.func
            fname = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
            if fname in ("_arg", "get", "pop"):
                for arg in n.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        keys.add(arg.value)
        elif isinstance(n, ast.Subscript):
            sl = n.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                keys.add(sl.value)
    keys.discard(None)
    return keys


def _dir_read_keys(paths) -> set[str]:
    """여러 .py 파일에서 읽기키 합집합."""
    keys: set[str] = set()
    for py in paths:
        try:
            keys |= _file_read_keys(py.read_text(encoding="utf-8"))
        except Exception:
            continue
    return keys


def _extract_action_param_aliases(root: Path) -> dict[str, set[str]]:
    """backend/ibl_routing.py 의 ACTION_PARAM_ALIASES → {qualified: {정규키 ∪ 별칭들}} (AST)."""
    path = root / "backend" / "ibl_routing.py"
    out: dict[str, set[str]] = {}
    if not path.is_file():
        return out
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return out
    for node in tree.body:
        # 일반 대입과 주석 대입(`X: T = {...}`) 둘 다.
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "ACTION_PARAM_ALIASES" for t in targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for k_node, v_node in zip(node.value.keys, node.value.values):
            if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
                continue
            ks: set[str] = set()
            if isinstance(v_node, ast.Dict):
                for ck, cv in zip(v_node.keys, v_node.values):
                    if isinstance(ck, ast.Constant) and isinstance(ck.value, str):
                        ks.add(ck.value)
                    if isinstance(cv, ast.List):
                        for el in cv.elts:
                            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                                ks.add(el.value)
            out[k_node.value] = ks
    return out


def _load_corpus_param_keys(root: Path) -> dict[str, set[str]] | None:
    """학습 코퍼스를 실제 IBL 파서로 파싱 → {qualified: set(top-level param 키)}.
    파서/코퍼스 미가용 시 None (검사 건너뜀)."""
    backend = root / "backend"
    try:
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        import ibl_parser  # type: ignore
    except Exception:
        return None

    def walk(obj):
        res = []
        if isinstance(obj, dict):
            if "_node" in obj and "action" in obj:
                res.append(obj)
            for v in obj.values():
                res += walk(v)
        elif isinstance(obj, list):
            for v in obj:
                res += walk(v)
        return res

    out: dict[str, set[str]] = {}
    found_any = False
    for rel in CORPUS_FILES:
        f = root / rel
        if not f.is_file():
            continue
        try:
            entries = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        found_any = True
        for e in entries:
            try:
                parsed = ibl_parser.parse(e.get("ibl_code", ""))
            except Exception:
                continue
            for st in walk(parsed):
                q = f"{st.get('_node')}:{st.get('action')}"
                out.setdefault(q, set()).update((st.get("params") or {}).keys())
    return out if found_any else None


def validate_corpus_params(data: dict, root: Path) -> list[str] | None:
    """코퍼스 param 키 ↔ (핸들러 읽기키 ∪ ACTION_PARAM_ALIASES ∪ 보편키 ∪ target_key) 대조.

    코퍼스가 자연어로 쓰는 키를 핸들러가 조용히 무시하는 신규 불일치를 검출한다.
    router:handler 액션은 패키지 .py 전체를, 그 외(system/engine/driver/trigger)는
    backend/*.py 전역 어휘를 핸들러 키 출처로 본다 (후자는 보수적 = 오탐 회피 우선).
    파서/코퍼스 미가용 시 None (검사 건너뜀)."""
    corpus = _load_corpus_param_keys(root)
    if corpus is None:
        return None
    aliases = _extract_action_param_aliases(root)
    tool_index = build_tool_index(root)
    backend_keys = _dir_read_keys((root / "backend").glob("*.py"))
    pkg_cache: dict[Path, set[str]] = {}

    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            used = corpus.get(qualified)
            if not used:
                continue
            known = set(UNIVERSAL_PARAM_KEYS)
            if action.get("target_key"):
                known.add(action["target_key"])
            known |= aliases.get(qualified, set())
            known |= CORPUS_PARAM_ALLOW.get(qualified, set())
            tool_name = action.get("tool")
            if action.get("router") == "handler" and tool_name and tool_name in tool_index:
                pkg_dir = tool_index[tool_name][0]
                if pkg_dir not in pkg_cache:
                    pkg_cache[pkg_dir] = _dir_read_keys(pkg_dir.rglob("*.py"))
                known |= pkg_cache[pkg_dir]
            else:
                known |= backend_keys
            unknown = sorted(used - known)
            if unknown:
                issues.append(
                    f"{qualified}: 코퍼스 param 키가 핸들러/별칭에 없음 — {unknown} "
                    f"(ibl_routing.ACTION_PARAM_ALIASES 별칭 추가 · 핸들러 폴백 · 코퍼스 정정 중 택1; "
                    f"의도된 노이즈면 build_ibl_nodes.CORPUS_PARAM_ALLOW 에 등록)"
                )
    return issues


# === app: 블록 검증 (2026-06-11, 원격 앱 표면 제네릭화 2단계) ===
# 액션이 자기 앱 표면(inputs/action 템플릿/view)을 선언하면 원격 런처가 자동 파생.
# 어휘 명세: docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md. 소비자: api_launcher_web._derive_instruments.
APP_VIEW_TYPES = {"metric", "kv", "kv_list", "card_list", "image_grid", "sparkline", "list_action", "thread", "form", "editable_list", "map", "calendar", "group"}
# 뷰-이벤트 → 액션 바인딩(상호작용을 데이터로): map 프리미티브가 사용자 조작을 액션으로 흘린다.
#   marker_click=마커 클릭(IBL 템플릿: 페이로드 $id/$name/$lat/$lng/$url · 또는 {stream: true}=마커 url 을 클라이언트 영상 재생, CCTV) · moveend/center_drag=지도 이동·중심 드래그(재조회, $lat/$lng/$radius)
APP_VIEW_EVENTS = {"marker_click", "moveend", "center_drag"}
APP_EVENT_VARS = {"lat", "lng", "id", "name", "radius", "url"}  # 이벤트 페이로드가 액션 템플릿에 주입하는 $변수
APP_INPUT_TYPES = {"text", "select"}
APP_FORM_FIELD_TYPES = {"text", "select", "toggle", "textarea", "images", "date", "time", "datetime", "recurrence"}
APP_KEYS = {"instrument", "icon", "name", "order", "mode", "mode_order", "modes",
            "note", "auto_run", "inputs", "buttons", "action", "view", "renderer", "compose", "filter",
            "phone_render"}
APP_TPL_FILTERS = {"round", "num", "abs", "arrow"}  # + 'opt:' / 'trunc:' 접두 허용


def _app_action_templates(app: dict) -> list[str]:
    """app 블록에서 IBL 액션 템플릿 문자열 전부 수집 (참조 존재 검증용)."""
    import re as _re  # noqa: F401 (지역 사용 명시)
    out: list[str] = []
    if isinstance(app.get("action"), str):
        out.append(app["action"])
    cmp = app.get("compose")  # 블록 레벨 작성바(채팅/피드) — $text + {행필드} 템플릿
    if isinstance(cmp, dict) and isinstance(cmp.get("action"), str):
        out.append(cmp["action"])
    for b in app.get("buttons") or []:
        if isinstance(b, dict) and isinstance(b.get("action"), str):
            out.append(b["action"])
    for inp in app.get("inputs") or []:
        if isinstance(inp, dict) and isinstance(inp.get("options_action"), str):
            out.append(inp["options_action"])

    def walk_view(view):
        for p in view or []:
            if not isinstance(p, dict):
                continue
            # form(저장) / editable_list(추가·삭제) 액션
            if p.get("type") == "form" and isinstance(p.get("action"), str):
                out.append(p["action"])
            if p.get("type") == "form":  # 보조 액션(즐겨찾기 토글·삭제 등)
                for a in p.get("actions") or []:
                    if isinstance(a, dict) and isinstance(a.get("action"), str):
                        out.append(a["action"])
                for f in p.get("fields") or []:  # images 필드의 add_image/remove_image 템플릿
                    if isinstance(f, dict) and f.get("type") == "images":
                        for k in ("add_action", "remove_action"):
                            if isinstance(f.get(k), str):
                                out.append(f[k])
            if p.get("type") in ("editable_list", "calendar"):
                if isinstance(p.get("delete_action"), str):
                    out.append(p["delete_action"])
                add = p.get("add")
                if isinstance(add, dict) and isinstance(add.get("action"), str):
                    out.append(add["action"])
            for _bk in ("button", "button2"):  # list_action 행 버튼(▶ 재생 / ⬇ 다운로드)
                btn = p.get(_bk)
                if isinstance(btn, dict) and isinstance(btn.get("action"), str):
                    out.append(btn["action"])
            drill = p.get("item_click")
            if isinstance(drill, dict):
                if isinstance(drill.get("action"), str):
                    out.append(drill["action"])
                dcmp = drill.get("compose")  # 드릴(스레드) 레벨 작성바
                if isinstance(dcmp, dict) and isinstance(dcmp.get("action"), str):
                    out.append(dcmp["action"])
                walk_view(drill.get("view"))
                for tab in drill.get("tabs") or []:  # 드릴 상세 탭(대화/정보)
                    if isinstance(tab, dict):
                        tcmp = tab.get("compose")
                        if isinstance(tcmp, dict) and isinstance(tcmp.get("action"), str):
                            out.append(tcmp["action"])
                        walk_view(tab.get("view"))
            on = p.get("on")  # 뷰-이벤트(마커클릭·지도이동)→액션 템플릿
            if isinstance(on, dict):
                for v in on.values():
                    if isinstance(v, str):
                        out.append(v)

    walk_view(app.get("view"))
    return out


def _block_local_keys(blk: dict) -> set:
    """블록 내 암묵 입력 키 집합 — compose($text), form 필드, editable_list add 필드.
    드릴 view·tabs 까지 재귀. validate 의 $key↔input 검사에 합류."""
    keys: set = set()

    def from_compose(c):
        if isinstance(c, dict) and c.get("action"):
            keys.add("text")
            if isinstance(c.get("channels"), dict):  # 채널 선택 → action 의 $channel_type/$to 주입
                keys.update(("channel_type", "to"))

    def from_fields(fields):
        for f in fields or []:
            if isinstance(f, dict) and f.get("key"):
                keys.add(f["key"])
            if isinstance(f, dict) and f.get("type") == "images":  # add/remove_image 가 $path 런타임 주입
                keys.add("path")

    def walk(view):
        for p in view or []:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "form":
                from_fields(p.get("fields"))
            if p.get("type") == "editable_list" and isinstance(p.get("add"), dict):
                from_fields(p["add"].get("fields"))
            if p.get("type") == "calendar" and isinstance(p.get("add"), dict):
                from_fields(p["add"].get("fields"))  # add.fields 키(제목/시간/반복/타입/메모 등)
                keys.add("date")  # 렌더러가 선택일 date 를 add 액션에 자동 주입
            if isinstance(p.get("on"), dict):  # 뷰-이벤트 액션의 $lat/$lng/$id/$radius 등은 이벤트 페이로드가 주입
                keys.update(APP_EVENT_VARS)
            drill = p.get("item_click")
            if isinstance(drill, dict):
                from_compose(drill.get("compose"))
                walk(drill.get("view"))
                for tab in drill.get("tabs") or []:
                    if isinstance(tab, dict):
                        from_compose(tab.get("compose"))
                        walk(tab.get("view"))

    from_compose(blk.get("compose"))
    walk(blk.get("view"))
    return keys


def _check_compose_channels(where: str, cmp) -> list[str]:
    """compose.channels(발신 채널 선택) 스키마 검증 — from/type/value 필수, sendable 은 리스트."""
    issues: list[str] = []
    if not isinstance(cmp, dict):
        return issues
    ch = cmp.get("channels")
    if ch is None:
        return issues
    if not isinstance(ch, dict):
        issues.append(f"{where}: compose.channels 는 매핑")
        return issues
    for k in ("from", "type", "value"):
        if not isinstance(ch.get(k), str) or not ch.get(k):
            issues.append(f"{where}: compose.channels.{k}(필드명) 필수")
    if ch.get("sendable") is not None and not isinstance(ch.get("sendable"), list):
        issues.append(f"{where}: compose.channels.sendable 은 채널 타입 리스트")
    return issues


def _app_check_filter_block(where: str, blk: dict) -> list[str]:
    """app.filter 구조 검증 — 정적(items) 또는 동적(from_field) 둘 중 하나.
    items=재조회 칩([{label,value,default?}], 선택 시 $key 로 액션 재호출).
    from_field=클라이언트 측 결과-필드 동적 칩(distinct 값, 재조회 없이 items 거름). from=거를 배열 경로(기본 items)."""
    issues: list[str] = []
    f = blk.get("filter")
    if f is None:
        return issues
    if not isinstance(f, dict):
        issues.append(f"{where}: app.filter 는 매핑이어야 함")
        return issues
    has_items = isinstance(f.get("items"), list) and bool(f["items"])
    has_ff = isinstance(f.get("from_field"), str) and bool(f["from_field"])
    if not has_items and not has_ff:
        issues.append(f"{where}: app.filter 는 items(정적 칩) 또는 from_field(결과-필드 동적 칩) 필수")
    if has_items and has_ff:
        issues.append(f"{where}: app.filter 는 items 와 from_field 중 하나만(정적 vs 동적)")
    if f.get("from") is not None and not isinstance(f.get("from"), str):
        issues.append(f"{where}: app.filter.from 은 거를 배열 경로(문자열)")
    return issues


def _app_check_view(qualified: str, view, depth: int = 0, in_group: bool = False) -> list[str]:
    """view 프리미티브 배열 구조 검증 (드릴 뷰 재귀 포함).

    in_group=True 는 group 콤비네이터 내부 view — 원격 rowDrill 이 최상위 view[vi] 로만 항목을 찾아
    중첩 카드의 item_click 을 못 잇는다. 데스크탑만 되고 원격이 깨지는 드리프트를 막으려 item_click 금지
    (링크·버튼은 됨). group-내부-드릴이 필요해지면 원격 rowDrill 을 group 인지하게 고친 뒤 허용.
    """
    issues: list[str] = []
    if not isinstance(view, list) or not view:
        issues.append(f"{qualified}: app.view 는 비어있지 않은 리스트여야 함")
        return issues
    for i, p in enumerate(view):
        where = f"{qualified}: app.view[{i}]" + (" (드릴)" if depth else "")
        if not isinstance(p, dict):
            issues.append(f"{where} 가 매핑이 아님")
            continue
        ptype = p.get("type")
        if ptype not in APP_VIEW_TYPES:
            issues.append(f"{where}: 미지의 프리미티브 type={ptype!r} (어휘: {sorted(APP_VIEW_TYPES)})")
            continue
        if ptype in ("kv_list", "card_list", "image_grid", "sparkline", "list_action", "thread", "editable_list") and not p.get("from"):
            issues.append(f"{where}: {ptype} 는 from(데이터 경로) 필수")
        if ptype == "card_list" and not isinstance(p.get("card"), dict):
            issues.append(f"{where}: card_list 는 card 매핑 필수")
        if ptype == "thread" and not p.get("text"):
            issues.append(f"{where}: thread 는 text(버블 본문 템플릿) 필수")
        if ptype == "form":
            if not isinstance(p.get("action"), str):
                issues.append(f"{where}: form 은 action(저장 IBL 템플릿) 필수")
            fields = p.get("fields")
            if not isinstance(fields, list) or not fields:
                issues.append(f"{where}: form 은 fields(필드 리스트) 필수")
            else:
                for fi, f in enumerate(fields):
                    if not isinstance(f, dict) or not f.get("key"):
                        issues.append(f"{where}: form.fields[{fi}] key 필수")
                    elif f.get("type") not in APP_FORM_FIELD_TYPES:
                        issues.append(f"{where}: form.fields[{fi}] type={f.get('type')!r} (허용: {sorted(APP_FORM_FIELD_TYPES)})")
            # 보조 액션(즐겨찾기 토글·삭제 등) — label + action 필수, style 은 danger 만
            acts = p.get("actions")
            if acts is not None:
                if not isinstance(acts, list):
                    issues.append(f"{where}: form.actions 는 리스트")
                else:
                    for ai, a in enumerate(acts):
                        if not isinstance(a, dict) or not a.get("label") or not isinstance(a.get("action"), str):
                            issues.append(f"{where}: form.actions[{ai}] label·action(IBL 템플릿) 필수")
                        elif a.get("style") not in (None, "danger"):
                            issues.append(f"{where}: form.actions[{ai}] style={a.get('style')!r} (허용: danger)")
        if ptype == "group":
            # 파티션 콤비네이터 — from 리스트를 by 키로 나눠 그룹마다 내부 view 를 재귀 렌더(data={items: 멤버}).
            # table:groupby(집계)와 달리 멤버를 유지한다. 뷰-계층의 groupby. 내부 view 는 from:items 로 그룹 슬라이스 참조.
            if not isinstance(p.get("by"), str) or not p.get("by"):
                issues.append(f"{where}: group 은 by(파티션 키 템플릿, 예 '{{query}}') 필수")
            issues.extend(_app_check_view(qualified, p.get("view"), depth + 1, in_group=True))
        if ptype == "calendar":
            # 월 그리드 + 선택일 상세 + add.fields 폼(form 필드 어휘 재사용, date 자동주입). from=이벤트 리스트.
            if not p.get("from"):
                issues.append(f"{where}: calendar 는 from(이벤트 리스트 경로) 필수")
            add = p.get("add")
            if add is not None:
                if not isinstance(add, dict) or not isinstance(add.get("action"), str):
                    issues.append(f"{where}: calendar.add 는 action(IBL 템플릿) 필수")
                else:
                    for fi, f in enumerate(add.get("fields") or []):
                        if not isinstance(f, dict) or not f.get("key"):
                            issues.append(f"{where}: calendar.add.fields[{fi}] key 필수")
                        elif f.get("type") not in APP_FORM_FIELD_TYPES:
                            issues.append(f"{where}: calendar.add.fields[{fi}] type={f.get('type')!r} (허용: {sorted(APP_FORM_FIELD_TYPES)})")
            if p.get("delete_action") is not None and not isinstance(p.get("delete_action"), str):
                issues.append(f"{where}: calendar.delete_action 은 IBL 템플릿 문자열")
        if ptype == "editable_list":
            if not p.get("display"):
                issues.append(f"{where}: editable_list 는 display(행 표시 템플릿) 필수")
            add = p.get("add")
            if add is not None and (not isinstance(add, dict) or not isinstance(add.get("action"), str)):
                issues.append(f"{where}: editable_list.add 는 action(IBL 템플릿) 필수")
            if p.get("delete_action") is not None and not isinstance(p.get("delete_action"), str):
                issues.append(f"{where}: editable_list.delete_action 은 IBL 템플릿 문자열")
        if True in p or False in p:  # ★YAML 1.1 함정: 따옴표 없는 on/off/yes/no 키가 불리언으로 파싱됨
            issues.append(f"{where}: 불리언 키 발견 — 'on'(또는 off/yes/no) 키는 YAML 불리언으로 해석됨. 따옴표로 감싸세요('on':)")
        if "on" in p:  # 뷰-이벤트→액션 바인딩 — 현재 map 전용
            on = p.get("on")
            if ptype != "map":
                issues.append(f"{where}: on(뷰-이벤트) 은 map 전용")
            elif not isinstance(on, dict) or not on:
                issues.append(f"{where}: on 은 비어있지 않은 매핑(event→IBL 템플릿)")
            else:
                for ev, atpl in on.items():
                    if ev not in APP_VIEW_EVENTS:
                        issues.append(f"{where}: on 미지의 이벤트 {ev!r} (허용: {sorted(APP_VIEW_EVENTS)})")
                    # marker_click 은 IBL 템플릿(문자열·재조회) 또는 클라이언트 스트림 재생 {stream: true}(CCTV 영상 등) 둘 중 하나.
                    if ev == "marker_click" and isinstance(atpl, dict):
                        if atpl.get("stream") is not True or (set(atpl) - {"stream"}):
                            issues.append(f"{where}: on.marker_click 객체형은 {{stream: true}} 만 허용")
                    elif not isinstance(atpl, str) or not atpl:
                        issues.append(f"{where}: on.{ev} 은 IBL 액션 템플릿 문자열(또는 marker_click 의 {{stream: true}})")
        drill = p.get("item_click")
        if drill is not None:
            if in_group:
                issues.append(f"{where}: group 내부 view 는 item_click(드릴) 미지원 — 원격 rowDrill 제약. 링크(card.link)·버튼 사용")
            if ptype != "card_list":
                issues.append(f"{where}: item_click 은 card_list 전용")
            elif not isinstance(drill, dict) or not isinstance(drill.get("action"), str):
                issues.append(f"{where}: item_click 은 action 템플릿 필수")
            else:
                tabs = drill.get("tabs")
                if isinstance(tabs, list) and tabs:  # 상세 탭(대화/정보)
                    for ti, tab in enumerate(tabs):
                        if not isinstance(tab, dict) or not tab.get("name"):
                            issues.append(f"{where}: item_click.tabs[{ti}] name 필수")
                            continue
                        issues.extend(_app_check_view(qualified, tab.get("view"), depth + 1))
                        tcmp = tab.get("compose")
                        if tcmp is not None and (not isinstance(tcmp, dict) or not isinstance(tcmp.get("action"), str)):
                            issues.append(f"{where}: item_click.tabs[{ti}].compose 는 action 필수")
                        issues.extend(_check_compose_channels(where, tcmp))
                elif "tabs" in drill:
                    issues.append(f"{where}: item_click.tabs 는 비어있지 않은 리스트여야 함")
                else:
                    issues.extend(_app_check_view(qualified, drill.get("view"), depth + 1))
                    dcmp = drill.get("compose")
                    if dcmp is not None and (not isinstance(dcmp, dict) or not isinstance(dcmp.get("action"), str)):
                        issues.append(f"{where}: item_click.compose 는 action(IBL 템플릿) 필수")
                    issues.extend(_check_compose_channels(where, dcmp))
        # button/button2: list_action 은 {action} 행 버튼(2번째=즐겨찾기·다운로드 등). form/editable_list 의 button 은 라벨 문자열이라 제외.
        if ptype not in ("form", "editable_list"):
            for _bk in ("button", "button2"):
                btn = p.get(_bk)
                if btn is None:
                    continue
                # stream:true 버튼 = 클라이언트 측 스트림 재생 지시(StreamPlayer). 행 데이터(url/playable)를
                # 그대로 플레이어로 연다 — IBL action 없이 동작하므로 action 면제(CCTV '▶ 보기' 등).
                if isinstance(btn, dict) and btn.get("stream") is True:
                    continue
                if not isinstance(btn, dict) or not isinstance(btn.get("action"), str):
                    issues.append(f"{where}: {_bk} 은 action 템플릿 필수")
    return issues


def _app_check_filters(qualified: str, app: dict) -> list[str]:
    """표시 템플릿 '{path|filter}' 의 필터 오타 검출."""
    import re
    issues: list[str] = []
    strings: list[str] = []

    def walk(o):
        if isinstance(o, str):
            strings.append(o)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)

    walk(app.get("view"))
    for m in app.get("modes") or []:          # 명시적 modes 각 탭의 view 도 검사
        if isinstance(m, dict):
            walk(m.get("view"))
    for s in strings:
        for expr in re.findall(r"\{([^{}]+)\}", s):
            for f in [x.strip() for x in expr.split("|")[1:]]:
                if f in APP_TPL_FILTERS or f.startswith("opt:") or f.startswith("trunc:"):
                    continue
                issues.append(f"{qualified}: 미지의 템플릿 필터 {f!r} (in {s!r})")
    return issues


def _validate_app_block(blabel: str, blk: dict, qualified_set: set) -> list[str]:
    """단일 앱 블록(탭 또는 단독 계기) 검증 — 노드 app: 블록과 standalone 매니페스트 공용.

    action(IBL 템플릿) 필수 · view 어휘 · compose · inputs(key/type/select) ·
    템플릿의 [node:action] 실존 · $key↔inputs 대응.
    """
    import re
    issues: list[str] = []
    if not isinstance(blk.get("action"), str) and not blk.get("buttons"):
        issues.append(f"{blabel}: app.action(IBL 템플릿) 또는 buttons 필수")
    # action 있는 블록은 결과를 그릴 view 필수. 버튼 전용(action 없음)은 그릴 데이터가
    # 없어 view 생략 가능 — 단 view 를 선언했으면 구조는 검증한다.
    _view = blk.get("view")
    if isinstance(blk.get("action"), str) or _view is not None:
        issues.extend(_app_check_view(blabel, _view))
    _cmp = blk.get("compose")
    if _cmp is not None and (not isinstance(_cmp, dict) or not isinstance(_cmp.get("action"), str)):
        issues.append(f"{blabel}: app.compose 는 action(IBL 템플릿) 필수")
    issues.extend(_check_compose_channels(blabel, _cmp))
    input_keys: set = set()
    input_keys |= _block_local_keys(blk)
    issues.extend(_app_check_filter_block(blabel, blk))
    _pd = blk.get("filter")
    if isinstance(_pd, dict) and not _pd.get("from_field"):
        input_keys.add(_pd.get("key") or "filter")
    for j, inp in enumerate(blk.get("inputs") or []):
        if not isinstance(inp, dict) or not inp.get("key"):
            issues.append(f"{blabel}: app.inputs[{j}] 에 key 없음")
            continue
        input_keys.add(inp["key"])
        itype = inp.get("type")
        if itype not in APP_INPUT_TYPES:
            issues.append(f"{blabel}: app.inputs[{j}] type={itype!r} (허용: {sorted(APP_INPUT_TYPES)})")
        if itype == "select":
            if inp.get("options"):
                opts = inp["options"]
                if not isinstance(opts, list) or not all(
                    isinstance(o, dict) and "value" in o and "label" in o for o in opts
                ):
                    issues.append(f"{blabel}: app.inputs[{j}] 정적 options 는 [{{value,label}}] 배열")
            elif inp.get("options_action"):
                if not inp.get("options_from"):
                    issues.append(f"{blabel}: app.inputs[{j}] select options_action 에 options_from 필수")
            else:
                issues.append(f"{blabel}: app.inputs[{j}] select 는 정적 options 또는 options_action 필수")
    for t in _app_action_templates(blk):
        for ref_node, ref_action in re.findall(r"\[(\w+):(\w+)\]", t):
            if f"{ref_node}:{ref_action}" not in qualified_set:
                issues.append(f"{blabel}: app 템플릿이 미존재 액션 [{ref_node}:{ref_action}] 참조 ({t!r})")
        for key in re.findall(r"\$(\w+)", t):
            if key not in input_keys:
                issues.append(f"{blabel}: app 템플릿 $%s 에 대응하는 input 없음 ({t!r})" % key)
    return issues


def validate_standalone_instruments(data: dict) -> list[str]:
    """data/instruments/*.yaml (어휘 없는 순수 앱) 검증 — 노드 app: 블록과 같은 어휘.

    각 파일은 하나의 계기: instrument/icon/name 필수 + 각 모드가 앱 블록.
    모드 action: 의 [node:action] 이 실존하는지 검사 → 앱→어휘 참조 깨짐을 저술 시점에 잡음.
    """
    import glob
    import os
    import re
    import yaml
    issues: list[str] = []
    inst_dir = os.path.join(os.path.dirname(__file__), "..", "data", "instruments")
    if not os.path.isdir(inst_dir):
        return issues
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    qualified_set = {
        f"{n}:{a}"
        for n, nd in nodes.items() if isinstance(nd, dict)
        for a in (nd.get("actions") or {})
    }
    for fp in sorted(glob.glob(os.path.join(inst_dir, "*.yaml"))):
        name = os.path.basename(fp)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                m = yaml.safe_load(f) or {}
        except Exception as e:  # noqa: BLE001
            issues.append(f"instruments/{name}: YAML 파싱 실패 — {e}")
            continue
        if not isinstance(m, dict):
            issues.append(f"instruments/{name}: 매핑이어야 함")
            continue
        for req in ("instrument", "icon", "name"):
            if not m.get(req):
                issues.append(f"instruments/{name}: {req} 필수")
        # %BASE% 는 서버측 치환 토큰이라 검증 시엔 그대로 둔 채 [node:action]·$key 만 본다.
        modes = m.get("modes")
        if isinstance(modes, list) and modes:
            for mi, mode in enumerate(modes):
                if not isinstance(mode, dict):
                    issues.append(f"instruments/{name}: modes[{mi}] 가 매핑이 아님")
                    continue
                if not mode.get("name"):
                    issues.append(f"instruments/{name}: modes[{mi}] name(탭 이름) 필수")
                issues.extend(_validate_app_block(f"instruments/{name} modes[{mi}]", mode, qualified_set))
        else:
            issues.append(f"instruments/{name}: modes(비어있지 않은 리스트) 필수")
    return issues


def validate_app_blocks(data: dict) -> list[str]:
    """app: 블록 정합성 — 액션 템플릿의 [node:action] 실존, $key↔inputs, view 어휘, 계기 그룹."""
    import re
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    qualified_set = {
        f"{n}:{a}"
        for n, nd in nodes.items() if isinstance(nd, dict)
        for a in (nd.get("actions") or {})
    }
    groups: dict[str, list[tuple[str, dict]]] = {}

    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict) or "app" not in action:
                continue
            qualified = f"{node_name}:{action_name}"
            app = action["app"]
            if not isinstance(app, dict):
                issues.append(f"{qualified}: app 은 매핑이어야 함")
                continue

            unknown = set(app.keys()) - APP_KEYS
            if unknown:
                issues.append(f"{qualified}: app 미지의 키 {sorted(unknown)} (허용: {sorted(APP_KEYS)})")

            # io(action/view/inputs/템플릿)는 블록 단위로 검증.
            # 명시적 modes(탭)면 각 탭이 독립 블록, 아니면 app 자신이 단일 블록.
            mode_list = app.get("modes")
            if isinstance(mode_list, list) and mode_list:
                blocks: list[tuple[str, dict]] = []
                for mi, m in enumerate(mode_list):
                    if not isinstance(m, dict):
                        issues.append(f"{qualified}: app.modes[{mi}] 가 매핑이 아님")
                        continue
                    if not m.get("name"):
                        issues.append(f"{qualified}: app.modes[{mi}] name(탭 이름) 필수")
                    blocks.append((f"{qualified} modes[{mi}]", m))
            elif "modes" in app:
                issues.append(f"{qualified}: app.modes 는 비어있지 않은 리스트여야 함")
                blocks = []
            else:
                blocks = [(qualified, app)]

            for blabel, blk in blocks:
                issues.extend(_validate_app_block(blabel, blk, qualified_set))

            issues.extend(_app_check_filters(qualified, app))

            gid = app.get("instrument") or action_name
            groups.setdefault(gid, []).append((qualified, app))

    # 계기 그룹 정합
    for gid, members in groups.items():
        partial = [q for q, a in members if bool(a.get("icon")) != bool(a.get("name"))]
        if partial:
            issues.append(f"계기 {gid!r}: icon/name 은 함께 선언해야 함 — 반쪽 선언 {partial}")
        primaries = [q for q, a in members if a.get("icon") and a.get("name")]
        if len(members) == 1:
            q, a = members[0]
            if not (a.get("icon") and a.get("name")):
                issues.append(f"{q}: 단독 계기 {gid!r} 는 icon+name 필수")
        else:
            if len(primaries) != 1:
                issues.append(
                    f"계기 {gid!r}: icon+name 선언 멤버(primary)가 정확히 1개여야 함 (현재 {len(primaries)}: {primaries})"
                )
            no_mode = [q for q, a in members if not a.get("mode")]
            if no_mode:
                issues.append(f"계기 {gid!r}: 복수 멤버는 전원 mode(탭 이름) 필수 — 누락 {no_mode}")
            mode_names = [a.get("mode") for _, a in members if a.get("mode")]
            if len(mode_names) != len(set(mode_names)):
                issues.append(f"계기 {gid!r}: mode 이름 중복 {mode_names}")
    return issues


# === runs_on 검증 + 폰 매니페스트 파생 (2026-06-11, #3) ===

def validate_runs_on(data: dict) -> list[str]:
    """모든 액션의 runs_on 값이 유효 enum 인지 검사 (미지정=anywhere 허용)."""
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            ro = action.get("runs_on")
            if ro is not None and ro not in VALID_RUNS_ON:
                issues.append(
                    f"{node_name}:{action_name} — 잘못된 runs_on '{ro}' "
                    f"(허용: {', '.join(sorted(VALID_RUNS_ON))})"
                )
    return issues


def validate_transform_contract(data: dict) -> list[str]:
    """통화 변환자(group: transform) 계약 강제 — 닫힌-계급 문법/superstructure.

    변환자(filter/sort/groupby/join…)는 통화→통화 순수 함수다 — 몸 무관, 외부 자원 없음.
    *이름*(현재 engines:)이 아니라 **group 태그가 닫힌 계급의 단일 마커**다(설계 결정:
    비싼 노드 이전 대신 태그를 load-bearing 으로 — docs/ibl_design_philosophy.md). 계약:
      - scope: workspace  — 무프로젝트 파이프에서도 돌아야(project 기본이면 0ms 즉시 실패: 과거 버그)
      - runs_on: anywhere — 통화는 몸 무관(폰-로컬 통화도 그 몸에서 거르고 정렬)
    새 변환자가 이 계약을 빠뜨리면 침묵-실패가 재발 → 여기서 구조로 막는다.
    """
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict) or action.get("group") != "transform":
                continue
            q = f"{node_name}:{action_name}"
            if action.get("scope") != "workspace":
                issues.append(
                    f"{q} — 변환자(group:transform)는 scope: workspace 필수 "
                    f"(현재 '{action.get('scope') or '없음=project기본'}'). "
                    f"무프로젝트 파이프서 즉시 실패 방지."
                )
            if action.get("runs_on") != "anywhere":
                issues.append(
                    f"{q} — 변환자는 runs_on: anywhere 필수 "
                    f"(현재 '{action.get('runs_on') or '없음'}'). 통화는 몸 무관."
                )
    return issues


def validate_phone_reachability(data: dict, root: Path) -> list[str]:
    """runs_on 정직성: anywhere(기본) 액션인데 handler/driver 패키지가 PHONE_VERIFIED 가 아니면
    적발. 그런 액션은 폰서 _phone_runnable=False → 조용히 _forward_to_mac 된다(ibl_engine.py).
    즉 anywhere 와 mac_only 가 폰에서 행동이 같아 태그가 거짓 → silent-forward 라 self-check 가
    못 잡던 부류. 해소: 패키지를 PHONE_VERIFIED 에 넣거나(폰 로컬 실행) 액션에 runs_on: mac_only
    명시(맥 포워드 명시). 비-패키지(system/engine 등) 액션은 대상 아님(번들 모듈로 폰서 실행)."""
    issues: list[str] = []
    tool_index = build_tool_index(root)
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            ro = action.get("runs_on", DEFAULT_RUNS_ON)
            if ro != "anywhere":
                continue  # mac_only/phone_only = 명시적(정직)
            tool = action.get("tool")
            if not tool or tool not in tool_index:
                continue  # 비-패키지 액션(system/engine 등) — 번들 모듈로 폰 실행
            pkg = tool_index[tool][0].name
            if pkg not in PHONE_VERIFIED_PACKAGES:
                issues.append(
                    f"{node_name}:{action_name} — runs_on=anywhere 인데 패키지 '{pkg}' 폰 미검증 "
                    f"→ 폰서 조용히 맥 포워드(태그 거짓). 패키지를 PHONE_VERIFIED_PACKAGES 에 넣거나 "
                    f"액션에 'runs_on: mac_only' 명시."
                )
    return issues


def derive_phone_manifest(data: dict, root: Path) -> dict:
    """runs_on + 검증된 폰 패키지 → 폰 프로파일 매니페스트.

    runnable_actions(폰서 실행 가능):
      - runs_on == phone_only  → 폰 전용 하드웨어 액션(항상 포함)
      - runs_on == mac_only   → 제외
      - runs_on == anywhere(기본):
          · handler/driver 라우터(패키지 보유) → 패키지가 PHONE_VERIFIED 일 때만
          · 비-패키지(system/engine 등) → 기본 포함(mac_only 로 명시 태그 안 한 한)
    packages: 폰에 번들할 패키지 = PHONE_VERIFIED (Gradle 이 읽음).
    """
    tool_index = build_tool_index(root)
    runnable: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            ro = action.get("runs_on", DEFAULT_RUNS_ON)
            if ro == "mac_only":
                continue
            if ro == "phone_only":
                runnable.append(qualified)
                continue
            # anywhere
            tool = action.get("tool")
            pkg = None
            if tool and tool in tool_index:
                pkg = tool_index[tool][0].name
            if pkg is None:
                runnable.append(qualified)          # 비-패키지 액션: 기본 폰가능
            elif pkg in PHONE_VERIFIED_PACKAGES:
                runnable.append(qualified)          # 검증된 폰 패키지
            # else: 미검증 패키지 → 폰서 제외
    return {
        "_comment": "GENERATED by build_ibl_nodes.py — 폰 프로파일(어디서 도는가) 단일 진실 소스. 직접 수정 금지.",
        "packages": sorted(PHONE_VERIFIED_PACKAGES),
        "runnable_actions": sorted(runnable),
    }


def derive_fixtures(data: dict) -> dict:
    """병합된 data 에서 액션별 fixture/exempt 필드를 모아 ibl_fixtures.json 을 파생.

    fixture 는 이제 각 액션 정의(패키지 ibl_actions.yaml / 코어 ibl_nodes_src)에
    `fixture:`(올바른 파라미터 예 하나)·`exempt:`(실행 인자 의존 — 사유) 필드로 산다
    — returns/ops/tool 같은 다른 액션 메타와 동형. *설치된* 어휘에서만 파생되므로
    패키지 제거 → 재빌드 하면 그 fixture 도 함께 빠진다(고아 fixture 문제가 구조적으로
    소멸 — 별도 orphan 검사 불필요). ibl_health_check.py 가 이 파생물을 읽어 통화를 단언한다.
    """
    fixtures: dict = {}
    exempt: dict = {}
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            qual = f"{node_name}:{action_name}"
            if action.get("fixture"):
                fixtures[qual] = action["fixture"]
            elif action.get("exempt"):
                exempt[qual] = action["exempt"]
    return {
        "_comment": (
            "GENERATED by build_ibl_nodes.py — 각 액션의 fixture:/exempt: 필드에서 파생. "
            "직접 수정 금지(소스=패키지 ibl_actions.yaml / 코어 ibl_nodes_src). "
            "ibl_health_check.py 가 읽는다."
        ),
        "fixtures": dict(sorted(fixtures.items())),
        "exempt": dict(sorted(exempt.items())),
    }


def validate_fixture_coverage(data: dict, root: Path) -> list[str]:
    """행동 건강 fixture 완전성 강제 — 신규 액션이 건강검사망을 빠져나갈 수 없게.

    실행 가능한(returns: items|scalar) 액션은 자기 정의에 `fixture:`(올바른 파라미터
    예 하나) 또는 `exempt:`(실행 인자 의존 — 사유) 필드를 반드시 가져야 한다.
    effect(부작용 — 실행 불가)·transform(골든파이프로 흐름검증)은 면제.

    필드는 액션이 사는 소스(패키지 ibl_actions.yaml / 코어 ibl_nodes_src)에 두고,
    build 가 ibl_fixtures.json 으로 파생한다. 파생물이라 *고아 fixture 는 구조적으로
    없다*(과거의 별도 orphan 검사 불필요). 이로써 "어휘를 만들면 fixture 한 줄도 같이"가
    권고가 아니라 커밋 게이트가 되고(new_action_checklist.md), 제거는 재빌드만으로
    fixture 가 함께 빠진다(action_removal.md).
    """
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            if action.get("returns") in ("items", "scalar"):
                if not action.get("fixture") and not action.get("exempt"):
                    issues.append(
                        f"{node_name}:{action_name}: returns:items|scalar 인데 "
                        f"fixture/exempt 필드 없음 — 액션 정의(패키지 ibl_actions.yaml "
                        f"또는 ibl_nodes_src)에 `fixture: '[...]'` 한 줄 추가 "
                        f"(실행 인자 의존이면 `exempt: '<사유>'`)"
                    )
    return issues


def validate(data: dict, root: Path) -> list[str]:
    """전체 yaml 데이터에 대해 삼각 검증 수행."""
    issues: list[str] = []
    tool_index = build_tool_index(root)
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        actions = node.get("actions", {}) or {}
        for action_name, action in actions.items():
            if not isinstance(action, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            issues.extend(_check_action(qualified, action, tool_index))
    issues.extend(validate_app_blocks(data))
    issues.extend(validate_standalone_instruments(data))
    issues.extend(validate_runs_on(data))
    issues.extend(validate_transform_contract(data))
    issues.extend(validate_phone_reachability(data, root))
    return issues


# === 능력 자기완결화 (Phase 0): 설치된 패키지의 어휘 fragment 병합 ===
# 각 패키지가 자기 폴더에 `ibl_actions.yaml`({node, actions})을 두면 빌드가 흡수한다.
# 설치된 fragment 가 하나도 없으면 출력은 기존 텍스트와 바이트 동일(안전 착지).
# 형식 템플릿: data/packages/not_installed/tools/house-designer/ibl_actions.yaml

def collect_package_fragments(root: Path, yaml_mod) -> tuple[list, list]:
    """설치된 패키지들의 ibl_actions.yaml 수집.

    반환: (fragments, issues)
      fragments = [(pkg_name, node, actions_dict), ...]
      issues    = 형식 오류 메시지 리스트
    """
    fragments: list = []
    issues: list = []
    for rel in PACKAGE_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for pkg_dir in sorted(base.iterdir()):
            frag = pkg_dir / "ibl_actions.yaml"
            if not frag.is_file():
                continue
            try:
                doc = yaml_mod.safe_load(frag.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                issues.append(f"{pkg_dir.name}/ibl_actions.yaml 파싱 실패: {e}")
                continue
            if not isinstance(doc, dict):
                issues.append(f"{pkg_dir.name}/ibl_actions.yaml: 최상위가 매핑이 아님")
                continue
            # 형식 A(단일 노드): {node: <name>, actions: {...}}
            # 형식 B(다중 노드): {nodes: {<node>: {actions: {...}}, ...}}  ← radio 등 노드 걸침
            if isinstance(doc.get("nodes"), dict):
                any_ok = False
                for node, ndef in doc["nodes"].items():
                    actions = ndef.get("actions") if isinstance(ndef, dict) else None
                    if not isinstance(actions, dict):
                        issues.append(
                            f"{pkg_dir.name}/ibl_actions.yaml: nodes.{node}.actions 매핑 필요"
                        )
                        continue
                    fragments.append((pkg_dir.name, node, actions))
                    any_ok = True
                if not any_ok:
                    issues.append(
                        f"{pkg_dir.name}/ibl_actions.yaml: nodes 아래 유효 액션 없음"
                    )
            else:
                node = doc.get("node")
                actions = doc.get("actions")
                if not node or not isinstance(actions, dict):
                    issues.append(
                        f"{pkg_dir.name}/ibl_actions.yaml: 'node'+'actions' 또는 'nodes' 필수"
                    )
                    continue
                fragments.append((pkg_dir.name, node, actions))
    return fragments, issues


def collect_dormant_package_qualifiers(root: Path, yaml_mod) -> set[str]:
    """not_installed 패키지들의 ibl_actions.yaml에서 소유 액션 qualifier(node:action) 집합.

    부재-패키지 관용(Phase 4): "철거됐을 뿐 정의는 실존하는" 액션과 "정의 자체가
    사라진 진짜 좀비"를 구분하는 판별 집합. best-effort — 형식 오류는 조용히 건너뛴다
    (dormant 패키지의 fragment 오류는 --check 실패 사유가 아니다, 재설치 시 그때 걸린다).
    """
    quals: set[str] = set()
    for rel in NOT_INSTALLED_PACKAGE_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for pkg_dir in sorted(base.iterdir()):
            frag = pkg_dir / "ibl_actions.yaml"
            if not frag.is_file():
                continue
            try:
                doc = yaml_mod.safe_load(frag.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(doc, dict):
                continue
            if isinstance(doc.get("nodes"), dict):
                for node, ndef in doc["nodes"].items():
                    actions = ndef.get("actions") if isinstance(ndef, dict) else None
                    if isinstance(actions, dict):
                        quals.update(f"{node}:{a}" for a in actions)
            else:
                node = doc.get("node")
                actions = doc.get("actions")
                if node and isinstance(actions, dict):
                    quals.update(f"{node}:{a}" for a in actions)
    return quals


# === 능력 메타 자동 도출 (Phase 4, 2026-07-01) ===
# 패키지별 needs_key/weight/locale을 손수 유지하는 어노테이션이 아니라 코드에서 직접
# 스캔해 도출한다 — 단일 진실 소스는 항상 코드(핸들러 자신)이지 사람이 손으로 미러링한
# 메타데이터가 아니다(드리프트 방지, docs/CAPABILITY_SELF_CONTAINMENT_PLAN.md Phase 4).
_KEY_ENV_SUFFIX_RE = re.compile(
    r"^[A-Z][A-Z0-9_]*_(?:API_KEY|API_TOKEN|TOKEN|API_SECRET|SECRET|CLIENT_ID|CLIENT_SECRET|ACCOUNT_ID)$"
)
_DIRECT_ENV_CALL_RE = re.compile(
    r'(?:os\.environ\.get|os\.getenv|get_api_key)\(\s*["\']([A-Z0-9_]+)["\']'
)
_CHECK_API_KEY_RE = re.compile(r'check_api_key\(\s*["\']([a-z0-9_]+)["\']')

# 시스템/런타임 경로 변수 — API 키가 아니므로 needs_key에서 제외.
_META_KEY_EXCLUDE_ENV_VARS = {
    "INDIEBIZ_PROFILE", "INDIEBIZ_USERDATA", "INDIEBIZ_NODE_PATH",
    "INDIEBIZ_RUNTIME_PATH", "INDIEBIZ_PYTHON_PATH",
}
# auth_manager._AUTH_REGISTRY 서비스 중 한국 공식/상용 API로 잠긴 것 (locale:kr 판정 근거).
_KR_LOCKED_AUTH_SERVICES = {
    "kakao", "naver", "law", "dart", "kosis", "data_go_kr", "molit",
    "kopis", "data4library", "nanet",
}
# 레지스트리 밖 직접 env var 중 KR 확정분(교통정보 등 한국 전용 공공 API).
_KR_LOCKED_ENV_VARS = {"ITS_API_KEY", "UTIC_API_KEY"}
# 무거운 의존성(브라우저 자동화·CV·GUI 자동화·영상/TTS 처리) — 표준=keyless∧universal∧light
# 프리셋(Phase 5)의 "light" 판정 근거.
_HEAVY_DEP_MARKERS = (
    "playwright", "moviepy", "cv2", "torch", "whisper", "selenium",
    "pyautogui", "edge_tts", "remotion",
)


def _registry_env_vars(auth_config: dict) -> set[str]:
    """auth_manager._AUTH_REGISTRY 항목 하나에서 env var 이름(들) 추출."""
    t = auth_config.get("type")
    if t in ("header", "query_param"):
        v = auth_config.get("env_var")
        return {v} if v else set()
    if t == "header_pair":
        return set(auth_config.get("headers", {}).values())
    if t == "oauth2":
        return set(auth_config.get("env_vars", {}).values())
    return set()


def _load_auth_registry(root: Path) -> dict:
    """backend/common/auth_manager.py 의 _AUTH_REGISTRY 재사용 — 매핑을 복제하지 않고
    단일 소스를 그대로 import(KR-lock 서비스가 그쪽에서 바뀌면 이쪽도 즉시 정합)."""
    import sys as _sys
    backend_dir = str(root / "backend")
    added = backend_dir not in _sys.path
    if added:
        _sys.path.insert(0, backend_dir)
    try:
        from common.auth_manager import _AUTH_REGISTRY  # type: ignore
        return dict(_AUTH_REGISTRY)
    except Exception:  # noqa: BLE001
        return {}
    finally:
        if added:
            _sys.path.remove(backend_dir)


def derive_package_meta(root: Path, package_dirs=None) -> dict:
    """설치된 각 패키지의 needs_key/weight/locale을 .py 코드 스캔으로 자동 도출 +
    action_owner(어느 액션이 어느 패키지 소유인지)까지 함께 산출 — 런타임(ibl_access.py)이
    "이 액션은 needs_key가 있는데 env var가 없다"를 판정하려면 qualifier→패키지 역참조가
    필요한데, 그 원천은 collect_package_fragments가 이미 갖고 있어 재사용한다(중복 스캔 방지 X,
    fragment 자체는 작아서 재파싱 비용은 무시 가능 — 대신 단일 진실 소스 유지가 이득).

    package_dirs: 스캔할 패키지 루트 목록(root 상대). None이면 PACKAGE_DIRS(installed).
      apply_edition.py 가 not_installed 팩의 메타까지 필요할 때 확장 목록을 넘긴다.
      action_owner 는 항상 installed 기준(collect_package_fragments)이라 이 인자와 무관.

    반환: {
      "packages": {pkg_name: {needs_key: [env_var,...], weight: light|heavy, locale: kr|universal}},
      "action_owner": {"node:action": pkg_name, ...},
    } (양쪽 다 알파벳순 정렬, 결정적).
    """
    registry = _load_auth_registry(root)
    # KR-locked env var 전체 집합 = 직접 확정분 ∪ KR 서비스가 요구하는 env var들.
    kr_env_vars = set(_KR_LOCKED_ENV_VARS)
    for svc in _KR_LOCKED_AUTH_SERVICES:
        cfg = registry.get(svc)
        if cfg:
            kr_env_vars |= _registry_env_vars(cfg)

    result: dict[str, dict] = {}
    for rel in (package_dirs or PACKAGE_DIRS):
        base = root / rel
        if not base.is_dir():
            continue
        for pkg_dir in sorted(base.iterdir()):
            if not pkg_dir.is_dir():
                continue
            py_files = list(pkg_dir.rglob("*.py"))
            if not py_files:
                continue
            needs_key: set[str] = set()
            kr_hit = False
            heavy = False
            for f in py_files:
                try:
                    text = f.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for m in _DIRECT_ENV_CALL_RE.finditer(text):
                    name = m.group(1)
                    if name in _META_KEY_EXCLUDE_ENV_VARS or not _KEY_ENV_SUFFIX_RE.match(name):
                        continue
                    needs_key.add(name)
                    if name in kr_env_vars:
                        kr_hit = True
                for m in _CHECK_API_KEY_RE.finditer(text):
                    svc = m.group(1)
                    cfg = registry.get(svc)
                    if cfg:
                        needs_key.update(_registry_env_vars(cfg))
                        if svc in _KR_LOCKED_AUTH_SERVICES:
                            kr_hit = True
                if any(marker in text for marker in _HEAVY_DEP_MARKERS):
                    heavy = True
            result[pkg_dir.name] = {
                "needs_key": sorted(needs_key),
                "weight": "heavy" if heavy else "light",
                "locale": "kr" if kr_hit else "universal",
            }

    action_owner: dict[str, str] = {}
    try:
        import yaml as _yaml_for_meta
    except ImportError:
        _yaml_for_meta = None
    if _yaml_for_meta is not None:
        fragments, _frag_issues = collect_package_fragments(root, _yaml_for_meta)
        for pkg_name, node, actions in fragments:
            for aname in actions:
                action_owner[f"{node}:{aname}"] = pkg_name

    return {
        "packages": dict(sorted(result.items())),
        "action_owner": dict(sorted(action_owner.items())),
    }


def merge_fragments(data: dict, fragments: list) -> list:
    """fragments 를 data['nodes'][node]['actions'] 에 병합(data 변경). 반환: 충돌/오류 issues."""
    issues: list = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for pkg_name, node, actions in fragments:
        node_def = nodes.get(node)
        if not isinstance(node_def, dict):
            issues.append(f"{pkg_name}: 알 수 없는 노드 '{node}'")
            continue
        # 노드의 모든 액션이 이관되면 중앙 src엔 `actions:`가 빈 값(None)으로 남는다 —
        # setdefault는 기존 키가 None이어도 덮어쓰지 않으므로 명시적으로 정규화한다.
        node_actions = node_def.get("actions")
        if node_actions is None:
            node_actions = {}
            node_def["actions"] = node_actions
        for aname, adef in actions.items():
            if aname in node_actions:
                issues.append(
                    f"{pkg_name}: 어휘 충돌 '{node}:{aname}' — 코어/타 패키지에 이미 존재"
                )
                continue
            node_actions[aname] = adef
    return issues


def serialize_nodes_document(header: str, data: dict, yaml_mod) -> str:
    """병합된 data 를 ibl_nodes.yaml 텍스트로 재직렬화 (fragment 존재 시에만 사용)."""
    body = yaml_mod.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1 << 20,
    )
    return header + body


def build(check: bool = False, validate_only: bool = False) -> int:
    root = repo_root()
    src_dir = root / "data" / "ibl_nodes_src"
    target = root / "data" / "ibl_nodes.yaml"

    if not src_dir.is_dir():
        print(f"[build_ibl_nodes] 소스 디렉토리 없음: {src_dir}", file=sys.stderr)
        return 2

    header = (
        "# GENERATED — DO NOT EDIT\n"
        "# Source : data/ibl_nodes_src/{meta,sense,self,limbs,others,engines,table}.yaml\n"
        "# Rebuild: python3 scripts/build_ibl_nodes.py\n"
        "# Check  : python3 scripts/build_ibl_nodes.py --check\n"
        "\n"
    )
    parts: list[str] = [header]

    meta_path = src_dir / "meta.yaml"
    if not meta_path.is_file():
        print(f"[build_ibl_nodes] 누락: {meta_path}", file=sys.stderr)
        return 2
    parts.append(meta_path.read_text(encoding="utf-8"))

    # `nodes:` 헤더를 명시적으로 삽입 (소스 파일 어디에도 두지 않는다).
    parts.append("nodes:\n")

    for node in NODE_ORDER:
        node_path = src_dir / f"{node}.yaml"
        if not node_path.is_file():
            print(f"[build_ibl_nodes] 누락: {node_path}", file=sys.stderr)
            return 2
        parts.append(node_path.read_text(encoding="utf-8"))

    merged = "".join(parts)

    # YAML 파싱으로 sanity check — 노드/액션 수가 정상인지 + 검증.
    try:
        import yaml as _yaml
    except ImportError:
        print(
            "[build_ibl_nodes] PyYAML 없음 — 검증 건너뜀 (sanity check 불가)",
            file=sys.stderr,
        )
        _yaml = None

    data: dict | None = None
    output = merged          # 기본: 설치된 fragment 가 없으면 바이트 동일(안전 착지)
    frag_issues: list = []
    if _yaml is not None:
        data = _yaml.safe_load(merged)
        # --- 설치된 패키지 어휘 fragment 병합 (Phase 0) ---
        fragments, collect_issues = collect_package_fragments(root, _yaml)
        merge_issues = merge_fragments(data, fragments) if fragments else []
        frag_issues = collect_issues + merge_issues
        frag_action_n = sum(len(a) for _, _, a in fragments)
        if fragments and not frag_issues:
            # fragment 가 있고 병합 성공 시에만 재직렬화(그 외엔 기존 텍스트 유지).
            output = serialize_nodes_document(header, data, _yaml)
        nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
        total_actions = sum(
            len(n.get("actions") or {}) for n in nodes.values() if isinstance(n, dict)
        )
        extra = (
            f", 패키지 fragment {len(fragments)}개(+{frag_action_n} 액션)"
            if fragments else ""
        )
        print(
            f"[build_ibl_nodes] 노드 {len(nodes)}개, 액션 {total_actions}개{extra} "
            f"({sum(1 for _ in output.splitlines())}줄, {len(output.encode('utf-8'))}바이트)"
        )

    # --- 삼각 검증 ---
    validation_failed = False
    if data is not None:
        issues = frag_issues + validate(data, root)
        if issues:
            validation_failed = True
            print(
                f"[build_ibl_nodes] 검증 실패: {len(issues)}건",
                file=sys.stderr,
            )
            for issue in issues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 검증 통과 ✓ (등록·op enum·default·handler 분기)")

    # --- 코퍼스 param 정합 검사 (--check/--validate 전용) ---
    # 코퍼스 드리프트가 평소 yaml 빌드를 막지 않도록, 게이트(check/validate)에서만 평가.
    corpus_failed = False
    if data is not None and (check or validate_only):
        cissues = validate_corpus_params(data, root)
        if cissues is None:
            print(
                "[build_ibl_nodes] 코퍼스/파서 미가용 — param 정합 검사 건너뜀",
                file=sys.stderr,
            )
        elif cissues:
            corpus_failed = True
            print(
                f"[build_ibl_nodes] 코퍼스 param 정합 실패: {len(cissues)}건",
                file=sys.stderr,
            )
            for issue in cissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 코퍼스 param 정합 통과 ✓")

    # --- 행동 건강 fixture 완전성 (--check/--validate 전용) ---
    # 실행 가능한(items/scalar) 액션은 ibl_fixtures.json 에 fixture 또는 exempt 가 있어야 한다.
    # 신규 어휘가 건강검사망을 조용히 빠져나가는 걸 *커밋 게이트*로 막는다.
    fixture_failed = False
    if data is not None and (check or validate_only):
        xissues = validate_fixture_coverage(data, root)
        if xissues:
            fixture_failed = True
            print(
                f"[build_ibl_nodes] fixture 완전성 실패: {len(xissues)}건 "
                f"(items/scalar 액션은 data/ibl_fixtures.json 에 fixture 또는 exempt 필수)",
                file=sys.stderr,
            )
            for issue in xissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] fixture 완전성 통과 ✓ (모든 items/scalar 액션이 fixture/exempt 보유)")

    # --- 포크-가드: INDIEBIZ_PROFILE 분기 위치 (--check/--validate 전용) ---
    profile_failed = False
    if check or validate_only:
        pissues = check_profile_branches(root)
        if pissues:
            profile_failed = True
            print(
                f"[build_ibl_nodes] 포크-가드 실패: {len(pissues)}건 "
                f"(이음매 위 INDIEBIZ_PROFILE 분기)",
                file=sys.stderr,
            )
            for issue in pissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print(
                f"[build_ibl_nodes] 포크-가드 통과 ✓ "
                f"(INDIEBIZ_PROFILE 분기 {len(PROFILE_BRANCH_ALLOWLIST)}개, 전부 이음매 아래)"
            )

    # --- OS-가드: platform/유닉스-바이너리 의존 위치 (--check/--validate 전용) ---
    os_failed = False
    if check or validate_only:
        oissues = check_os_branches(root)
        if oissues:
            os_failed = True
            print(
                f"[build_ibl_nodes] OS-가드 실패: {len(oissues)}건 "
                f"(몸 독립 코어에 OS 의존)",
                file=sys.stderr,
            )
            for issue in oissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print(
                f"[build_ibl_nodes] OS-가드 통과 ✓ "
                f"(OS 이음매 {len(OS_SEAM_ALLOWLIST)}개 파일 — 윈도우/리눅스 이식 점검 대상)"
            )

    # --- launcher-가드: 어휘→라우터→main.js 핸들러 계약 (--check/--validate 전용) ---
    launcher_failed = False
    if check or validate_only:
        lissues = check_launcher_handlers(root)
        if lissues:
            launcher_failed = True
            print(
                f"[build_ibl_nodes] launcher-가드 실패: {len(lissues)}건 "
                f"(라우팅된 창 명령에 main.js 핸들러 부재 — 침묵 실패)",
                file=sys.stderr,
            )
            for issue in lissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print(
                "[build_ibl_nodes] launcher-가드 통과 ✓ "
                "(라우팅된 창 명령 전부 main.js switch 에 핸들러 보유)"
            )

    # --- 교재-가드: 12_ibl_only.md ↔ 카탈로그 (--check/--validate 전용) ---
    textbook_failed = False
    if check or validate_only:
        tissues = check_textbook(root, data)
        if tissues:
            textbook_failed = True
            print(
                f"[build_ibl_nodes] 교재-가드 실패: {len(tissues)}건 "
                f"(12_ibl_only.md 스니펫/노드표가 카탈로그와 불일치)",
                file=sys.stderr,
            )
            for issue in tissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 교재-가드 통과 ✓ (스니펫 실존 + 노드 선택표 집합 일치)")

    if validate_only:
        return 1 if (validation_failed or corpus_failed or fixture_failed
                     or profile_failed or os_failed or launcher_failed
                     or textbook_failed) else 0

    # 폰 매니페스트 파생 (runs_on + 검증된 폰 패키지). data 파싱 성공 시에만.
    manifest_path = root / "data" / "phone_manifest.json"
    manifest_text = None
    if data is not None:
        manifest = derive_phone_manifest(data, root)
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"

    # 능력 메타 파생 (Phase 4, needs_key/weight/locale — 코드 스캔, 손수 유지 아님).
    pkg_meta_path = root / "data" / "package_meta.json"
    pkg_meta_text = json.dumps(derive_package_meta(root), ensure_ascii=False, indent=2) + "\n"

    # 행동 건강 fixture 파생 (액션별 fixture:/exempt: 필드 → 중앙 파일). data 파싱 성공 시에만.
    fixtures_path = root / "data" / "ibl_fixtures.json"
    fixtures_text = None
    if data is not None:
        fixtures_text = json.dumps(derive_fixtures(data), ensure_ascii=False, indent=2) + "\n"

    if check:
        if not target.is_file():
            print(f"[build_ibl_nodes] check: 타깃 부재 — {target}", file=sys.stderr)
            return 1
        current = target.read_text(encoding="utf-8")
        bytes_ok = current == output
        if not bytes_ok:
            h_cur = hashlib.sha256(current.encode("utf-8")).hexdigest()[:12]
            h_new = hashlib.sha256(output.encode("utf-8")).hexdigest()[:12]
            print(
                f"[build_ibl_nodes] check: 바이트 불일치 — 빌드 결과가 현재 yaml과 다름\n"
                f"  현재 {h_cur} / 빌드 {h_new}",
                file=sys.stderr,
            )
        else:
            print("[build_ibl_nodes] check: 바이트 일치 ✓")
        # 폰 매니페스트 정합 (드리프트 방지)
        manifest_ok = True
        if manifest_text is not None:
            on_disk = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else None
            manifest_ok = on_disk == manifest_text
            if not manifest_ok:
                print(
                    f"[build_ibl_nodes] check: phone_manifest.json 불일치 — "
                    f"`python3 scripts/build_ibl_nodes.py` 로 재생성 필요",
                    file=sys.stderr,
                )
            else:
                print("[build_ibl_nodes] check: phone_manifest.json 일치 ✓")
        # 능력 메타 정합 (드리프트 방지 — needs_key/weight/locale 은 코드가 유일한 소스)
        pkg_meta_on_disk = pkg_meta_path.read_text(encoding="utf-8") if pkg_meta_path.is_file() else None
        pkg_meta_ok = pkg_meta_on_disk == pkg_meta_text
        if not pkg_meta_ok:
            print(
                f"[build_ibl_nodes] check: package_meta.json 불일치 — "
                f"`python3 scripts/build_ibl_nodes.py` 로 재생성 필요",
                file=sys.stderr,
            )
        else:
            print("[build_ibl_nodes] check: package_meta.json 일치 ✓")
        # fixture 파생 정합 (드리프트 방지 — 소스는 액션별 fixture:/exempt: 필드)
        fixtures_ok = True
        if fixtures_text is not None:
            fx_on_disk = fixtures_path.read_text(encoding="utf-8") if fixtures_path.is_file() else None
            fixtures_ok = fx_on_disk == fixtures_text
            if not fixtures_ok:
                print(
                    f"[build_ibl_nodes] check: ibl_fixtures.json 불일치 — "
                    f"`python3 scripts/build_ibl_nodes.py` 로 재생성 필요",
                    file=sys.stderr,
                )
            else:
                print("[build_ibl_nodes] check: ibl_fixtures.json 일치 ✓")
        return 0 if (bytes_ok and manifest_ok and pkg_meta_ok and fixtures_ok
                     and not validation_failed
                     and not corpus_failed and not fixture_failed
                     and not profile_failed and not os_failed
                     and not launcher_failed and not textbook_failed) else 1

    if validation_failed:
        print(
            "[build_ibl_nodes] 빌드는 수행했지만 검증 실패 — "
            "ibl_nodes.yaml 작성 보류. --validate 로 재확인하세요.",
            file=sys.stderr,
        )
        return 1

    target.write_text(output, encoding="utf-8")
    print(f"[build_ibl_nodes] 작성: {target}")
    if manifest_text is not None:
        manifest_path.write_text(manifest_text, encoding="utf-8")
        print(f"[build_ibl_nodes] 작성: {manifest_path} "
              f"(폰 패키지 {len(PHONE_VERIFIED_PACKAGES)}, runnable {manifest_text.count(':')})")
    pkg_meta_path.write_text(pkg_meta_text, encoding="utf-8")
    print(f"[build_ibl_nodes] 작성: {pkg_meta_path}")
    if fixtures_text is not None:
        fixtures_path.write_text(fixtures_text, encoding="utf-8")
        print(f"[build_ibl_nodes] 작성: {fixtures_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="작성하지 않고 현재 data/ibl_nodes.yaml과 일치 + 검증 통과 확인 (CI/pre-commit용)",
    )
    ap.add_argument(
        "--validate",
        action="store_true",
        help="삼각 검증만 수행 (yaml 작성·바이트 비교 없음)",
    )
    args = ap.parse_args(argv)
    return build(check=args.check, validate_only=args.validate)


if __name__ == "__main__":
    raise SystemExit(main())
