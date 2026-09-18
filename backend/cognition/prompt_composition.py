"""prompt_composition.py — 프롬프트 구성 표면 (2026-09-13)

에이전트마다 프롬프트가 *어떤 조각으로, 어떤 순서로, 어디서 와서* 조립되는지를 한 곳에서
보여준다. 시스템 AI·프로젝트 에이전트·의식·의식 감독·무의식·최종 평가자·경험 증류·가이드
순찰·IBL 번역·자동응답 … 은 전부 다르게 조립되는데, 그 조립문이 코드 여기저기에 흩어져
있어 "지금 이 에이전트가 무엇을 읽고 있나"를 사람이 볼 표면이 없었다.

원칙:
- **LLM 호출 0.** 조각을 만드는 데 쓰는 함수는 실제 조립 함수(prompt_builder·ibl_access·
  해마 회상 등)를 그대로 부른다 — 표면이 거짓말하면 안 되므로 요약본을 따로 짓지 않는다.
- 파일로 고정된 조각(kind=file)은 본문을 그대로, 실행기억처럼 턴마다 달라지는 조각(kind=
  memory/dynamic)은 *샘플 메시지 한 건*으로 실제 조립해 분량을 보인다. 실제 턴에서만 생기는
  조각(kind=turn — 도구 원장·응답 본문 등)은 자리와 상한만 적고 본문은 비운다.
- 조건부 조각(condition)은 이번 샘플에서 안 실리더라도 목록에 남긴다(included=False).
- 부작용 있는 로더는 피한다: 가이드는 `_guide_block`(주입 기록) 대신 `_load_guide_file`.

조각(section) 스키마:
  key, label, layer('system'|'turn'|'user'), kind('file'|'dynamic'|'memory'|'history'|'constant'|
  'turn'|'input'), source(경로 또는 함수), condition(None 또는 문장), included(bool),
  chars, tokens, content, note
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_utils import get_base_path

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE = "어제 찍은 사진 중 잘 나온 것만 골라 공유창고에 올려줘"


# ─── 토큰 추정 (prompt_benchmark.estimate_tokens 와 같은 식 — 한국어 비율 가중) ──────────

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    korean = sum(1 for c in text if '가' <= c <= '힣')
    total = len(text)
    ratio = korean / max(total, 1)
    return int(total / (4 - ratio * 2.5))


# ─── 조각 만들기 ─────────────────────────────────────────────────────────────────

def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(get_base_path()))
    except ValueError:
        return str(path)


def _section(key: str, label: str, layer: str, kind: str, source: str, content: str = "",
             condition: Optional[str] = None, included: bool = True, note: str = "") -> Dict[str, Any]:
    content = content or ""
    return {
        "key": key, "label": label, "layer": layer, "kind": kind, "source": source,
        "condition": condition, "included": bool(included),
        "chars": len(content), "tokens": estimate_tokens(content),
        "content": content, "note": note,
    }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _file_section(key: str, label: str, layer: str, rel: str, condition: Optional[str] = None,
                  included: bool = True, note: str = "") -> Dict[str, Any]:
    p = get_base_path() / rel
    content = _read(p)
    if not p.exists():
        note = (note + " " if note else "") + "(파일 없음)"
    return _section(key, label, layer, "file", rel, content, condition, included, note)


def _model_info(role: str) -> Dict[str, Any]:
    """모델 기어 해소 결과 — 키는 뺀다."""
    try:
        from model_resolver import resolve
        d = resolve(role) or {}
        return {"role": role, "provider": d.get("provider", ""), "model": d.get("model", ""),
                "tier": d.get("tier", ""), "axis": d.get("axis", ""), "source": d.get("source", "")}
    except Exception as e:  # noqa: BLE001 — 표면이므로 해소 실패도 보여준다
        return {"role": role, "error": str(e)}


# ─── 공유 조각(여러 에이전트가 같은 함수로 만든다) ───────────────────────────────

def _date_section() -> Dict[str, Any]:
    from datetime import datetime
    now = datetime.now()
    wd = ('월', '화', '수', '목', '금', '토', '일')[now.weekday()]
    txt = f"# 현재 시점\n현재 날짜: {now.year}년 {now.month:02d}월 {now.day:02d}일 {wd}요일"
    return _section("date", "현재 날짜", "system", "dynamic", "prompt_builder.PromptBuilder.build #0", txt,
                    note="날짜만 — 분 단위 시각은 캐시 prefix 를 깨므로 턴 컨텍스트로 옮겨져 있다.")


def _structure_section() -> Dict[str, Any]:
    from prompt_builder import get_system_structure_core
    core = get_system_structure_core()
    txt = f"<system_structure>\n{core}\n</system_structure>" if core else ""
    return _section("system_structure", "시스템 구조 (정체성 코어)", "system", "dynamic",
                    "data/system_docs/system_structure.md → prompt_builder.get_system_structure_core",
                    txt, note="CODEBASE_MAP 마커 구간은 빼고(guides/codebase_map.md 로 파생) 한 줄 포인터로 대체.")


def _ibl_env_section(allowed_nodes=None, project_path=None, agent_id=None, allowed_set=None,
                     compact=True) -> Dict[str, Any]:
    from ibl_access import build_environment
    try:
        env = build_environment(allowed_nodes=allowed_nodes, project_path=project_path, agent_id=agent_id,
                                allowed_set=allowed_set, compact=compact)
    except Exception as e:  # noqa: BLE001
        env = f"(IBL 환경 조립 실패: {e})"
    frag = "12_ibl_compact.md" if compact else "12_ibl_only.md"
    return _section("ibl_environment", "IBL 환경 (문법서 + 액션 카탈로그 + 관용구)", "system", "dynamic",
                    f"ibl_access.build_environment — data/common_prompts/fragments/{frag} + data/ibl_nodes.yaml",
                    env, note=("compact=True: 압축 문법서 + 노드별 액션 목록. " if compact else
                               "전체 문법서 + 전체 액션 카탈로그. ")
                    + "동료 에이전트·<goal_context>·<attempt_history> 도 여기 실린다(프로젝트 에이전트).")


def _recall_bundle(sample: str) -> str:
    """연상 묶음 — 실행자와 같은 공통 흐름(associative_recall, 채널 sample). 러너가 없으면 러너 없는 조립(심층기억만 빠진다)."""
    runner = None
    try:
        from system_ai_core import get_system_ai_runner
        runner = get_system_ai_runner()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[prompt_composition] 러너 없음, 러너 없는 조립으로: {e}")
    try:
        from associative_recall import begin
        return begin(runner, sample, channel="sample").route("THINK").text()
    except Exception as e:  # noqa: BLE001
        return f"(연상 조립 실패: {e})"


def _recall_section(sample: str, layer: str = "turn") -> Dict[str, Any]:
    return _section("execution_memory", "실행기억 (해마 회상 + 심층 지도·선택 기억 + 가이드 목차)", layer, "memory",
                    "associative_recall.begin → route — 공급원 정책 표 SOURCES(해마·심층·가이드·손발·수리·판정·세계)",
                    _recall_bundle(sample),
                    note="샘플 메시지로 실제 회상한 결과. 메시지마다 내용·분량이 달라진다(LLM 0, 임베딩 검색).")


def _now_section() -> Dict[str, Any]:
    from datetime import datetime
    return _section("now", "현재 시각", "turn", "dynamic", "prompt_builder._build_dynamic_context",
                    f"# 현재 시각\n{datetime.now().strftime('%Y-%m-%d %H:%M')}")


def _model_name_section(model_name: str) -> Dict[str, Any]:
    return _section("self_model", "자기 인식 (모델명)", "turn", "dynamic", "prompt_builder._build_dynamic_context",
                    f"# 자기 인식\n- AI 모델: {model_name}" if model_name else "",
                    included=bool(model_name))


def _guides_section() -> Dict[str, Any]:
    return _section("guide_files", "의식이 고른 가이드 본문", "turn", "dynamic",
                    "data/guides/<name>.md ← consciousness_output.guide_files (prompt_builder._guide_block)",
                    "", condition="THINK 경로에서 의식이 guide_files 를 지정한 턴",
                    included=False,
                    note="가이드마다 본문 전체 + 신선도 주석. 없는 가이드는 '# 가이드 본문 미제공' 목록으로.")


def _repair_section(layer: str = "turn") -> Dict[str, Any]:
    s = _file_section("repair_doctrine", "수리 턴 교리", layer, "data/common_prompts/fragments/13_repair.md",
                      condition="이 턴에 RED 그랜트(자기수리 허가)가 살아 있을 때", included=False)
    s["note"] = "실행자에게 직접 — 의식의 task_framing 을 거치지 않는다."
    return s


def _user_command_section(sample: str, include_think_note: bool = True) -> Dict[str, Any]:
    from prompt_builder import compile_user_command
    plain = compile_user_command(sample, None)
    note = ("EXECUTE·반사 경로: 원문 그대로. THINK 경로: 원문 뒤에 '— 다음 절차에 따라 수행하라:' 앵커를 "
            "끼우고 task_framing · 기준의 출처(criteria_contract) · 전문가의 선택 · 전제(assumptions) · "
            "쓸 수 있는 IBL 액션 + 상세 계약 · 수행 절차(hint) · 실행 초안(imagined_ibl, 기계 검증) · "
            "참고할 가이드 · 충족 기준이 차례로 붙는다." if include_think_note else "")
    return _section("user_command", "사용자 명령 (의식 보강 융합)", "user", "input",
                    "prompt_builder.compile_user_command", plain, note=note)


def _history_section(note: str) -> Dict[str, Any]:
    return _section("history", "대화 이력", "user", "history",
                    "conversation_db (프로젝트별) / history_checkpoint (긴 스레드 압축)", "",
                    note=note)


# ─── 에이전트별 조립 ───────────────────────────────────────────────────────────

def _assemble_system_ai(sample: str, variant: str = "") -> Dict[str, Any]:
    """시스템 AI(상주 실행 에이전트). variant: '' | 'forage' | 'appmaker'."""
    from prompt_builder import build_system_ai_prompt_split
    from system_ai_memory import load_user_profile

    base = get_base_path()
    git_enabled = (base / ".git").exists()
    profile = load_user_profile() or ""
    model = _model_info("system_ai")
    model_name = model.get("model", "")

    extra_role = ""
    allowed_set = None
    extra_sections: List[Dict[str, Any]] = []
    if variant == "forage":
        allowed_set = {"sense", "self", "table"}
        chunks = []
        for key, label, rel in (
            ("forage_role", "포식 역할", "data/forage_role.txt"),
            ("forage_guide", "포식 검색 가이드", "data/guides/forage_search.md"),
            ("web_landmarks", "웹 랜드마크 지도", "data/guides/web_landmarks.md"),
        ):
            s = _file_section(key, label, "system", rel, note="표면별 추가 역할 — '# Role (표면별 추가)' 아래에 ---로 이어 붙는다.")
            extra_sections.append(s)
            if s["content"]:
                chunks.append(s["content"])
        extra_role = "\n\n---\n\n".join(chunks)
    elif variant == "appmaker":
        s = _file_section("appmaker_role", "앱메이커 역할", "system", "data/appmaker_role.txt",
                          note="표면별 추가 역할 — '# Role (표면별 추가)' 아래.")
        extra_sections.append(s)
        extra_role = s["content"]

    sections: List[Dict[str, Any]] = [
        _date_section(),
        _file_section("base_prompt", "기본 프롬프트", "system", "data/common_prompts/base_prompt_v6.md"),
        _structure_section(),
        _file_section("git", "Git 규약", "system", "data/common_prompts/fragments/06_git.md",
                      condition="indiebizOS 루트에 .git 이 있을 때", included=git_enabled),
        _ibl_env_section(allowed_set=allowed_set, compact=True),
        _file_section("system_ai_delegation", "위임 규약 (시스템 AI → 프로젝트 에이전트)", "system",
                      "data/common_prompts/fragments/10_system_ai_delegation.md"),
    ]
    role_txt = _read(base / "data" / "system_ai_role.txt").strip()
    sections.append(_section("role", "역할 (# Role)", "system", "file", "data/system_ai_role.txt",
                             f"# Role\n{role_txt}" if role_txt else "", included=bool(role_txt),
                             condition="역할 파일이 비어 있지 않을 때",
                             note="조종실 설정 > 시스템 AI 역할 에서 편집."))
    if extra_role.strip():
        # 실제 조립은 표면별 추가 역할을 한 덩어리로 '# Role (표면별 추가)' 아래 둔다 — 파일별 조각은 그 내역.
        sections.append(_section("extra_role", "역할 (표면별 추가) — 아래 파일들의 결합", "system", "dynamic",
                                 "api_system_ai.forage_chat / chat_streams (extra_role)",
                                 f"# Role (표면별 추가)\n{extra_role.strip()}"))
        for es in extra_sections:
            es.update(included=False, condition="위 '표면별 추가' 조각의 구성 파일 — 결합돼 한 조각으로 실린다")
        sections.extend(extra_sections)
    sections.append(_section("system_memo", "시스템 메모 (# 시스템 메모)", "system", "memory",
                             "system_ai_memory.load_user_profile (영구 메모)",
                             f"# 시스템 메모\n{profile.strip()}" if profile.strip() else "",
                             included=bool(profile.strip()), condition="메모가 비어 있지 않을 때"))
    # 턴 컨텍스트
    sections += [
        _now_section(),
        _recall_section(sample),
        _model_name_section(model_name),
        _guides_section(),
        _repair_section(),
    ]
    # 사용자 메시지
    sections += [
        _history_section("시스템 AI 스레드의 이전 턴. THINK 경로에선 의식의 history_summary 로 치환된다."),
        _user_command_section(sample),
    ]

    # 실제 조립 총량 — 위 조각 목록이 아니라 진짜 빌더가 돌린 결과로 잰다(대조용).
    try:
        stable, dynamic = build_system_ai_prompt_split(
            user_profile=profile, git_enabled=git_enabled, consciousness_output=None,
            model_name=model_name, execution_memory=_first(sections, "execution_memory")["content"],
            extra_role=extra_role, allowed_set=allowed_set)
        assembled = {"stable_chars": len(stable), "dynamic_chars": len(dynamic),
                     "stable_tokens": estimate_tokens(stable), "dynamic_tokens": estimate_tokens(dynamic)}
    except Exception as e:  # noqa: BLE001
        assembled = {"error": str(e)}
    return {"model": model, "sections": sections, "assembled": assembled,
            "entry": "agent_pipeline._refresh_execution_prompt → agent_cognitive._build_system_ai_prompt_split "
                     "→ prompt_builder.build_system_ai_prompt_split"}


def _pick_project(project_id: Optional[str]):
    """프로젝트 + agents.yaml 첫 활성 에이전트. (project_path, agent_cfg, project_name)"""
    import yaml
    base = get_base_path()
    projects_dir = base / "projects"
    candidates: List[Path] = []
    if project_id:
        p = projects_dir / Path(project_id).name
        if p.is_dir():
            candidates.append(p)
    if not candidates:
        try:
            from safe_store import safe_load_json
            for row in safe_load_json(projects_dir / "projects.json", []) or []:
                if row.get("type", "project") == "project" and row.get("path"):
                    candidates.append(Path(row["path"]))
        except Exception:  # noqa: BLE001
            pass
        for p in sorted(projects_dir.iterdir()) if projects_dir.is_dir() else []:
            if p.is_dir() and (p / "agents.yaml").exists():
                candidates.append(p)
    for p in candidates:
        ay = p / "agents.yaml"
        if not ay.exists():
            continue
        try:
            data = yaml.safe_load(ay.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        agents = [a for a in (data.get("agents") or []) if isinstance(a, dict) and a.get("active", True)]
        if agents:
            return p, agents[0], len(agents), p.name
    return None, None, 0, ""


def list_projects() -> List[Dict[str, Any]]:
    """프로젝트 에이전트 조립을 볼 수 있는 프로젝트 목록(agents.yaml 에 활성 에이전트가 있는 것)."""
    import yaml
    base = get_base_path()
    projects_dir = base / "projects"
    out = []
    if not projects_dir.is_dir():
        return out
    for p in sorted(projects_dir.iterdir()):
        ay = p / "agents.yaml"
        if not p.is_dir() or not ay.exists():
            continue
        try:
            data = yaml.safe_load(ay.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        names = [a.get("name", "") for a in (data.get("agents") or []) if isinstance(a, dict) and a.get("active", True)]
        if names:
            out.append({"id": p.name, "name": p.name, "agents": names})
    return out


def _assemble_project_agent(sample: str, project_id: Optional[str]) -> Dict[str, Any]:
    from prompt_builder import build_agent_prompt_split, get_prompt_builder

    project_path, cfg, agent_count, project_name = _pick_project(project_id)
    if project_path is None:
        return {"model": {}, "sections": [], "assembled": {},
                "error": "agents.yaml 에 활성 에이전트가 있는 프로젝트가 없습니다."}
    agent_name = cfg.get("name", "에이전트")
    agent_id = cfg.get("id")
    allowed_nodes = cfg.get("allowed_nodes")
    git_enabled = (project_path / ".git").exists()
    role_file = project_path / f"agent_{agent_name}_role.txt"
    note_file = project_path / f"agent_{agent_name}_note.txt"
    role_text = _read(role_file) if role_file.exists() else ""
    notes_text = _read(note_file).strip() if note_file.exists() else ""
    model = _model_info("execution")
    model_name = cfg.get("model", "") or model.get("model", "")

    builder = get_prompt_builder()
    pm_block = builder._project_memory_block(str(project_path))
    try:
        import forage_doc
        pm_doc = forage_doc.doc_path_at(forage_doc.TREE_BODY, os.path.abspath(str(project_path)))
    except Exception:  # noqa: BLE001
        pm_doc = "data/forage_surveys/<body>/<프로젝트 절대경로>/memory.md"

    role_prompt = "\n".join([f"당신은 '{agent_name}'입니다."] + ([role_text] if role_text else []))
    sections: List[Dict[str, Any]] = [
        _date_section(),
        _file_section("base_prompt", "기본 프롬프트", "system", "data/common_prompts/base_prompt_v6.md"),
        _structure_section(),
        _file_section("git", "Git 규약", "system", "data/common_prompts/fragments/06_git.md",
                      condition="프로젝트 폴더에 .git 이 있을 때", included=git_enabled),
        _file_section("delegation", "위임 규약 (동료 에이전트)", "system", "data/common_prompts/fragments/09_delegation.md",
                      condition="프로젝트 활성 에이전트가 2명 이상이거나 시스템 AI 가 위임한 턴",
                      included=agent_count > 1),
        _ibl_env_section(allowed_nodes=allowed_nodes, project_path=str(project_path), agent_id=agent_id, compact=True),
        _section("project_memory", "프로젝트 포식 기억 (<project_memory>)", "system", "memory",
                 f"{_rel(Path(str(pm_doc)))} + forage_map 상속 단언 (prompt_builder._project_memory_block)",
                 pm_block, included=bool(pm_block), condition="프로젝트 폴더의 포식 문서가 있을 때",
                 note="프로젝트 에이전트의 CLAUDE.md 에 해당. 24KB 상한, 넘으면 잘림 표식."),
        _section("role", "역할 (# Role)", "system", "file", _rel(role_file),
                 f"\n# Role\n{role_prompt}", note="'당신은 <이름>입니다.' 한 줄 + agent_<이름>_role.txt 본문."),
        _section("notes", "노트 (# Notes)", "system", "file", _rel(note_file),
                 f"# Notes\n{notes_text}" if notes_text else "", included=bool(notes_text),
                 condition="agent_<이름>_note.txt 가 있을 때 (의료 프로젝트는 환자 차트가 라이브로 덧붙음)"),
        _now_section(),
        _recall_section(sample),
        _model_name_section(model_name),
        _guides_section(),
        _repair_section(),
        _history_section("프로젝트 스레드의 이전 턴. THINK 경로에선 의식의 history_summary 로 치환."),
        _user_command_section(sample),
    ]
    try:
        stable, dynamic = build_agent_prompt_split(
            agent_name=agent_name, role=role_text, agent_count=agent_count, agent_notes=notes_text,
            git_enabled=git_enabled, delegated_from_system_ai=False, ibl_only=True,
            allowed_nodes=allowed_nodes, project_path=str(project_path), agent_id=agent_id,
            consciousness_output=None, model_name=model_name,
            execution_memory=_first(sections, "execution_memory")["content"])
        assembled = {"stable_chars": len(stable), "dynamic_chars": len(dynamic),
                     "stable_tokens": estimate_tokens(stable), "dynamic_tokens": estimate_tokens(dynamic)}
    except Exception as e:  # noqa: BLE001
        assembled = {"error": str(e)}
    return {"model": model, "sections": sections, "assembled": assembled,
            "context": {"project": project_name, "agent": agent_name, "agent_count": agent_count,
                        "allowed_nodes": allowed_nodes},
            "entry": "agent_pipeline._refresh_execution_prompt → agent_cognitive._build_agent_prompt_split "
                     "→ prompt_builder.build_agent_prompt_split"}


def _assemble_consciousness(sample: str) -> Dict[str, Any]:
    from consciousness_agent import ConsciousnessAgent, get_world_pulse_text
    from system_ai_memory import load_user_profile

    model = _model_info("consciousness")
    role = _read(get_base_path() / "data" / "system_ai_role.txt").strip()
    notes = load_user_profile() or ""
    try:
        from system_ai_tools import get_all_system_ai_tools
        tools = [t.get("name", "") for t in get_all_system_ai_tools() if isinstance(t, dict) and t.get("name")]
    except Exception:  # noqa: BLE001
        tools = []
    recall = _recall_bundle(sample)
    pulse = get_world_pulse_text()

    sections: List[Dict[str, Any]] = [
        _file_section("consciousness_prompt", "의식 프롬프트", "system", "data/common_prompts/consciousness_prompt.md"),
        _structure_section(),
        _ibl_env_section(compact=False),
        _section("agent_block", "<agent> 역할 + 메모", "user", "memory",
                 "data/system_ai_role.txt (시스템 AI) 또는 agent_<이름>_role.txt / system_ai_memory 영구 메모",
                 _agent_block("시스템 AI", role, notes),
                 note="시스템 AI 기준. 프로젝트 에이전트면 그 에이전트의 역할 파일과 agents.yaml notes."),
        _section("world_pulse", "<world_pulse> 세계 상태", "user", "dynamic",
                 "data/guides/world_pulse.md (world_pulse_health 가 재생성)",
                 f"<world_pulse>\n{pulse}\n</world_pulse>" if pulse else "", included=bool(pulse)),
        _section("history", "<history> 대화 이력", "user", "history",
                 "conversation_db/system_ai_memory → history_excerpt → consciousness_agent._build_input", "",
                 note="이 샘플엔 이력이 없다. 실제 턴은 <turn index role>에 본문 또는 생략을 표시한 앞·뒤 발췌로 실린다. DB 발췌와 체크포인트를 의식 입구에서 다시 앞부분으로 자르지 않는다."),
        _section("execution_memory", "연상기억 (해마 + 지도)", "user", "memory",
                 "associative_recall — 실행자와 *같은* 묶음", recall,
                 note="실행자에게 가는 실행기억과 동일한 묶음이 의식 입력에도 실린다."),
        _section("available_tools", "<available_tools> 가용 도구", "user", "dynamic",
                 "system_ai_tools.get_all_system_ai_tools / agent_cognitive._get_available_tools",
                 _tools_block(tools) if tools else "", included=bool(tools)),
        _file_section("repair_doctrine", "<repair_doctrine> 수리 규정 규칙", "user",
                      "data/common_prompts/fragments/14_consciousness_repair.md",
                      condition="수리 턴(REPAIR 분류·RED 그랜트)에만", included=False),
        _section("framing_revision", "<framing_revision> 턴 안 재규정", "user", "turn",
                 "reframe.py — 실행자가 깨진 전제를 들고 되물은 경우", "",
                 condition="실행자가 reframe 도구를 부른 턴", included=False),
        _section("user_message", "<user_message>", "user", "input", "사용자 원문",
                 f"<user_message>\n{sample}\n</user_message>"),
    ]
    try:
        total_input = ConsciousnessAgent._build_input(
            None, user_message=sample, history=[], associative_memory=recall, world_pulse=pulse,
            agent_name="시스템 AI", agent_role=role, agent_notes=notes, available_tools=tools or None)
        sys_len = sum(s["chars"] for s in sections if s["layer"] == "system" and s["included"])
        assembled = {"stable_chars": sys_len,
                     "stable_tokens": sum(s["tokens"] for s in sections if s["layer"] == "system" and s["included"]),
                     "dynamic_chars": len(total_input), "dynamic_tokens": estimate_tokens(total_input)}
    except Exception as e:  # noqa: BLE001
        assembled = {"error": str(e)}
    return {"model": model, "sections": sections, "assembled": assembled,
            "entry": "cognitive_consciousness._run_consciousness → consciousness_agent.ConsciousnessAgent.process "
                     "(_load_prompt + _build_input); 감독이 살아 있으면 supervisor.plan 으로 위임",
            "output_keys": ["task_framing", "achievement_criteria", "expert_choice", "capability_focus",
                            "guide_files", "assumptions", "imagined_ibl", "needs_clarification", "needs_repair",
                            "history_summary"]}


def _agent_block(name: str, role: str, notes: str) -> str:
    parts = [f'<agent name="{name}">']
    if role:
        parts.append(f"<role>\n{role}\n</role>")
    if notes:
        parts.append(f"<notes>\n{notes}\n</notes>")
    parts.append("</agent>")
    return "\n".join(parts)


def _tools_block(tools: List[str]) -> str:
    return ("<available_tools note=\"hint 에서 도구 이름을 부를 땐 이 목록 안에서만 골라라. "
            "이외 도구를 추천하면 실행 에이전트가 도구를 찾지 못해 헛걸음한다.\">\n"
            f"{', '.join(tools)}\n</available_tools>")


def _assemble_supervisor(sample: str) -> Dict[str, Any]:
    import supervisor_runtime as SR
    model = _model_info("consciousness")
    # 계획 단계의 시스템 프롬프트 = 의식 항목의 3조각 그대로. 본문은 '의식' 항목에서 보고 여기선 분량만.
    stack_chars = 0
    try:
        stack_chars = sum(len(x) for x in (
            _read(get_base_path() / "data" / "common_prompts" / "consciousness_prompt.md"),
            _structure_section()["content"], _ibl_env_section(compact=False)["content"]))
    except Exception:  # noqa: BLE001
        pass
    stack = _section("consciousness_stack", "[계획 단계] 의식 프롬프트 전체", "system", "dynamic",
                     "consciousness_agent.ConsciousnessAgent._prompt (의식 항목과 동일 3조각)", "",
                     note="계획(plan)·재규정(reframe) 단계는 '의식' 항목의 시스템 프롬프트를 그대로 쓰고 아래 계획 도구 지침을 덧붙인다. 본문은 '의식' 항목에서.")
    stack.update(chars=stack_chars, tokens=int(stack_chars / 3.3), ref_agent="consciousness")
    sections = [
        stack,
        _section("planning_tool_prompt", "[계획 단계] 계획 도구 지침", "system", "constant",
                 "supervisor_runtime.PLANNING_TOOL_PROMPT", SR.PLANNING_TOOL_PROMPT),
        _section("role_prompt", "[검토 단계] 감독자 역할", "system", "constant",
                 "supervisor_runtime.ROLE_PROMPT", SR.ROLE_PROMPT,
                 note="중간관리(review) 호출의 시스템 프롬프트 — supervision 도구 하나로 state/evidence/execute."),
        _section("receipt_prompt", "[영수증 단계] 인용 확인", "system", "constant",
                 "supervisor_runtime.RECEIPT_PROMPT", SR.RECEIPT_PROMPT,
                 condition="내용 검수는 승인됐지만 인용 구간 읽기 기록이 빠진 경우", included=False),
        _section("plan_input", "[계획 단계] 의식 입력", "user", "dynamic",
                 "consciousness_agent.ConsciousnessAgent._build_input — '의식' 항목의 입력 조각들", "",
                 note="의식 항목의 user 층과 동일."),
        _section("state_json", "[검토 단계] 상태 JSON", "user", "turn",
                 "conscious_supervisor.ConsciousSupervisor.state — original_goal·framing·phase·checkpoint·"
                 "elapsed·최근 사건 로그·evidence 색인·job 상태", "",
                 note="{\"trigger\": <사유>, ...state} — 턴마다 하네스가 채운다."),
        _section("tool_context", "tool_context (가용 액션·도구·관용구)", "user", "dynamic",
                 "supervisor_runtime.tool_context — ibl_access.load_nodes_raw 필터 + 도구 설명 + 관용구 지도", "",
                 note="계획·검토 단계 모두 입력 끝에 'tool_context=' JSON 으로 붙는다."),
    ]
    return {"model": model, "sections": sections, "assembled": {},
            "entry": "conscious_supervisor.ConsciousSupervisor.plan / review / reframe → supervisor_runtime.invoke"}


def _assemble_unconscious(sample: str) -> Dict[str, Any]:
    from consciousness_agent import get_unconscious_prompt
    model = _model_info("classify")
    sections = [
        _section("unconscious_prompt", "무의식 프롬프트", "system", "file",
                 "data/common_prompts/unconscious_prompt.md (consciousness_agent.get_unconscious_prompt)",
                 get_unconscious_prompt()),
        _section("user_message", "사용자 원문", "user", "input", "사용자 메시지 그대로", sample,
                 note="분류기는 원문만 본다 — 이력·기억 없음. 해마 점수 ≥ 0.85 면 분류 자체를 건너뛴다(반사)."),
    ]
    return {"model": model, "sections": sections, "assembled": {},
            "entry": "cognitive_consciousness._classify_request → consciousness_agent.oneshot_ai_call(role='classify')",
            "output_keys": ["EXECUTE", "THINK", "REPAIR", "SESSION_RESET", "CONTEXT_UPDATE"]}


def _assemble_evaluator(sample: str) -> Dict[str, Any]:
    from cognitive_eval import CognitiveEvalMixin
    import final_evaluator as FE
    from supervisor_handoff import criteria_contract
    model = _model_info("evaluate")
    example_contract = json.dumps(criteria_contract(sample, {"achievement_criteria": "(의식이 정한 기준)"}),
                                  ensure_ascii=False)
    sections = [
        _section("evaluator_prompt", "평가자 프롬프트", "system", "file",
                 "data/common_prompts/evaluator_prompt.md (cognitive_eval._load_evaluator_prompt)",
                 CognitiveEvalMixin._load_evaluator_prompt(),
                 note="클래스 캐시 — 파일을 고치면 백엔드 재기동 뒤 반영."),
        _section("final_policy", "최종 평가 정책", "system", "constant", "final_evaluator.POLICY", FE.POLICY,
                 note="도구 없는 최종 평가 호출에만 덧붙는다."),
        _section("user_request", "## 사용자 요청", "user", "input", "사용자 원문", f"## 사용자 요청\n{sample}"),
        _section("criteria", "## 달성 기준 (criteria_contract)", "user", "turn",
                 "supervisor_handoff.criteria_contract ← 의식의 achievement_criteria",
                 f"## 달성 기준\n{example_contract}",
                 note="예시 형태. 실제 기준은 의식이 그 턴에 확정한 것."),
        _section("scheduled_repair", "지연 적용 예약 주석", "user", "turn", "cognitive_eval._scheduled_repair_note", "",
                 condition="지연 적용이 예약된 수리 턴", included=False),
        _section("action_ledger", "## 실제 실행된 액션 원장", "user", "turn",
                 "cognitive_trace.build_action_ledger(tool_calls)", "",
                 note="호출 로그에서 뽑은 전수 목록 — 에이전트 서술이 아니라 사실. 분량은 턴의 호출 수에 비례."),
        _section("history_summary", "## 기준 해석용 이전 대화", "user", "history",
                 "consciousness_output.history_summary", "", condition="의식이 history_summary 를 낸 턴", included=False),
        _section("tool_results", "## 도구 실행 결과", "user", "turn",
                 "cognitive_trace.serialize_tool_trace", "",
                 note="실행 트레이스 직렬화. 분량은 턴마다 다름."),
        _section("response", "## 에이전트 응답", "user", "turn", "실행자의 최종 응답 본문", "",
                 note="중간 평가는 8,000자 상한, 최종 평가(full_response)는 전체."),
        _section("evaluation_context", "## 하네스가 수집한 평가 맥락", "user", "turn",
                 "final_evaluator.prepare — 본문·지문·수량 검사(quantity_checks)·공개 대기열", "",
                 condition="최종 평가 패킷이 있을 때", included=False),
        _section("created_files", "## 생성된 파일 내용", "user", "turn",
                 "cognitive_eval._collect_created_files", "", condition="턴이 파일을 만들었을 때", included=False),
        _section("visual_artifacts", "## 시각 산출물 검수 (+이미지 첨부)", "user", "turn",
                 "cognitive_eval._collect_visual_artifacts", "", condition="이미지·렌더 산출물이 있을 때 (비전 모델로)", included=False),
        _section("closing", "판정 지시", "user", "constant", "cognitive_eval._evaluate_achievement",
                 "위 증거로 명시된 기준의 충족 여부만 판정하세요."),
    ]
    return {"model": model, "sections": sections, "assembled": {},
            "entry": "final_evaluator.prepare/invoke → cognitive_eval.CognitiveEvalMixin._evaluate_achievement "
                     "→ consciousness_agent.system_ai_call(role='evaluate')",
            "output_keys": ["ACHIEVED", "NOT_ACHIEVED (SEVERITY·REPAIR_SCOPE·DEFECTS)", "UNKNOWN"]}


def _assemble_distill(sample: str) -> Dict[str, Any]:
    from ibl_usage_rag import _build_distill_prompt
    model = _model_info("background")
    try:
        import hippo_tree
        topic_map = hippo_tree.map_text() or ""
    except Exception as e:  # noqa: BLE001
        topic_map = f"(지도 조립 실패: {e})"
    placeholder_log = "(실행 원문 — 이 턴에 실제로 실행된 IBL 문장들이 번호와 함께 실린다)"
    prompt = _build_distill_prompt(sample, placeholder_log, "", topic_map)
    sections = [
        _file_section("reflection_prompt", "반성 프롬프트", "system", "data/common_prompts/reflection_prompt.md"),
        _section("distill_prompt", "증류 지시 (사용자 명령 + 실행 원문 + 주제 지도)", "user", "dynamic",
                 "ibl_usage_rag._build_distill_prompt", prompt,
                 note="실행 원문 자리는 자리표. 주제 지도(hippo_tree.map_text)는 실제 값."),
        _section("tool_log", "실행 원문 (source_ids)", "user", "turn", "턴의 execute_ibl 호출 기록", "",
                 note="위 증류 지시 안에 번호 붙은 문장으로 삽입된다."),
        _section("retry_block", "재시도 블록", "user", "turn", "ibl_usage_rag.distill_experience", "",
                 condition="첫 증류 응답이 관문(hippo_syntax_gate 등)에 걸렸을 때", included=False),
    ]
    return {"model": model, "sections": sections, "assembled": {},
            "entry": "ibl_usage_rag.distill_experience → oneshot_ai_call(role='background')"}


def _assemble_deep_memory(sample: str) -> Dict[str, Any]:
    model = _model_info("background")
    sections = [
        _section("system", "시스템 한 줄", "system", "constant", "cognitive_distill._distill_deep_memory",
                 "사실 정보만 추출하라. JSON 배열로만 응답."),
        _section("extract_prompt", "추출 지시 (오늘 날짜 + 사용자 원문 + 응답)", "user", "turn",
                 "cognitive_distill._distill_deep_memory (f-string)", "",
                 note="사용자 원문에서 지속 가치가 있는 사실만 고른다. 도구 초안은 입력이 아니다."),
        _section("relation_judge", "관계 판정 (후속 호출)", "user", "turn",
                 "cognitive_distill (기억 관계 판정기) — 기존 기억과의 중복·갱신 판정", "",
                 condition="추출된 사실이 있을 때", included=False),
    ]
    return {"model": model, "sections": sections, "assembled": {},
            "entry": "cognitive_distill._distill_deep_memory (응답 뒤 백그라운드)"}


def _assemble_history_checkpoint(sample: str) -> Dict[str, Any]:
    import history_checkpoint as HC
    model = _model_info("background")
    sections = [
        _section("system", "압축기 시스템 프롬프트", "system", "constant", "history_checkpoint._SYSTEM_PROMPT",
                 HC._SYSTEM_PROMPT),
        _section("prompt", "기존 체크포인트 + 밀려나는 턴 + 규칙", "user", "dynamic",
                 "history_checkpoint._build_prompt", HC._build_prompt(None, [("user", sample)]),
                 note="밀려나는 턴은 자리표 한 줄(샘플). 행당 상한 있음."),
    ]
    return {"model": model, "sections": sections, "assembled": {},
            "entry": "history_checkpoint — 긴 스레드가 창 밖으로 밀릴 때"}


def _assemble_guide_maintenance(sample: str) -> Dict[str, Any]:
    import guide_audit as GA
    import guide_downscale as GD
    import guide_feedback as GF
    model = _model_info("guide_audit")
    sections = [
        _section("audit_sys", "[의미 순찰] 시스템", "system", "constant", "guide_audit._SYS", GA._SYS),
        _section("audit_prompt", "[의미 순찰] 가이드 본문 + 라이브 액션 목록 + 가이드 목록", "user", "dynamic",
                 "guide_audit._audit_one — data/guides/<x>.md + data/ibl_nodes.yaml + data/guide_db.json", "",
                 note="주 1회, 신선도 낮은 가이드 6개씩."),
        _section("downscale_sys", "[야간 축소] 시스템", "system", "constant", "guide_downscale._SYS", GD._SYS),
        _section("downscale_prompt", "[야간 축소] 가이드 + 표식 + 예산", "user", "dynamic",
                 "guide_downscale._prompt", "", condition="가이드가 36KB 예산을 넘을 때", included=False),
        _section("feedback_sys", "[턴 뒤 되먹임] 시스템", "system", "constant", "guide_feedback._SYS", GF._SYS),
        _section("feedback_prompt", "[턴 뒤 되먹임] 가이드 본문 + 사용자 메시지 + 응답 + 실행 액션", "user", "turn",
                 "guide_feedback._review_one (본문 상한 MAX_GUIDE_CHARS)", "",
                 condition="턴이 가이드를 실제로 읽고 썼을 때, 30일 쿨다운", included=False),
    ]
    return {"model": model, "sections": sections, "assembled": {},
            "entry": "guide_audit / guide_downscale / guide_feedback → oneshot(role='guide_audit')"}


def _assemble_translator(sample: str) -> Dict[str, Any]:
    import ibl_translate as IT
    model = _model_info("translate")
    spec = IT.load_ibl_spec()
    try:
        from ibl_usage_rag import IBLUsageRAG
        refs = IBLUsageRAG().get_references(sample) or ""
    except Exception as e:  # noqa: BLE001
        refs = f"(용례 검색 실패: {e})"
    sections = [
        _section("task", "번역 역할", "system", "constant", "ibl_translate.IBL_TRANSLATE_TASK", IT.IBL_TRANSLATE_TASK),
        _section("ibl_spec", "<ibl_spec> IBL 정식 교재", "system", "file",
                 "data/common_prompts/fragments/12_ibl_only.md (ibl_translate.load_ibl_spec)", spec),
        _section("references", "참고 용례 (해마)", "user", "memory", "ibl_usage_rag.IBLUsageRAG.get_references",
                 refs if isinstance(refs, str) else json.dumps(refs, ensure_ascii=False)),
        _section("intent", "번역할 의도", "user", "input", "사용자 원문", sample),
    ]
    return {"model": model, "sections": sections, "assembled": {},
            "entry": "POST /ibl/translate (api_ibl) · body_ask._compile_cockpit"}


def _assemble_autoresponse(sample: str) -> Dict[str, Any]:
    # auto_response 는 services 층(위층) — 여기서 import 하지 않는다(층 가드). 경로·조각은 명세로만 적는다.
    sections = [
        _file_section("system", "자동응답 기본 프롬프트", "system", "data/common_prompts/base_prompt_autoresponse.md"),
        _section("context", "<context> 근무지침·비즈니스 문서·카테고리·내 창고·대화 이력", "user", "dynamic",
                 "auto_response.AutoResponseEngine._build_user_prompt", "",
                 note="이웃(이메일·Nostr)에서 온 메시지에 답할 때. 모델 기어를 거치지 않고 도구 가능한 프로바이더를 직접 고른다."),
        _section("incoming", "<incoming_message> 받은 메시지", "user", "input", "채널 폴러가 넘긴 메시지", sample),
        _section("instructions", "<instructions>", "user", "constant", "auto_response._build_user_prompt", ""),
    ]
    return {"model": {"role": "(기어 밖)", "note": "도구 호출 가능한 프로바이더를 자체 선택"},
            "sections": sections, "assembled": {},
            "entry": "auto_response.AutoResponseEngine._call_ai_with_tools"}


def _first(sections: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    for s in sections:
        if s["key"] == key:
            return s
    return {"content": ""}


# ─── 에이전트 목록 (표면 정본) ───────────────────────────────────────────────────

AGENTS: List[Dict[str, Any]] = [
    {"id": "system_ai", "label": "시스템 AI", "group": "실행", "role": "system_ai",
     "summary": "상주 실행 에이전트. 조종실·자율주행의 사용자 대화를 받는다.",
     "build": lambda s, p: _assemble_system_ai(s)},
    {"id": "project_agent", "label": "프로젝트 에이전트", "group": "실행", "role": "execution",
     "summary": "프로젝트 폴더의 에이전트. 조립은 한 종류 — 역할·노트·포식 기억·허용 노드만 다르다.",
     "needs_project": True, "build": lambda s, p: _assemble_project_agent(s, p)},
    {"id": "system_ai_forage", "label": "포식 표면 (시스템 AI 변형)", "group": "실행", "role": "system_ai",
     "summary": "포식 브라우저의 시스템 AI. 역할에 포식 지침·랜드마크가 덧붙고 노드는 sense·self·table 로 좁혀진다. 무의식·의식 생략.",
     "build": lambda s, p: _assemble_system_ai(s, "forage")},
    {"id": "system_ai_appmaker", "label": "앱메이커 (시스템 AI 변형)", "group": "실행", "role": "system_ai",
     "summary": "앱 만들기 표면의 시스템 AI. 앱메이커 역할이 덧붙는다.",
     "build": lambda s, p: _assemble_system_ai(s, "appmaker")},
    {"id": "consciousness", "label": "의식", "group": "인지", "role": "consciousness",
     "summary": "THINK 턴의 문제 규정·달성 기준·전문가의 선택·실행 초안. 출력은 실행자의 사용자 명령에 융합된다.",
     "build": lambda s, p: _assemble_consciousness(s)},
    {"id": "supervisor", "label": "의식 감독", "group": "인지", "role": "consciousness",
     "summary": "계획·재규정·중간관리(검토)·인용 영수증. 감독 버스가 살아 있으면 의식 호출을 대신 받는다.",
     "build": lambda s, p: _assemble_supervisor(s)},
    {"id": "unconscious", "label": "무의식 (분류)", "group": "인지", "role": "classify",
     "summary": "매 턴 첫 관문 — EXECUTE / THINK / REPAIR 분류. 원문만 본다.",
     "build": lambda s, p: _assemble_unconscious(s)},
    {"id": "evaluator", "label": "최종 평가자", "group": "인지", "role": "evaluate",
     "summary": "도구 없는 원샷. 의식이 명시한 기준만 하네스가 모은 증거로 판정.",
     "build": lambda s, p: _assemble_evaluator(s)},
    {"id": "distill", "label": "경험 증류 (해마)", "group": "배경", "role": "background",
     "summary": "성공한 턴의 실행 원문에서 재사용할 문장을 골라 해마에 넣는다.",
     "build": lambda s, p: _assemble_distill(s)},
    {"id": "deep_memory", "label": "심층기억 추출", "group": "배경", "role": "background",
     "summary": "응답 뒤 사용자 원문에서 지속 가치가 있는 사실을 뽑는다.",
     "build": lambda s, p: _assemble_deep_memory(s)},
    {"id": "history_checkpoint", "label": "대화 이력 압축", "group": "배경", "role": "background",
     "summary": "긴 스레드에서 밀려나는 턴을 체크포인트 하나로 요약.",
     "build": lambda s, p: _assemble_history_checkpoint(s)},
    {"id": "guide_maintenance", "label": "가이드 순찰 3종", "group": "배경", "role": "guide_audit",
     "summary": "의미 순찰(주 1회)·야간 축소(예산 초과)·턴 뒤 되먹임.",
     "build": lambda s, p: _assemble_guide_maintenance(s)},
    {"id": "translator", "label": "IBL 번역기 (조종실)", "group": "서비스", "role": "translate",
     "summary": "조종실 수동 모드의 자연어 → IBL 컴파일. 몸 간 부탁(body_ask)도 같은 조립.",
     "build": lambda s, p: _assemble_translator(s)},
    {"id": "autoresponse", "label": "자동응답 (이웃 메시지)", "group": "서비스", "role": "",
     "summary": "이메일·Nostr 로 온 이웃 메시지에 근무지침·비즈니스 문서로 응대.",
     "build": lambda s, p: _assemble_autoresponse(s)},
]

# 프롬프트 없는(LLM 0) 배경 순찰 — 표면에서 '프롬프트 없음'으로 구분해 보여준다.
NO_PROMPT_JOBS = ["doc_drift (문서 부패 감사)", "world_pulse_health (IBL 건강 점검)", "vocab_overlap_audit",
                  "corpus_vocab_audit", "weekly_audits", "fixture_sweeps"]


def list_agents() -> Dict[str, Any]:
    return {
        "agents": [{k: v for k, v in a.items() if k != "build"} for a in AGENTS],
        "no_prompt_jobs": NO_PROMPT_JOBS,
        "projects": list_projects(),
        "default_sample": DEFAULT_SAMPLE,
    }


def assemble(agent_id: str, sample: str = "", project_id: Optional[str] = None) -> Dict[str, Any]:
    sample = (sample or "").strip() or DEFAULT_SAMPLE
    for a in AGENTS:
        if a["id"] == agent_id:
            result = a["build"](sample, project_id)
            result.update({"agent": {k: v for k, v in a.items() if k != "build"}, "sample": sample})
            secs = result.get("sections") or []
            result["totals"] = {
                layer: {
                    "chars": sum(s["chars"] for s in secs if s["layer"] == layer and s["included"]),
                    "tokens": sum(s["tokens"] for s in secs if s["layer"] == layer and s["included"]),
                    "count": sum(1 for s in secs if s["layer"] == layer),
                } for layer in ("system", "turn", "user")
            }
            return result
    raise KeyError(agent_id)
