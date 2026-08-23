"""데이터 소유 선언 레지스트리 + 주인 없는 파일 주간 감사 (2026-08-21 신설)

backend 모듈에 LAYERS 배정이 있듯, data/·outputs/ 파일 가족마다 **주인**(진실 소스
또는 생성 기관)과 **kind** 를 선언한다. 감사는 선언에 안 잡히는 파일을 깃발로 —
고아 캐시 소탕(2026-07-24 실측 13개)의 기계화다.

원칙:
  - **보고만 한다, 지우지 않는다** — 판정 불능→거짓 단정(B8) 회피. 실삭제=사용자.
  - 선언은 코드에 산다(몸의 명사=코드). 첫 매칭 승리(위→아래) — 구체 패턴을 앞에.
  - 통짜 디렉토리 가족은 프리픽스 선언(내용 미하강) → 감사 비용은 최상위 걷기뿐.
  - 백업 규약 집행 보조: data/_backups/ 의 30일 지난 항목도 삭제 *후보*로 보고.

kind 어휘:
  source(사람·AI 저술 정본) / derived(빌드·파생 — 재생성 가능) / state(런타임 상태 —
  현재값의 진실 소스) / ledger(append-only 사건 기록) / cache(재생성 가능 캐시) /
  output(작업 산출물) / log(로그) / backup(백업 규약 정거장)
"""
from __future__ import annotations

import fnmatch
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

try:
    from logging_utils import get_logger
    logger = get_logger(__name__)
except Exception:  # pragma: no cover - 독립 실행 폴백
    import logging
    logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent
_STATE_PATH = _ROOT / "data" / ".data_ownership_state.json"
_FLAGS_PATH = _ROOT / "data" / "data_ownership_flags.json"

CADENCE_HOURS = 168          # 주 1회 (vocab_overlap 과 같은 카덴스)
BACKUP_STALE_DAYS = 30       # 백업 규약: 30일 지난 _backups 항목 = 삭제 후보
_MAX_FLAGS = 80              # 보고 상한 — 그 이상이면 개별 파일이 아니라 구조 문제

# ── 소유 선언 (첫 매칭 승리 — 구체 패턴을 앞에) ──────────────────────────────
# (패턴, 주인, kind). 패턴=repo 루트 기준 상대경로 fnmatch("/" 구분자).
# 디렉토리 가족은 "prefix/**" — 감사는 그 안으로 하강하지 않는다.
DECLARATIONS: List[tuple] = [
    # 백업 규약 정거장 (README 가 규약 정본)
    ("data/_backups/**",            "백업 규약(data/_backups/README.md)",       "backup"),

    # 저술 정본 (source)
    ("data/ibl_nodes_src/**",       "IBL 코어 어휘 src(build_ibl_nodes)",       "source"),
    ("data/packages/**",            "패키지 시스템(코드+어휘 자기완결)",         "source"),
    ("data/system_docs/**",         "시스템 AI 장기기억(정본 서열 ③)",           "source"),
    ("data/guides/**",              "가이드(guide_db 배선)",                     "source"),
    ("data/guide_db.json",          "가이드 색인(수동 유지)",                    "source"),
    ("data/common_prompts/**",      "프롬프트 저술물(prompt_builder)",           "source"),
    ("data/instruments/**",         "standalone 계기 선언",                      "source"),
    ("data/system_ai_prompts/**",   "시스템 AI 프롬프트 저술물",                 "source"),
    ("data/api_registry.yaml",      "API 레지스트리(api_engine)",                "source"),
    ("data/*_role.txt",             "역할 저술물(appmaker·forage·system_ai)",    "source"),
    ("data/system_ai_memo.txt",     "사용자 메모(시스템 AI 참조)",               "source"),
    ("data/world_pulse_config.example.json", "설정 예시(저술물)",                "source"),

    # 빌드 파생 (derived — 재생성 가능, 직접 편집 금지 부류)
    ("data/ibl_nodes.yaml",         "build_ibl_nodes 산출물",                    "derived"),
    ("data/ibl_fixtures.json",      "build_ibl_nodes 산출물",                    "derived"),
    ("data/ibl_return_shapes.json", "ibl_shape_sweep 실측 반환 열(카탈로그 ⟨열⟩)",  "derived"),
    ("data/ibl_shape_sweep_state.json", "반환 모양 스윕 주간 카덴스 상태",        "state"),
    ("data/ibl_param_shapes.json",  "ibl_param_sweep 실측 입력 인자(카탈로그 ⟨인자⟩)", "derived"),
    ("data/ibl_param_sweep_state.json", "입력 모양 스윕 주간 카덴스 상태",        "state"),
    ("data/ibl_composition_metrics.json", "IBL 조합률 측정 산출(ibl_composition_metrics)", "derived"),
    ("data/core_manifest.json",     "build_ibl_nodes 산출물",                    "derived"),
    ("data/package_meta.json",      "build_ibl_nodes 산출물",                    "derived"),
    ("data/phone_manifest.json",    "build_ibl_nodes 산출물",                    "derived"),
    ("data/bodies/**",              "build_body_bundle 산출물",                  "derived"),

    # 해마·학습 (실행기억 = 코퍼스가 몸)
    ("data/ibl_usage.db",           "해마 코퍼스(ibl_usage_db)",                 "state"),
    ("data/ibl_examples.db",        "해마 예제 DB(ibl_usage_db)",                "state"),
    ("data/ibl_hippo_index.json",   "해마 색인 export(파생)",                    "derived"),
    ("data/ibl_hippo_vecs.f32",     "해마 벡터 export(파생)",                    "derived"),
    ("data/training/**",            "학습 코퍼스(gitignore — 몸)",               "state"),
    ("data/models/**",              "fine-tuned 모델(cloud_training 산출)",      "derived"),

    # 기억·인지 상태
    ("data/world_pulse.db",         "World Pulse(pulse_db)",                     "state"),
    ("data/system_ai_memory.db",    "시스템 AI 기억(system_ai_memory)",          "state"),
    ("data/forage_memory.db",       "포식 기억(forage_memory)",                  "state"),
    ("data/forage_boards.db",       "포식 부속(forage 계열)",                    "state"),
    ("data/forage_history.db",      "포식 부속(forage 계열)",                    "state"),
    ("data/forage_thumbs.db",       "포식 부속(forage 계열)",                    "state"),
    ("data/guide_usage.db",         "가이드 사용 계수(guide_registry)",          "state"),
    ("data/guide_dates_cache.json", "가이드 감사 캐시",                          "cache"),
    ("data/spill/**",               "파이프 자동 스필·재개 참조(common.spill, 24h 기계 GC)", "cache"),
    ("data/system_locator.db*",     "시스템 로케이터(file_index)",               "state"),
    ("data/table_since.db*",        "[table:since] 상태",                        "state"),

    # 대화·도메인 상태 (DB·디렉토리)
    ("data/conversation.db*",       "대화 DB(conversation_db)",                  "state"),
    ("data/conversations.db",       "대화 DB(conversation_db)",                  "state"),
    ("data/multi_chat.db",          "멀티채팅(multi_chat_db)",                   "state"),
    ("data/business.db",            "비즈니스/이웃(business_manager)",           "state"),
    ("data/phone_notifications.db", "폰 알림 포획소(phone_notifications)",       "state"),
    ("data/warehouse_feed.db",      "창고 피드(warehouse_feed)",                 "state"),
    ("data/bulletin/**",            "자유게시판(bulletin 패키지)",               "state"),
    ("data/family_news/**",         "가족신문(family-news 패키지)",              "state"),
    ("data/business_images/**",     "비즈니스 이미지(business)",                 "state"),
    ("data/finance/**",             "[self:finance] 원장",                       "state"),
    ("data/health/**",              "건강 기록(health-record)",                  "state"),
    ("data/music/**",               "내 음악 라이브러리([self:music])",          "state"),
    ("data/notebook/**",            "근거 고정 질의([self:notebook])",           "state"),
    ("data/voice/**",               "목소리 복제 자산(voice-narration)",         "state"),
    ("data/tokens/**",              "인증 토큰(auth_manager)",                   "state"),
    ("data/browser_cookies/**",     "브라우저 쿠키(browser-action)",             "state"),
    ("data/portal_icons/**",        "포털 아이콘(community-portal)",             "state"),
    ("data/launcher_uploads/**",    "런처 업로드(api_launcher_web)",             "state"),
    ("data/system_ai_images/**",    "채팅 이미지 왕복(api_system_ai)",           "state"),
    ("data/system_ai_state/**",     "시스템 AI 상태",                            "state"),
    ("data/projects/**",            "프로젝트 데이터(project_manager)",          "state"),
    ("data/workflows/**",           "워크플로우 원장(workflow_engine)",          "state"),
    ("data/scripts/**",             "등록 스크립트([self:script] — 절차의 거처)", "state"),
    ("data/scripts.json",           "등록 스크립트 원장([self:script])",          "state"),
    ("data/script_runs/**",         "스크립트 실행 기록([self:script])",          "log"),
    ("data/showcase_stage/**",      "공개파일 스테이징(showcase)",               "state"),
    ("data/xray/**",                "xray 스트림(xray_stream)",                  "state"),

    # 캐시 (재생성 가능)
    ("data/youtube_cache/**",       "유튜브 릴레이 LRU(api_ytrelay, 5GB)",       "cache"),
    ("data/nas_stream_cache/**",    "NAS HLS LRU(api_nas_hls, 20GB)",            "cache"),
    ("data/thumbnail_cache/**",     "썸네일 캐시(thumbnails)",                   "cache"),
    ("data/location_cache.json",    "역지오코딩 격자 캐시",                      "cache"),
    ("data/warehouse_directory_cache.json", "창고 둘러보기 캐시",                "cache"),

    # 런타임 상태 파일 (현재값의 진실 소스)
    ("data/model_gear.json",        "모델 기어(model_resolver)",                 "state"),
    ("data/*_ai_config.json",       "모델 티어 설정(model_resolver)",            "state"),
    ("data/world_pulse_config.json", "World Pulse 설정",                         "state"),
    ("data/portal_state.json",      "포털 원장(portal_core)",                    "state"),
    ("data/portal_state.lock",      "포털 원장 flock",                           "state"),
    ("data/webapps.json",           "웹앱 등기부 수동 보충([self:webapp])",      "state"),
    ("data/warehouse.json",         "창고 상태",                                 "state"),
    ("data/warehouse_directory.json", "창고 둘러보기",                           "state"),
    ("data/warehouse_guestbook.json", "창고 방명록",                             "state"),
    ("data/warehouse_likes.json",   "창고 좋아요(warehouse_likes)",              "state"),
    ("data/switches.json",          "스위치(switch_manager)",                    "state"),
    ("data/event_triggers.json",    "트리거(trigger_engine)",                    "state"),
    ("data/calendar_events.json",   "캘린더(calendar_manager)",                  "state"),
    ("data/launcher_app_layout.json", "앱 그리드 배치(런처)",                    "state"),
    ("data/launcher_web_config.json", "원격 런처 설정",                          "state"),
    ("data/limb_keys.json",         "손발 자격 원장(limb_keys)",                 "state"),
    ("data/device_registry.json",   "기기 등록(device_registry)",                "state"),
    ("data/device_id.txt",          "기기 신원",                                 "state"),
    ("data/public_face.json",       "몸 공개 주소(public_face)",                 "state"),
    ("data/tunnel_config.json",     "터널 설정(api_tunnel)",                     "state"),
    ("data/nas_config.json",        "NAS 설정",                                  "state"),
    ("data/report_publish.json",    "정기보고 발행 면(api_report)",              "state"),
    ("data/showcase_state.json",    "공개파일 상태(showcase)",                   "state"),
    ("data/youtube_watch.json",     "유튜브 시청 기록(api_ytrelay)",             "state"),
    ("data/body_location.json",     "몸 위치",                                   "state"),
    ("data/hidden_dm_peers.json",   "DM 숨김 목록",                              "state"),
    ("data/auto_response_state.json", "자동응답 on/off(auto_response)",          "state"),
    ("data/claude_code_*.json",     "claude_code 프로바이더 상태",               "state"),
    ("data/ai_desktop_map.json",    "자율주행 데스크탑 배치",                    "state"),
    ("data/world_pulse_db.json",    "World Pulse 판(world_pulse.PULSE_DB_PATH)", "state"),
    ("data/phone_agent.json",       "인가 폰 신원(phone_notifications)",         "state"),
    ("data/peer_cards/**",          "이웃 몸 명함 캐시(peer_cards)",             "state"),
    ("data/diagnostic_report.md",   "자가 진단 보고서(world_pulse_health — 재생성)", "derived"),
    ("data/outputs/**",             "시스템 AI 산출물(tool_context.output_dir 무맥락 착지점)", "output"),

    # 감사·카덴스 기관 (자기 자신 포함)
    ("data/*_state.json",           "감사·카덴스 상태(maintenance bundle)",      "state"),
    ("data/*_flags.json",           "감사 깃발(maintenance bundle)",             "state"),
    ("data/.*",                     "감사·카덴스 숨김 상태",                     "state"),

    # 원장(ledger)·로그·부속
    ("data/write_ledger.jsonl*",    "쓰기 관문 원장(write_ledger — 로테이션 포함)", "ledger"),
    ("data/*.jsonl",                "append-only 사건 원장",                     "ledger"),
    ("data/*.log",                  "런타임 로그",                               "log"),
    ("data/*.log.*",                "런타임 로그(로테이션)",                     "log"),
    ("data/*.pid",                  "프로세스 pid",                              "log"),
    ("data/*.db-wal",               "SQLite 사이드카",                           "state"),
    ("data/*.db-shm",               "SQLite 사이드카",                           "state"),
    ("data/*.bak",                  "safe_store 직전 세대(설계된 기능)",         "backup"),

    # 산출물 나무 (통짜 — outputs 는 본성이 산출물 더미라 개별 감사 안 함)
    ("outputs/**",                  "작업 산출물(에이전트·스케줄러)",            "output"),
]


def _match(rel: str):
    """선언 첫 매칭 — (주인, kind) 또는 None. 디렉토리 프리픽스( /** )는 상위 경로도 매칭."""
    for pat, owner, kind in DECLARATIONS:
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if rel == prefix or rel.startswith(prefix + "/"):
                return owner, kind
        elif fnmatch.fnmatch(rel, pat):
            return owner, kind
    return None


def _hint_of(rel: str, is_dir: bool) -> str:
    """고아의 부류 힌트 — 처방은 사람 몫, 힌트는 기계가."""
    name = rel.rsplit("/", 1)[-1]
    low = name.lower()
    if ".bak" in low or "backup" in low or "_cleanup" in low:
        return "일회성 백업으로 보임 — 규약 위반: data/_backups/YYYY-MM-DD_이름/ 으로"
    if low.endswith((".md", ".html", ".png", ".jpg", ".pdf")):
        return "산출물로 보임 — outputs/ 가 제자리"
    if low.endswith((".db", ".sqlite")):
        return "주인 없는 DB — 소비 코드가 있으면 선언 추가, 없으면 은퇴 후보"
    if is_dir:
        return "주인 없는 디렉토리 — 선언 추가 또는 정리 후보"
    return "주인 없는 파일 — 선언 추가 또는 정리 후보"


def _walk_flags() -> Dict:
    """data/·outputs/ 최상위(+선언 안 된 파일만)를 걷어 주인 없는 항목을 깃발로."""
    orphans: List[Dict] = []
    for base in ("data", "outputs"):
        base_dir = _ROOT / base
        if not base_dir.is_dir():
            continue
        for entry in sorted(base_dir.iterdir()):
            rel = f"{base}/{entry.name}"
            if _match(rel):
                continue
            try:
                st = entry.stat()
                size = st.st_size if entry.is_file() else sum(
                    f.stat().st_size for f in entry.rglob("*") if f.is_file())
                mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
            except OSError:
                size, mtime = 0, "?"
            orphans.append({"path": rel, "dir": entry.is_dir(), "size": size,
                            "mtime": mtime, "hint": _hint_of(rel, entry.is_dir())})

    # 백업 규약 집행 보조 — _backups 의 30일 지난 항목(보고만, 실삭제=사용자)
    stale_backups: List[Dict] = []
    backups = _ROOT / "data" / "_backups"
    if backups.is_dir():
        cutoff = datetime.now() - timedelta(days=BACKUP_STALE_DAYS)
        for entry in sorted(backups.iterdir()):
            if entry.name == "README.md":
                continue
            try:
                mt = datetime.fromtimestamp(entry.stat().st_mtime)
            except OSError:
                continue
            if mt < cutoff:
                stale_backups.append({"path": f"data/_backups/{entry.name}",
                                      "mtime": mt.strftime("%Y-%m-%d")})

    # 선언 부패 — 와일드카드 없는 정확 경로 선언인데 실체가 사라진 것
    vanished = [pat for pat, _, _ in DECLARATIONS
                if not any(c in pat for c in "*?[") and not (_ROOT / pat).exists()]

    return {"orphans": orphans[:_MAX_FLAGS], "orphans_total": len(orphans),
            "stale_backups": stale_backups, "vanished_declarations": vanished}


def run_data_ownership_check(force: bool = False) -> Dict:
    """주간 카덴스로 주인 없는 파일을 감사하고 self_checks 형식 1건을 반환.

    run_maintenance_bundle 합류. 깃발은 data/data_ownership_flags.json 에 —
    **보고만, 삭제 없음**(고아 판정의 실집행은 사용자 결정).
    """
    if not force:
        try:
            state = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            last = datetime.fromisoformat(state["last_run"])
            if datetime.now() - last < timedelta(hours=CADENCE_HOURS):
                return {"skipped": "cadence"}
        except Exception:
            pass

    started = datetime.now()
    error = None
    report: Dict = {}
    try:
        report = _walk_flags()
    except Exception as e:
        # ★측정 실패도 실패다 — 못 본 것을 '고아 0'으로 보고하면 이 감사는 눈이 먼 것.
        error = f"측정 실패: {e}"
        logger.warning(f"[DataOwnership] {error}")

    orphans = report.get("orphans", [])
    stale = report.get("stale_backups", [])
    vanished = report.get("vanished_declarations", [])
    try:
        _STATE_PATH.write_text(json.dumps({
            "last_run": started.isoformat(), "orphans": report.get("orphans_total", 0),
            "stale_backups": len(stale), "error": error,
        }, ensure_ascii=False), encoding="utf-8")
        _FLAGS_PATH.write_text(json.dumps({
            "measured_at": started.isoformat(), "declarations": len(DECLARATIONS),
            **report,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[DataOwnership] 상태 저장 실패 (무시): {e}")

    if orphans:
        head = "; ".join(o["path"] for o in orphans[:5])
        logger.warning(f"[DataOwnership] 주인 없는 항목 {report['orphans_total']}건 — {head} … ({_FLAGS_PATH.name})")
    if stale:
        logger.info(f"[DataOwnership] 30일 지난 백업 {len(stale)}건 — 삭제 후보(실삭제=사용자)")
    if vanished:
        logger.info(f"[DataOwnership] 실체 사라진 선언 {len(vanished)}건 — 선언 정리 후보")
    if not orphans and not error:
        logger.info("[DataOwnership] 주인 없는 항목 없음 — 소유 선언 완전")

    n = report.get("orphans_total", 0)
    return {
        "node": "__static__",
        "action": "data_ownership",
        "success": not orphans and not error,
        "response_ms": int((datetime.now() - started).total_seconds() * 1000),
        "data_quality": ("ok" if not orphans and not error
                         else "orphans" if orphans else "audit_incomplete"),
        "error_message": (f"주인 없는 항목 {n}건 — data_ownership_flags.json" if orphans else error),
        "orphans": orphans, "stale_backups": stale,
    }
