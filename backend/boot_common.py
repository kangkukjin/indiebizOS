"""boot_common.py — 몸 독립 부팅 배선 (shared boot wiring)

모든 indiebizOS 인스턴스가 *하드웨어와 무관하게* 켜야 하는 서브시스템을 한 곳에서
배선한다. 맥(`api.py`)·폰(`phone_api.py`)·미래 플랫폼(윈도우 등)이 부팅 시 모두
`wire_local_subsystems()` 를 호출한다.

설계 원칙 (헌법1조 — substrate/superstructure 이음매):
  - **몸 독립(superstructure)** 부팅은 여기 한 곳. 순수 로컬·하드웨어 무관한 서브시스템
    (에피소드 기록, 로컬 메모리 DB 보장 등)은 반드시 여기 추가한다 → 새 몸의 진입점을
    손으로 만들 때 *빠뜨릴 수 없게*.
  - **몸 종속** 부팅(터널·임베딩 모델 로딩·world_pulse 수집기·채널 폴러 등)은 각 진입점이
    `profile` 게이트로 *명시적으로* 분기한다 — 여기 넣지 않는다.

배경: 에피소드 로거가 맥 진입점(api.py)에만 배선돼 있어, 폰 진입점(phone_api.py)을 별도로
만들 때 침묵으로 누락됐다(폰에 world_pulse.db 미생성 → 실행 회고 불가). 몸 독립 서브시스템이
몸 종속 진입점에 갇혀 있던 것이 원인. 이 모듈이 그 이음매를 바로잡는다.
"""


def wire_local_subsystems(profile: str = None) -> dict:
    """몸 독립 부팅 서브시스템을 켠다.

    각 단계는 독립 try 로 감싼다 — 하나가 실패해도 나머지와 부팅은 계속된다
    (에피소드 기록 실패가 시스템 본체에 영향을 주면 안 된다).

    Args:
        profile: 호출 몸 식별용(로그 가독성). "mac" | "phone" | ... — 동작 분기엔
                 쓰지 않는다(몸 독립이므로). 몸별 차이는 각 진입점의 게이트가 책임진다.

    Returns:
        {서브시스템명: 성공여부} dict.
    """
    results = {}
    tag = f"[boot:{profile}]" if profile else "[boot]"

    # 에피소드 로거: 사용자 명령 → 최종 응답까지 1턴을 로컬 SQLite(world_pulse.db)에 기록한다.
    # 순수 로컬, 하드웨어 무관 — 모든 몸이 자기 실행을 (성공·실패 모두) 회고할 수 있어야 한다.
    # install() 이 자기 스키마(episode_log/episode_summary)도 보장하므로 추가 DB 초기화 불필요.
    try:
        from episode_logger import EpisodeLogger
        EpisodeLogger.install()
        results["episode_logger"] = True
        print(f"{tag} 에피소드 로거 설치")
    except Exception as e:
        print(f"{tag} 에피소드 로거 설치 실패 (무시): {e}")
        results["episode_logger"] = False

    # 이전 세션의 완료된 task 기록 정리: 프로젝트별 conversations.db + system_ai_memory.db 의
    # status='completed' 행을 비운다(현재 세션 task만 보존). 순수 로컬 SQLite, 하드웨어 무관 —
    # 폰-자아도 로컬에서 에이전트를 돌려 task 를 쌓으므로 같이 정리받아야 한다(맥 진입점에만
    # 있던 것이 폰서 침묵 누락이었다). 경로는 runtime_utils 가 INDIEBIZ_BASE_PATH 로 몸별 해소.
    try:
        from runtime_utils import get_base_path, get_data_path
        results["task_cleanup"] = _cleanup_completed_tasks(get_base_path(), get_data_path(), tag)
    except Exception as e:
        print(f"{tag} task 정리 실패 (무시): {e}")
        results["task_cleanup"] = False

    # 시스템 프로젝트(앱모드/수동모드) 폴더 보장: 런처의 앱/수동 모드가 IBL 실행 시
    # project_path 컨텍스트로 쓰는 홀더 폴더다. projects/ 는 런타임 상태(gitignore·미번들)라
    # fresh 설치(특히 윈도우 패키지)엔 없어, api_ibl 의 p.exists() 게이트가 실패 → 앱/수동
    # 모드 도구가 "활성 프로젝트 경로 없음"으로 전멸했다. 없으면 만들어 자가 치유(멱등).
    # 몸 독립 — 폰-자아도 앱/수동 표면을 쓰므로 같이 보장받아야 한다.
    try:
        from project_manager import ProjectManager
        made = ProjectManager().ensure_system_projects()
        results["system_projects"] = True
        if made:
            print(f"{tag} 시스템 프로젝트 폴더 생성: {', '.join(made)}")
    except Exception as e:
        print(f"{tag} 시스템 프로젝트 보장 실패 (무시): {e}")
        results["system_projects"] = False

    return results


def _cleanup_completed_tasks(base_path, data_path, tag: str) -> bool:
    """projects.json 의 각 프로젝트 conversations.db + system_ai_memory.db 에서 완료 task 삭제.

    stdlib(json/sqlite3/pathlib)만 사용 — 새 backend 모듈 의존 없음(폰 번들 안전).
    """
    import json
    import sqlite3
    from pathlib import Path

    cleaned = 0
    projects_file = base_path / "projects" / "projects.json"
    if projects_file.exists():
        with open(projects_file, "r", encoding="utf-8") as f:
            projects = json.load(f)
        for proj in projects:
            if proj.get("type") != "project":
                continue
            db = Path(proj.get("path", "")) / "conversations.db"
            if db.exists():
                try:
                    conn = sqlite3.connect(str(db), timeout=3)
                    conn.execute("DELETE FROM tasks WHERE status = 'completed'")
                    conn.commit()
                    cleaned += conn.total_changes
                    conn.close()
                except Exception:
                    pass

    # 시스템 AI 메모리 DB 도 정리
    sys_db = data_path / "system_ai_memory.db"
    if sys_db.exists():
        try:
            conn = sqlite3.connect(str(sys_db), timeout=3)
            conn.execute("DELETE FROM tasks WHERE status = 'completed'")
            conn.commit()
            cleaned += conn.total_changes
            conn.close()
        except Exception:
            pass

    if cleaned > 0:
        print(f"{tag} 이전 세션 완료 task {cleaned}건 정리")
    return True
