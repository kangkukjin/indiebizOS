"""build_ibl_nodes 공유 상수·헬퍼 (2026-07-18 모듈화 — 1500줄 규칙).

build_ibl_nodes.py 에서 verbatim 이동. 진입점은 여전히 scripts/build_ibl_nodes.py —
외부(migrate_*·apply_edition)는 그쪽 재수출을 쓴다. 여기는 형제 모듈
(iblbuild_guards/derive/appview/validators)이 공유하는 최하층: 순환 import 금지.
"""
from __future__ import annotations
import sys
from pathlib import Path

# 인자 어휘(읽기키 추출기·보편키·문서화 예외)는 backend/ibl_param_vocab.py 가 단일
# 소유한다 — 런타임 검사(ibl_engine 경고·증류 게이트)와 이 정적 검사가 같은 수를 쓰게.
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

try:
    import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)
except ImportError:
    pass
from ibl_param_vocab import (  # noqa: E402,F401 (형제 모듈·build_ibl_nodes 재수출용)
    UNIVERSAL_PARAM_KEYS,
    RUNTIME_META_KEYS,
    CORPUS_PARAM_ALLOW,
    _file_read_keys,
    _dir_read_keys,
)


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
# 액션이 어디서 도는가: anywhere(기본·이식가능 로직/HTTP) / pc_only(데스크톱=맥·리눅스·
# 윈도우 하드웨어·무거운 의존·미검증 패키지, 폰 아님) / phone_only(폰 하드웨어=알림·센서).
VALID_RUNS_ON = {"anywhere", "pc_only", "phone_only"}
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
    "real-estate",
    "android",   # M3: [sense:phone] 폰 로컬 알림. limbs:android(android_op)은 pc_only 태그로 제외.
    "business",  # 메신저(others:messages/neighbor/contact)+비즈니스 CRM(self:business*). business.db 폰 머지 토대 위. auto_response 는 pc_only 로 제외(PC 전용 폴러).
    "cctv",      # CCTV 검색(sense:cctv search) — 모듈 import importlib.util(stdlib)뿐, HLS는 WebView <video>+hls.js 재생.
    "health-record",  # 의료기록(self:health save/query) — storage 가 stdlib(sqlite)만. health_records.db 폰↔맥 합집합 머지(health_sync, business.db 선례) 토대.
    # 2026-06-13 runs_on 정직성 회복: anywhere 인데 폰 미번들이던 이식 가능 패키지(HTTP API 조회류,
    # 자원이 외부라 몸 무관). 의존성 모듈레벨 스캔=stdlib/HTTP. A36 대표 액션 실행으로 import 확정.
    "cloudflare",       # Cloudflare API(HTTP)
    "context7",         # 라이브러리 문서 검색(HTTP)
    "kosis",            # 통계청 KOSIS API(HTTP)
    "legal",            # 법령/판례 검색(HTTP)
    "startup",          # 창업 정보(HTTP + stdlib xml)
    # (local-info 는 2026-08-15 지역정보 3형제 은퇴와 함께 패키지째 삭제됐는데 이 목록에만
    #  남아 있었다 → 폰 번들 빌드가 "정본 누락: tools/local-info" 로 그날부터 깨져 있었다.
    #  2026-08-17 제거. 어휘를 지우면 그 어휘의 배선도 따라와야 한다.)
    "shopping-assistant",  # 다나와 가격비교(tool_danawa 순수 HTTP — stdlib urllib 폴백이라 curl_cffi 없는 폰서도 로컬 실행) + sense:used 번개장터/당근 내부 API + sense:freelance 크몽. 중고 스크래핑(playwright)만 지연 import→폰선 graceful 미지원(arxiv 선례). ★옛 근거였던 네이버 쇼핑 API 는 2026-08 은퇴(공식 SE05 + 내부 API 418 봇차단) → 폰 쇼핑 축을 다나와로 옮겨 이 등재를 회복.
    "memory",   # 심층기억(self:memory). 자아별 사적 로컬 DB(동기화 안 함). 모듈레벨 stdlib만(numpy/sqlite_vec 지연) → 폰서 import 안전, 시맨틱 미가용 시 LIKE/FTS 키워드 폴백(기존 graceful 강등). 시맨틱-온-폰(/embed 렌트+brute-force)은 후속.
    # self 노드 = AI 자신 → file 액션은 자기 몸의 fs 에 작용(각 몸 자기 파일·시계). 둘 다 모듈레벨 stdlib,
    # 무거운 것(fitz/docx/openpyxl·api_pcmanager)은 지연 import → 폰 import 안전. read 의 PDF/docx 포맷만
    # 폰서 graceful 실패(텍스트는 됨). spreadsheet(openpyxl write)는 액션별 pc_only 유지.
    "system_essentials",  # self:time(자기 시계)·read/write/list/grep/copy/move/delete/file_find(glob+메타, 구 fs_query 흡수)/edit(자기 fs)
    "pc-manager",         # self:storage/folder_note(자기 fs 인덱스·주석). (limbs:explorer 는 2026-08-15 open_window{app:files} 로 흡수)
    "photo-manager",      # self:photo 라이브 질의 — backend/file_index 가 몸 분기(맥 Spotlight↔폰 MediaStore via PhoneActions.queryMedia). 핸들러 얇은 preset, photo_db/scanner 는 guard import(폰선 질의 경로 미사용). A36 종단 검증.

    "contest",          # AI 경진대회 검색(sense:contest, Kaggle API HTTP + stdlib). KAGGLE_API_TOKEN 폰 프로비저닝 전제.
    "study",            # 연구 검색(HTTP + stdlib; study:paper 만 arxiv 3p — A36서 안 되면 그 액션 pc_only)
    # python-exec 은퇴(2026-07-02 d4408c6): pre-IBL 화석 → not_installed. 어휘 미배선이라
    #   execute_ibl 단일도구로 도달 불가 → 폰 번들에서도 제외(맥·폰 대칭). 부활 시 installed 복귀 + 재등재.
    "data-ops",  # 통화→통화 변환자(filter/sort/take/select/dedup/groupby/join/union/merge) + 표준 코어 문서 emitter(table:structure/document — 2026-07-03 media_producer서 이관). 순수 superstructure(IBL 문법, 몸 무관), 모듈레벨 stdlib만(json/re, 서드파티 0 — 문서 emitter의 playwright/docx/pptx/typst는 함수 안 지연 import, html 렌더=문자열이라 폰서도 동작). 폰-로컬 통화(sense:here 등)는 폰서 거르고 정렬해야 맞음 → anywhere 가 정직.
    "media_producer",  # ★순수 연산만 anywhere(image_critic/image_gemini=httpx+Gemini REST). 무거운 emitter(tts·render_html=moviepy/edge_tts/playwright — html_video·slide·remotion 은 2026-08-05 은퇴·이관)는 액션별 pc_only 유지 → 폰선 포워드. moviepy·edge_tts 모듈레벨 import를 지연화해 폰서 모듈 import 성공(폰 시뮬 검증). (table:document/structure 문서 emitter는 data-ops로 이관.)
}


# === 코퍼스 param 정합 검사 (2026-06-04) ===
# UNIVERSAL_PARAM_KEYS / CORPUS_PARAM_ALLOW 는 backend/ibl_param_vocab.py 로 이주
# (2026-07-03, 런타임 인자 경고와 단일 소스). 상단 import 로 여기서도 같은 수를 쓴다.
# 정리됨(2026-06-04): pew_research:topic / blog:sort / web_site:reference / web:font
#   (migrate_allowlist_cleanup.py — 군더더기 제거) + self:trigger:cron
#   (trigger_engine._cron_to_config 로 내부 해소 — 핸들러가 cron 직접 읽음).

# 학습 코퍼스 (param 키 추출 대상).
CORPUS_FILES = [
    "data/training/ibl_training_balanced_20260516.json",
    "data/training/ibl_distilled.json",
]


# ── 가드 입력 선언 (--check 트리거의 단일 진실 소스) ───────────────────────────
#
# ★왜 여기 있나 (2026-07-25): pre-commit 훅이 트리거 정규식을 자기 안에 하드코딩하고
# 있었고, 그 목록이 가드가 *실제로 읽는 파일*과 어긋나 있었다. 대표 사례 —
# 뷰-렌더러 가드(iblbuild_appview.check_view_renderers)는
# frontend/.../GenericInstrument.tsx 와 backend/launcher_web_render.py 를 열어
# p.type 파리티를 대조하는데, 그 두 파일 중 어느 것도 트리거에 없었다. 즉 이 가드는
# **어휘를 고칠 때만 발동하고 렌더러를 고칠 때는 발동하지 않았다** — 렌더러에서
# 프리미티브 케이스를 지워도 커밋이 그냥 통과했다.
#
# 그래서 "무엇이 --check 를 트리거하는가"를 훅이 아니라 빌더가 선언한다. 새 가드가
# 새 파일을 읽기 시작하면 이 목록에 한 줄 더하면 되고, 훅은 손대지 않는다.
# 훅은 `build_ibl_nodes.py --inputs-regex` 로 물어본다.
#
# 형식: git ls-files 스타일 상대경로에 대한 POSIX ERE (전체 매칭, ^…$ 는 훅이 씌움).
GUARD_INPUT_PATTERNS = [
    # ── 어휘 정의 (기존 트리거) ──
    r"data/ibl_nodes_src/.*\.yaml",
    r"data/packages/(installed|not_installed)/.*/ibl_actions\.yaml",
    r"data/packages/(installed|not_installed)/.*/tool\.json",
    # 패키지 실행 코드 전체 — op 분기는 handler.py 지만 코퍼스 param 키 추출과
    # OS-가드는 tool_*.py 등 형제 모듈도 읽는다(예: radio/tool_radio.py).
    r"data/packages/(installed|not_installed)/.*\.py",
    r"data/training/.*\.json",
    r"scripts/(build_ibl_nodes|iblbuild_[a-z]+)\.py",

    # ── 빌드 산출물 (바이트 일치 대조 대상 — 손으로 고치면 즉시 어긋난다) ──
    r"data/(ibl_nodes\.yaml|ibl_fixtures\.json|package_meta\.json|phone_manifest\.json|core_manifest\.json)",

    # ── backend (2026-07-25 신규) ──
    # validate_corpus_params 가 (root/"backend").glob("*.py") 를 통째로 읽고,
    # 표준-코어 가드=ibl_parser.py, 뷰-렌더러 가드=launcher_web_render.py,
    # launcher-가드=ibl_routing.py, OS-가드=backend 파일 12종,
    # iblbuild_common=ibl_param_vocab.py, derive=common/auth_manager.py 를 읽는다.
    r"backend/.*\.py",

    # ── frontend (2026-07-25 신규) ──
    # 뷰-렌더러 가드(데스크탑 쪽)와 launcher-가드(창 명령 ↔ main.js switch).
    r"frontend/src/components/GenericInstrument\.tsx",
    r"frontend/src/components/generic/.*\.tsx",
    r"frontend/electron/main\.js",

    # ── 문서·프롬프트 (2026-07-25 신규) ──
    # 뷰-어휘 문서-동기 가드 = ibl.md·new_action_checklist.md 의 어휘 줄,
    # 교재-가드 = 12_ibl_only.md ↔ 카탈로그, 노드 guides 실존 = data/guides/.
    r"data/system_docs/ibl\.md",
    r"data/guides/.*\.md",
    r"data/common_prompts/fragments/12_ibl_only\.md",
]


def guard_inputs_regex() -> str:
    """GUARD_INPUT_PATTERNS 를 훅이 쓸 단일 ERE 로 합친다(^…$ 포함)."""
    return "^(" + "|".join(GUARD_INPUT_PATTERNS) + ")$"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _extract_action_param_aliases(data: dict) -> dict[str, set[str]]:
    """병합된 레지스트리의 액션별 aliases 블록 → {qualified: {정규키 ∪ 별칭들}}.

    (이주 2026-07-03: 옛 ibl_routing.ACTION_PARAM_ALIASES AST 추출 → 어휘 데이터 소유.
    별칭은 각 액션 정의처(src yaml / 패키지 ibl_actions.yaml)의 aliases: 블록이 단일 소스.)"""
    out: dict[str, set[str]] = {}
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            aliases = action.get("aliases")
            if not isinstance(aliases, dict):
                continue
            ks: set[str] = set()
            for canonical, alts in aliases.items():
                ks.add(str(canonical))
                ks.update(str(a) for a in (alts or []))
            out[f"{node_name}:{action_name}"] = ks
    return out


def backend_module_path(root, name):
    """평면 모듈명 → 실제 파일 경로 (물리 이동 2026-08-05: 층 디렉토리 탐색).

    모듈 이름은 평면 유일이므로 첫 일치가 정답. 못 찾으면 옛 평면 경로를
    돌려줘 호출측 exists() 검사가 종전 에러 문구를 내게 한다.
    """
    from pathlib import Path
    base = Path(root) / "backend"
    direct = base / f"{name}.py"
    if direct.exists():
        return direct
    for p in base.rglob(f"{name}.py"):
        if "__pycache__" not in p.parts:
            return p
    return direct
