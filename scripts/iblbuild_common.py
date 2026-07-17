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
    # python-exec 은퇴(2026-07-02 d4408c6): pre-IBL 화석 → not_installed. 어휘 미배선이라
    #   execute_ibl 단일도구로 도달 불가 → 폰 번들에서도 제외(맥·폰 대칭). 부활 시 installed 복귀 + 재등재.
    "data-ops",  # 통화→통화 변환자(filter/sort/take/select/dedup/groupby/join/union/merge) + 표준 코어 문서 emitter(table:structure/document — 2026-07-03 media_producer서 이관). 순수 superstructure(IBL 문법, 몸 무관), 모듈레벨 stdlib만(json/re, 서드파티 0 — 문서 emitter의 playwright/docx/pptx/typst는 함수 안 지연 import, html 렌더=문자열이라 폰서도 동작). 폰-로컬 통화(sense:here 등)는 폰서 거르고 정렬해야 맞음 → anywhere 가 정직.
    "media_producer",  # ★순수 연산만 anywhere(image_critic/image_gemini=httpx+Gemini REST). 무거운 emitter(html_video·tts·slide·render_html·remotion=moviepy/edge_tts/playwright)는 액션별 mac_only 유지 → 폰선 포워드. moviepy·edge_tts 모듈레벨 import를 지연화해 폰서 모듈 import 성공(폰 시뮬 검증). (table:document/structure 문서 emitter는 data-ops로 이관.)
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
