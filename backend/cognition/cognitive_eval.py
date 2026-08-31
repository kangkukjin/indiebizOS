"""
cognitive_eval.py - Goal 평가 루프 믹스인
IndieBiz OS Core

agent_cognitive.py 에서 분리(2026-07-17, 1500줄 규칙 모듈화). 의식 에이전트의
달성 기준(achievement_criteria) 기반 자동 평가 — 기준 추출, 생성 파일/시각
산출물 수집, 평가자 호출(_evaluate_achievement), 재실행 루프(_run_goal_evaluation_stream —
제너레이터: 재실행 이벤트를 그대로 흘린다, 2026-08-22).
trace 직렬화·액션 원장은 cognitive_trace 모듈 함수를 쓴다.
★consciousness_output 키 소비처 — scripts/consciousness_schema_check.py CONSUMER_FILES 등록.
"""

import re
from pathlib import Path
from typing import Optional, List, Dict, Any

from cognitive_trace import (
    serialize_tool_trace,
    build_action_ledger,
    _FILE_PATH_INPUT_KEYS,
    _FILE_WRITE_TOOL_NAMES,
)

# 판정 줄 매칭 — 줄 앞의 마크다운 장식(**, ##, >, 백틱, 괄호 등)을 관통해
# ACHIEVED / NOT_ACHIEVED 로 *시작*하는 줄을 찾는다. NOT 변형(NOT ACHIEVED,
# NOT-ACHIEVED)도 흡수. 대안 순서상 NOT 쪽을 먼저 둬야 ACHIEVED 부분매칭에 안 먹힌다.
_VERDICT_LINE_RE = re.compile(
    r"^[\s*_#>\"'`\[\(-]*(NOT[\s_-]?ACHIEVED|ACHIEVED)\b", re.IGNORECASE)
_VERDICT_WORD_RE = re.compile(r"\bNOT[\s_-]?ACHIEVED\b|\bACHIEVED\b", re.IGNORECASE)
_SEVERITY_RE = re.compile(r"SEVERITY\s*[:：]\s*([123])", re.IGNORECASE)


def parse_eval_verdict(text: str) -> tuple:
    """평가자 응답에서 (achieved: bool, severity: int)를 관용적으로 파싱한다.

    프롬프트는 '첫 줄에 ACHIEVED/NOT_ACHIEVED만'을 지시하지만, 평가자가 에이전틱
    프로바이더(claude_code 등 도구 사용)로 돌면 최종 응답이 서사체가 되어 판정이
    서두 문장 뒤 마크다운 볼드(**ACHIEVED**)로 밀려나는 일탈이 실측됨(에피소드 812 —
    첫 줄만 보던 옛 파서가 ACHIEVED 를 NOT_ACHIEVED 로 오판해 불필요한 재실행 발동).
    지시 강화로는 못 막으므로 파서가 흡수한다:
      1차: 판정 토큰으로 시작하는 첫 줄 (장식 관통)
      2차: 본문 어디든 첫 판정 토큰 등장
      3차: 판정 토큰 부재 → 통과 (기존 '평가 스킵=통과' 편향과 일치 —
           잘못된 NOT_ACHIEVED 는 전체 재실행 낭비를 부른다)
    severity 는 NOT_ACHIEVED 일 때 본문 전체에서 SEVERITY: n 탐색 (미표기=2).
    """
    achieved = None
    for line in text.strip().split('\n'):
        m = _VERDICT_LINE_RE.match(line.strip())
        if m:
            achieved = not m.group(1).upper().startswith("NOT")
            break
    if achieved is None:
        m = _VERDICT_WORD_RE.search(text)
        achieved = (m is None) or not m.group(0).upper().startswith("NOT")

    severity = 0
    if not achieved:
        m = _SEVERITY_RE.search(text)
        severity = int(m.group(1)) if m else 2  # 미표기 시 중간값
    return achieved, severity


class CognitiveEvalMixin:
    """Goal 평가 루프 — 의식 에이전트의 달성 기준 기반 자동 평가 메서드 모음."""

    def _extract_achievement_criteria(self, consciousness_output: dict,
                                       tool_results_str: str = "") -> Optional[str]:
        """의식 에이전트 출력에서 달성 기준을 추출한다.

        1차: achievement_criteria 필드 (별도 필드)
        2차: task_framing에서 "달성 기준:" 이후 텍스트 (하위 호환)
        3차: 도구 실행 결과에 박힌 [ACHIEVEMENT_CRITERIA:node:action] ... [/ACHIEVEMENT_CRITERIA]
             마커 — 액션 메타데이터 자동 보강 (ibl_actions.yaml의 achievement_criteria 필드)
        """
        # 1차: consciousness_output의 별도 필드
        if consciousness_output:
            criteria = consciousness_output.get("achievement_criteria", "")
            if isinstance(criteria, list):
                criteria = ", ".join(str(c) for c in criteria if c)
            if criteria and isinstance(criteria, str) and criteria.strip():
                return criteria.strip()

            # 2차: task_framing에서 추출 (하위 호환)
            task_framing = consciousness_output.get("task_framing", "")
            if "달성 기준:" in task_framing:
                return task_framing.split("달성 기준:")[-1].strip().rstrip(".")
            if "달성기준:" in task_framing:
                return task_framing.split("달성기준:")[-1].strip().rstrip(".")

        # 3차: 도구 실행 결과에 박힌 액션 메타 마커 (achievement_criteria 마커 등)
        if tool_results_str:
            marker_pat = re.compile(
                r"\[ACHIEVEMENT_CRITERIA:([^\]]+)\]\s*(.+?)\s*\[/ACHIEVEMENT_CRITERIA\]",
                re.DOTALL,
            )
            matches = marker_pat.findall(tool_results_str)
            if matches:
                # 여러 액션이 연달아 실행되면 모든 criteria를 묶음
                parts = [f"[{action}] {body.strip()}" for action, body in matches]
                return "\n".join(parts)

        return None

    def _collect_created_files(self, response: str,
                                tool_calls: Optional[List[Dict[str, Any]]] = None) -> str:
        """생성/수정된 파일 경로를 찾아 내용을 읽는다.

        1차: tool_calls(있으면)에서 Write/Edit/MultiEdit/NotebookEdit 같은 파일 변경 도구의
             input.file_path 등을 직접 수집. IBL execute_ibl `[self:write]` 같은 케이스도
             input.params.path 등에서 추출. 응답 텍스트에 안 보여도 누락 안 됨.
        2차: 응답 텍스트에서 절대 경로 정규식 fallback — 1차에서 못 찾은 경로 보강용.

        Args:
            response: 에이전트 최종 응답 텍스트
            tool_calls: `{name, input, result, ...}` 리스트 (선택)
        """
        import os

        paths_seen: List[str] = []
        seen_set: set = set()

        def _add(path: str):
            if path and path not in seen_set and path.startswith("/"):
                seen_set.add(path)
                paths_seen.append(path)

        # 1차: tool_calls에서 직접 수집
        if tool_calls:
            for entry in tool_calls:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name") or entry.get("tool_name") or ""
                inp = entry.get("input") or {}
                if not isinstance(inp, dict):
                    continue

                # 표준 Write/Edit 류
                if name in _FILE_WRITE_TOOL_NAMES or name.endswith("/Write") or name.endswith("/Edit"):
                    for key in _FILE_PATH_INPUT_KEYS:
                        v = inp.get(key)
                        if isinstance(v, str):
                            _add(v)

                # IBL self:write 같은 케이스: execute_ibl({node:"self", action:"write", params:{path:...}})
                if name in ("execute_ibl", "mcp__indiebizos__execute_ibl"):
                    params = inp.get("params") or {}
                    if isinstance(params, dict):
                        for key in _FILE_PATH_INPUT_KEYS:
                            v = params.get(key)
                            if isinstance(v, str):
                                _add(v)

        # 2차: 응답 텍스트에서 절대 경로 fallback (1차에서 못 잡은 경우 보강)
        path_pattern = re.compile(r'(/[^\s"\'<>]+\.\w{1,10})')
        for p in path_pattern.findall(response or ""):
            _add(p)

        files_content = []
        for path in paths_seen:
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if len(content) > 10000:
                        content = content[:10000] + "\n\n... (10000자 초과, 생략됨)"
                    files_content.append(f"### {os.path.basename(path)} ({path})\n```\n{content}\n```")
                except Exception:
                    pass

        return "\n\n".join(files_content) if files_content else ""

    _VISUAL_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp", ".gif": "image/gif"}

    def _collect_visual_artifacts(self, response: str,
                                   tool_calls: Optional[List[Dict[str, Any]]] = None,
                                   max_images: int = 3) -> List[Dict[str, str]]:
        """생성된 시각 산출물(이미지)을 멀티모달 평가용으로 수집한다 (G 루프 보편 백스톱).

        _collect_created_files는 파일을 UTF-8 텍스트로 읽어 이미지를 조용히 버린다 —
        이게 평가자가 픽셀을 못 보던 물리적 원인. 여기서는 이미지 경로를 따로 모아
        base64로 인코딩해 평가자(경량 비전 모델)가 직접 보게 한다.

        수집원: tool_calls의 input(파일 경로 키)·result(산출 경로, 예 image_path)·응답 텍스트.
        반환: [{"base64","media_type","_path"}], 최신순 max_images개.
        """
        import os, base64 as _b64
        cand: List[str] = []
        seen: set = set()

        def _add(p):
            if (isinstance(p, str) and p.startswith("/")
                    and os.path.splitext(p)[1].lower() in self._VISUAL_EXTS
                    and p not in seen):
                seen.add(p)
                cand.append(p)

        img_re = re.compile(r'(/[^\s"\'<>]+\.(?:png|jpe?g|webp|gif))', re.IGNORECASE)

        if tool_calls:
            for entry in tool_calls:
                if not isinstance(entry, dict):
                    continue
                inp = entry.get("input") or {}
                if isinstance(inp, dict):
                    for key in _FILE_PATH_INPUT_KEYS:
                        _add(inp.get(key))
                    params = inp.get("params")
                    if isinstance(params, dict):
                        for key in _FILE_PATH_INPUT_KEYS:
                            _add(params.get(key))
                res = entry.get("result")
                if isinstance(res, str):
                    for m in img_re.findall(res):
                        _add(m)

        for m in img_re.findall(response or ""):
            _add(m)

        # 실존+크기 검증을 max_images 슬라이스 *전에* 수행 — 그래야 상한이 진짜
        # 이미지에만 쓰인다. (상대경로 'slides/s.png' 안의 '/s.png' 조각 같은 가짜
        # 후보가 창을 갉아먹어 실제 이미지가 덜 첨부되던 것을 막는다.)
        valid = [p for p in cand
                 if os.path.isfile(p) and os.path.getsize(p) <= 6 * 1024 * 1024]
        # 최신순 max_images개 (마지막 산출물이 보통 최종본)
        chosen = valid[-max_images:] if len(valid) > max_images else valid
        artifacts: List[Dict[str, str]] = []
        for path in chosen:
            try:
                with open(path, "rb") as f:
                    b64 = _b64.b64encode(f.read()).decode("utf-8")
                mt = self._VISUAL_EXTS.get(os.path.splitext(path)[1].lower(), "image/png")
                artifacts.append({"base64": b64, "media_type": mt, "_path": path})
            except Exception:
                pass
        if len(valid) > len(artifacts) and artifacts:
            self._log(f"[GoalEval] 시각 산출물 {len(valid)}개 중 {len(artifacts)}개만 평가 첨부(상한)")
        return artifacts

    # 예약이 이보다 오래 apply_scheduled 로 남아 있으면 수행자(red_apply) 좌초로 보고
    # 주입하지 않는다 — red_report.SCHEDULED_STALE_S 와 같은 값(그쪽이 좌초 재보고를 맡는다).
    _SCHEDULED_FRESH_S = 30 * 60

    def _scheduled_repair_note(self) -> str:
        """이 턴에 걸린 backend 지연 적용 예약을 평가자용 사실 문단으로 만든다 (없으면 "").

        ★왜(2026-08-31, ep2386 실측): backend/*.py 가 낀 수리는 검증 통과 후 라이브 쓰기가
        턴 종료 뒤 분리 수행자(red_apply)로 미뤄진다 — 증상 소멸의 실측은 구조적으로 이 턴
        밖이다(재현·회귀는 verify_cmd 위탁, 판정 보고는 red_report 가 다음 턴에). 평가자가
        이 사실을 모르면 정직한 "적용 예약됨" 보고를 미완으로 찍고 재실행을 라운드 소진까지
        돌린 뒤 증류에서도 제외한다 — 올바른 수리 패턴이 학습되지 못해 헤맴이 재생산된다.
        상태는 수리 세션 원장(데이터)에서 읽는다 — 산문 지시가 아니라 기계 판독이 진실.
        """
        try:
            import json as _json
            from datetime import datetime as _dt
            from thread_context import get_current_task_id
            from runtime_utils import get_base_path
            tid = (get_current_task_id() or "").strip()
            if not tid:
                return ""
            # 키 규칙은 repair_staging.task_key 와 동일 — 정본은 그쪽(데이터 계약 복제 1줄).
            key = re.sub(r"[^A-Za-z0-9_-]", "_", tid)[:48] or "notask"
            sess_dir = get_base_path() / "data" / "system_ai_state" / "repair_sessions"
            sess_path = sess_dir / f"{key}.json"
            if not sess_path.is_file():
                return ""
            sess = _json.loads(sess_path.read_text(encoding="utf-8"))
            if sess.get("status") != "apply_scheduled":
                return ""
            try:
                age_s = (_dt.now() - _dt.fromisoformat(sess["scheduled_at"])).total_seconds()
                if age_s > self._SCHEDULED_FRESH_S:
                    return ""   # 좌초된 옛 예약 — 이 턴의 사실이 아니다
            except Exception:
                pass
            rels = sorted(r.get("rel") or "" for r in (sess.get("files") or {}).values())
            files_str = ", ".join(f"`{r}`" for r in rels if r) or "(파일 목록 미기재)"
            verify_cmd = ""
            try:
                job = _json.loads((sess_dir / f"{key}.apply.json").read_text(encoding="utf-8"))
                verify_cmd = (job.get("verify_cmd") or "").strip()
            except Exception:
                pass
            verify_line = (
                f"적용 후 재현 검증은 verify_cmd(`{verify_cmd[:160]}`)로 수행자에게 위탁되었다."
                if verify_cmd else
                "적용 후 재현 검증 명령(verify_cmd)은 위탁되지 않았다 — 이 부재는 경미한 "
                "피드백으로 지적해도 되나, 아래 판정 규칙을 뒤집는 사유는 아니다.")
            return (
                "## 자기수리 지연 적용 상태 (기계 판독 — 수리 세션 원장)\n"
                f"이 턴의 backend 수리는 검증 관문 통과 후 **적용이 예약**되었다(대상: {files_str}). "
                "라이브 쓰기는 이 턴이 닫힌 뒤 분리 수행자(red_apply)가 재검증 후 수행하고, "
                f"{verify_line} 판정은 다음 턴 보고(red_report)가 소유한다.\n"
                "**판정 규칙**: 증상 소멸·수리 효과의 턴 내 실측은 구조적으로 불가능하다 — "
                "달성 기준에 '재실행으로 증상 소멸 실측' 류 항목이 있어도, 이 턴에서는 "
                "\"검증 통과·적용 예약됨(판정은 다음 턴)\" 보고가 그 항목의 충족이다. "
                "턴 내 미실측을 이유로 NOT_ACHIEVED 를 내리지 마라 — 재실행해도 같은 벽에 "
                "부딪히는 낭비만 반복된다.\n\n")
        except Exception:
            return ""   # 주입은 보강 — 실패해도 평가 자체를 막지 않는다

    _evaluator_prompt_cache: str = ""

    @classmethod
    def _load_evaluator_prompt(cls) -> str:
        """평가 에이전트 프롬프트 파일을 로드한다 (캐시). 시스템 구조 문서 포함."""
        if not cls._evaluator_prompt_cache:
            base = Path(__file__).parent.parent.parent / "data"
            prompt_path = base / "common_prompts" / "evaluator_prompt.md"
            try:
                cls._evaluator_prompt_cache = prompt_path.read_text(encoding='utf-8')
            except FileNotFoundError:
                cls._evaluator_prompt_cache = "달성 기준의 모든 항목을 엄격히 평가하라."
            # 시스템 구조 문서(정체성 코어)만 항상 주입 — 디렉토리/파일 트리는
            # codebase_map 가이드로 분리(get_system_structure_core)
            try:
                from prompt_builder import get_system_structure_core
                structure = get_system_structure_core()
            except Exception:
                structure = ""
            if structure:
                cls._evaluator_prompt_cache += f"\n\n<system_structure>\n{structure}\n</system_structure>"
            # IBL 카탈로그(12_ibl_only, ~15K) 주입 폐지 (2026-06-28) — 평가는 IBL 체계 전문이
            # 아니라 criteria + action_ledger(실제 호출 사실) + capability_focus(추천 도구)로 판정한다.
            # evaluator_prompt.md 어디도 IBL 카탈로그를 참조하지 않아 dead weight 였다.
        return cls._evaluator_prompt_cache

    def _evaluate_achievement(self, user_message: str, criteria: str,
                               response: str, created_files: str,
                               consciousness_output: dict = None,
                               tool_results_str: str = "",
                               action_ledger: str = "",
                               execution_memory: str = "",
                               visual_artifacts: list = None) -> tuple:
        """평가 AI로 달성 기준 충족 여부를 판단한다.

        의식 에이전트의 출력(task_framing, capability_focus)과 action_ledger
        (실제 호출된 액션의 사실 기록)를 활용하여 결과물뿐 아니라
        도구 활용의 적절성까지 평가한다.

        Returns:
            (achieved: bool, feedback: str, severity: int)
            severity: 0=N/A(achieved), 1=경미, 2=중대, 3=치명
        """
        evaluator_system_prompt = self._load_evaluator_prompt()

        # 메시지에는 평가 대상 데이터만
        prompt = (
            f"## 사용자 요청\n{user_message}\n\n"
            f"## 달성 기준\n{criteria}\n\n"
        )

        # 지연 적용 예약이 걸린 턴이면 그 사실을 기준 직후에 주입 — 평가자가 "증상 소멸
        # 미실측"을 미달 사유로 삼아 재실행 루프를 헛돌리지 않게 한다(ep2386 실측).
        prompt += self._scheduled_repair_note()

        # 검증용 액션 원장 — 기준 직후에 배치(인접성). 에이전트의 '서술'이 아니라
        # 실제 호출 로그에서 추출한 '사실'. 안 한 일의 부재를 평가자가 볼 수 있게 한다.
        if action_ledger:
            prompt += (
                "## 실제 실행된 액션 원장 (전수 · 검증 기준)\n"
                "아래는 에이전트가 *실제로 호출한* 액션의 전수 목록이다 — 에이전트의 서술이 아니라 "
                "도구 호출 로그에서 추출한 사실. 달성 기준이 특정 액션을 요구하면(예: 특정 파일 읽기, "
                "grep/검색, 특정 도구 실행), **그 액션이 이 목록에 실제로 있는지로 판정하라.** "
                "목록에 없으면 그 단계는 *수행되지 않은 것*이다 — 에이전트 응답이 '했다'고 말해도 "
                "이 원장에 없으면 안 한 것으로 간주하라.\n"
                f"{action_ledger}\n\n"
            )

        # 의식 에이전트의 메타 판단을 평가 맥락으로 제공
        if consciousness_output:
            task_framing = consciousness_output.get("task_framing", "")
            if task_framing:
                prompt += f"## 문제 정의 (의식 에이전트 판단)\n{task_framing}\n\n"

            history_summary = consciousness_output.get("history_summary", "")
            if history_summary:
                prompt += f"## 이전 대화 맥락\n{history_summary}\n\n"

            # self_awareness 출력 필드 폐지 (2026-06-28) — task_framing 으로 흡수.
            cap_focus = consciousness_output.get("capability_focus", {})
            if isinstance(cap_focus, dict):
                hint = cap_focus.get("hint", "")
                actions = cap_focus.get("highlight_actions", [])
                if hint or actions:
                    prompt += "## 도구 활용 맥락\n"
                    if actions:
                        prompt += f"- 추천된 도구: {', '.join(actions)}\n"
                    if hint:
                        prompt += f"- 접근 방향: {hint}\n"
                    prompt += "\n"

            # world_state 출력 필드 폐지 (2026-06-28) — task_framing 으로 흡수.

        # 연상기억(execution_memory=해마 IBL 레퍼런스) 주입 폐지 (2026-06-28) — 평가는
        # action_ledger(실제 호출 사실)와 capability_focus(추천 도구)로 도구 적절성을 판정한다.
        # 과거 코드 사례 블록은 "기준 충족 여부" 판단에 불필요했다.

        if tool_results_str:
            prompt += f"## 도구 실행 결과\n{tool_results_str}\n\n"

        prompt += f"## 에이전트 응답\n{response[:8000]}\n\n"

        if created_files:
            prompt += f"## 생성된 파일 내용\n{created_files}\n\n"

        if visual_artifacts:
            import os as _os
            names = ", ".join(_os.path.basename(a.get("_path", "")) for a in visual_artifacts)
            prompt += (
                f"## 시각 산출물 검수 ({len(visual_artifacts)}개 첨부: {names})\n"
                "아래에 **실제 생성된 이미지**가 첨부되어 있다. 텍스트 설명이 아니라 이미지를 "
                "직접 보고 달성 기준 충족을 판단하라 — 레이아웃·가독성·의도 표현·잘림/깨짐/빈 영역 등 "
                "실제 시각 품질을 확인할 것.\n\n"
            )

        prompt += "위 정보를 바탕으로 평가하세요. 도구 실행 결과가 있으면 실제로 작업이 수행되었는지 확인하세요."

        # 평가 입력 가시화 — 평가자에게 충분한 컨텍스트가 전달되는지 진단.
        # 어제 208번 같은 오판(도구 결과가 평가자에 부족하게 전달되어 "상상 보고" 판정) 검출용.
        _tool_results_info = f"{len(tool_results_str)}자" if tool_results_str else "없음"
        _created_files_info = f"{len(created_files)}자" if created_files else "없음"
        _ledger_info = f"{action_ledger.count(chr(10)) + 1}줄" if action_ledger else "없음"
        self._log(
            f"[GoalEval] 평가 입력: prompt={len(prompt)}자, "
            f"criteria={len(criteria)}자, response={len(response)}자, "
            f"tool_results={_tool_results_info}, action_ledger={_ledger_info}, "
            f"created_files={_created_files_info}"
        )

        try:
            # 평가기 = 의식 모델과 동일(system_ai_config). 평가 프롬프트의 정교한 루브릭(원장
            # 교차검증·열린문제 노력선·표면 vs 실질)을 경량 flash-lite 가 실행하지 못해 거짓합격을
            # 달성 기준 평가는 모델 기어 '평가' 축(role=evaluate)으로 해소된다 —
            # 기어 프리셋상 평가 축은 경량 티어(과거 opus 고정 → 경량 개선). system_ai_call 은
            # role 만 다를 뿐 oneshot_ai_call 과 같은 계약(prompt/system_prompt/images).
            from consciousness_agent import system_ai_call

            eval_images = None
            if visual_artifacts:
                eval_images = [{"base64": a["base64"], "media_type": a["media_type"]}
                               for a in visual_artifacts]
            eval_response = system_ai_call(prompt, system_prompt=evaluator_system_prompt,
                                           images=eval_images, role="evaluate")
            if eval_response is None or not eval_response.strip():
                self._log("[GoalEval] AI 응답 없음 (API 오류 등), 통과 처리")
                return True, "평가 스킵 (AI 응답 없음)", 0

            self._log(f"[GoalEval] 평가 응답: {eval_response[:200]}")

            # 관용 파서 — 서두 문장·마크다운 장식 뒤로 밀린 판정도 흡수 (모듈 함수 참조)
            achieved, severity = parse_eval_verdict(eval_response)

            return achieved, eval_response, severity

        except Exception as e:
            self._log(f"[GoalEval] 평가 오류: {e}")
            return True, f"평가 오류 (통과 처리): {e}", 0

    def _run_goal_evaluation_stream(self, user_message: str, criteria: str,
                                    initial_response: str, history: list,
                                    consciousness_output: dict = None,
                                    max_rounds: int = 2,
                                    tool_results: list = None,
                                    tool_calls: list = None,
                                    execution_memory: str = "",
                                    cancel_check=None):
        """달성 기준 기반 평가 루프 — **제너레이터**. 최종 응답은 `return` 값.

        호출자는 `evaluated = yield from self._run_goal_evaluation_stream(...)` 로 쓴다.

        ★왜 제너레이터인가 (2026-08-22): 옛 판은 `-> str` 블로킹 함수라 평가자 호출
        (실측 50~90초)과 **에이전트 전면 재실행**(실측 595,995ms = 9분56초, 도구 30여 회)이
        전부 스트림 밖이었다. 실행 단계(6번)는 도구마다 이벤트를 흘리는데 같은 에이전트를
        다시 돌리는 재실행은 한 글자도 안 흘리는 비대칭 — 화면에는 1라운드 응답이 나온 뒤
        영원히 도는 스피너로 보였고, 그 침묵 구간이 WS 유휴 타임아웃(600초)보다 길어
        긴 턴은 NOT_ACHIEVED 를 받는 순간 타임아웃이 구조적으로 확정이었다.
        이제 재실행 이벤트가 그대로 흐르므로 화면도 살고 유휴 타이머도 리셋된다.

        Args:
            user_message: 사용자 원래 요청
            criteria: 달성 기준
            initial_response: 에이전트 첫 응답
            history: 대화 히스토리
            consciousness_output: 의식 에이전트 출력 (task_framing, capability_focus 등)
            max_rounds: 최대 평가 횟수 (기본 2)
            tool_results: 도구 실행 결과 문자열 리스트 (legacy — 이름·인풋 없음)
            tool_calls: 도구 호출 구조화 이력 `{name,input,result,is_error}` 리스트.
                tool_results보다 우선 사용된다. 둘 다 있으면 tool_calls 사용.
                평가자가 시퀀스 자체(어떤 도구를 어떤 순서로)를 판단 근거로 쓸 수 있다.
            execution_memory: 실행기억 (도구/사례/implementation)
            cancel_check: 중단 여부 콜백 — 재실행 구간에도 사용자의 중단이 닿게 한다.
                옛 판은 이 인자가 없어 평가 루프에 들어간 뒤로는 중단 버튼이 무력했다.

        Yields:
            평가 진행 상태(`thinking`)와 재실행 에이전트의 스트림 이벤트 그대로
            (`text`/`tool_start`/`tool_result`/`thinking`). 재실행의 `final` 은
            여기서 회수해 반환값으로 삼으므로 흘리지 않는다.

        Returns:
            최종 응답 텍스트 (`yield from` 의 값)
        """
        import time as _time
        from thread_context import set_goal_eval_outcome, clear_goal_eval_outcome
        # 이번 평가의 판정을 초기화 — 증류 게이트가 직전 메시지의 stale 판정을 보지 않도록.
        clear_goal_eval_outcome()
        response = initial_response

        # 도구 호출 trace를 직렬화 — 시퀀스 자체는 어떤 경우에도 보존됨.
        # tool_calls가 우선; 없으면 tool_results(legacy) 사용.
        trace_source: list = tool_calls if tool_calls else (tool_results or [])
        tool_results_str = serialize_tool_trace(trace_source)
        # 검증용 액션 원장 — execute_ibl code에서 [node:action]+대상을 전수 추출.
        # serialize_tool_trace가 못 보여주던 '실제 호출된 IBL 액션'을 평가자에게 노출한다.
        action_ledger = build_action_ledger(trace_source)
        # _collect_created_files용: tool_calls가 있으면 그쪽도 활용.
        _trace_dicts = tool_calls if tool_calls else None

        # ★거짓 '허위보고' 버그 근본 수정: 재실행 호출을 self.ai.get_last_tool_calls()로만
        # 읽었는데 gemini provider는 _last_tool_calls를 안 채워 빈 결과 → action_ledger가 초기
        # 호출에 멈춤 → "재실행했는데 원장에 없으니 조작"이라는 거짓 양성(루프가 영원히 통과 못 함).
        # thread_context는 실행기(execute_tool/ibl_engine)가 채우므로 provider와 무관하게 모든
        # 라운드를 담는 진실 소스 → 여기서 델타를 떠 원장에 누적한다.
        try:
            from thread_context import get_tool_calls as _get_tc
        except Exception:
            _get_tc = None

        def _tc_calls():
            """thread_context의 execute_tool 레벨 호출만 (ibl_engine 레벨 ibl: 중복 제외)."""
            if not _get_tc:
                return []
            try:
                return [c for c in (_get_tc() or [])
                        if not str(c.get("tool_name", "")).startswith("ibl:")]
            except Exception:
                return []

        # 초기 trace가 비면(예: gemini 비-streaming 경로는 provider 호출이력을 안 줌) thread_context로 시드.
        if not trace_source:
            _seed = _tc_calls()
            if _seed:
                trace_source = list(_seed)
                tool_results_str = serialize_tool_trace(trace_source)
                action_ledger = build_action_ledger(trace_source)
                _trace_dicts = trace_source
        _tc_seen = len(_tc_calls())

        for round_num in range(1, max_rounds + 1):
            if cancel_check and cancel_check():
                self._log("[GoalEval] 사용자 중단 — 현재 응답 반환")
                set_goal_eval_outcome(False, 0)
                return response

            self._log(f"[GoalEval] 라운드 {round_num}/{max_rounds} 평가 시작")
            # 평가자 호출은 50~90초 블로킹 — 들어가기 전에 상태를 흘려 화면과
            # WS 유휴 타이머를 함께 살린다(transient: thinking).
            yield {"type": "thinking",
                   "content": f"🎯 달성 기준 평가 중 (라운드 {round_num}/{max_rounds})"}
            eval_start = _time.time()

            # 생성된 파일 수집 (tool_calls의 file_path를 우선 활용)
            created_files = self._collect_created_files(response, tool_calls=_trace_dicts)
            # 시각 산출물(이미지) 수집 — 평가자가 픽셀을 직접 보게 (G 루프 보편 백스톱)
            visual_artifacts = self._collect_visual_artifacts(response, tool_calls=_trace_dicts)

            # 달성 여부 평가 (criteria + action_ledger(실제 호출 사실) + capability_focus + 시각 산출물)
            # execution_memory(해마)는 평가에 불필요해 미전달 (2026-06-28).
            achieved, feedback, severity = self._evaluate_achievement(
                user_message, criteria, response, created_files,
                consciousness_output=consciousness_output,
                tool_results_str=tool_results_str,
                action_ledger=action_ledger,
                visual_artifacts=visual_artifacts,
            )

            eval_time = _time.time() - eval_start
            severity_label = {0: "-", 1: "LOW", 2: "MED", 3: "HIGH"}.get(severity, "?")
            try:
                import hashlib as _hashlib
                from episode_logger import record_trajectory_event
                record_trajectory_event("validation.completed", {
                    "validator": "goal_eval",
                    "round": round_num,
                    "achieved": bool(achieved),
                    "severity": int(severity or 0),
                    "elapsed_ms": int(eval_time * 1000),
                    "criteria_sha256": _hashlib.sha256((criteria or "").encode(
                        "utf-8", "replace")).hexdigest(),
                    "feedback_sha256": _hashlib.sha256((feedback or "").encode(
                        "utf-8", "replace")).hexdigest(),
                })
            except Exception:
                pass  # 검증 기록은 관측 — 평가 결과를 바꾸지 않는다
            self._log(
                f"[GoalEval] 라운드 {round_num}: "
                f"{'ACHIEVED' if achieved else 'NOT_ACHIEVED'} "
                f"(severity={severity_label}, {eval_time:.1f}초)"
            )

            if achieved:
                set_goal_eval_outcome(True, 0)
                return response

            # 마지막 라운드면 그냥 반환 — 미달성으로 끝났음을 증류 게이트에 알린다.
            if round_num >= max_rounds:
                set_goal_eval_outcome(False, severity)
                self._log(f"[GoalEval] 라운드 소진, 현재 응답 반환 (미달성 → 증류 제외)")
                return response

            # 피드백을 주입하여 재실행 — severity에 따라 전략 분기
            self._log(f"[GoalEval] 재실행 시작 (severity={severity_label}, 피드백 주입)")

            if severity >= 3:
                # 치명적: 전략 전환 유도
                retry_directive = (
                    "⚠️ 이전 접근 방식이 근본적으로 잘못되었습니다. "
                    "동일한 방법을 반복하지 마세요.\n"
                    "아래 피드백의 '대안 전략'을 참고하여 완전히 다른 접근법으로 시도하세요. "
                    "이전 결과물은 폐기하고 처음부터 다시 작업하세요."
                )
            elif severity >= 2:
                # 중대: 접근법 부분 수정
                retry_directive = (
                    "핵심적인 부분이 미흡합니다. "
                    "이전 작업의 기본 틀은 유지하되, 접근 방식을 수정하세요. "
                    "특히 피드백에서 지적한 도구 활용이나 핵심 기준을 중점적으로 보완하세요."
                )
            else:
                # 경미: 기존 방식 보완
                retry_directive = (
                    "이전 작업 결과를 최대한 활용하고, 부족한 부분만 보완하세요."
                )

            feedback_message = (
                f"[평가 피드백] 이전 응답이 달성 기준을 충족하지 못했습니다. "
                f"(심각도: {severity_label})\n\n"
                f"달성 기준: {criteria}\n\n"
                f"부족한 점:\n{feedback}\n\n"
                f"{retry_directive}\n\n"
                f"⚠️ 중요: 이 재실행은 비대화형 모드입니다. "
                f"ask_user_question을 사용하지 마세요. 사용자에게 질문할 수 없습니다. "
                f"현재 가진 정보만으로 최선의 결과를 만드세요."
            )

            # 피드백을 히스토리에 추가하여 재실행
            retry_history = history + [
                {"role": "assistant", "content": response[:8000]},
                {"role": "user", "content": feedback_message}
            ]

            # 재실행 표식 — 실행 단계와 같은 어법(`[자기반성]`)으로 화면에 남긴다.
            yield {"type": "text",
                   "content": f"\n\n---\n[평가 피드백 반영 재실행 {round_num}/{max_rounds - 1}]\n\n"}

            try:
                # ★스트리밍 재실행 — 이벤트를 그대로 흘린다. `final` 만 회수해
                #  응답으로 삼는다(빈 final 이 채워진 final 을 못 덮게: ep1251 규약).
                #  흘려보내는 김에 tool_start/tool_result 를 구조화 수집한다 — 이게
                #  재실행 원장의 1차 소스다(아래 누적 주석 참조).
                retry_response = ""
                _stream_calls: list = []  # 이번 재실행의 {name,input,result,is_error}
                _sc_cursor = 0  # id 없는 결과의 도착 순서 페어링 커서 (claude_code.process_message 와 동일 규약)
                for ev in self.ai.process_message_stream(
                    message_content=feedback_message,
                    history=retry_history,
                    images=None,
                    cancel_check=cancel_check,
                ):
                    _et = ev.get("type")
                    if _et == "final":
                        _c = ev.get("content", "")
                        if _c or not retry_response:
                            retry_response = _c
                        continue
                    if _et == "tool_start":
                        _stream_calls.append({
                            "id": ev.get("id", ""),
                            "name": ev.get("name", ""),
                            "input": ev.get("input") or {},
                            "result": "",
                            "is_error": False,
                        })
                    elif _et == "tool_result":
                        _rid = ev.get("id", "")
                        _slot = None
                        if _rid:
                            _slot = next(
                                (tc for tc in _stream_calls if tc.get("id") == _rid),
                                None,
                            )
                        if _slot is None and _sc_cursor < len(_stream_calls):
                            _slot = _stream_calls[_sc_cursor]
                        _sc_cursor += 1
                        if _slot is not None:
                            _slot["result"] = ev.get("result", "")
                            _slot["is_error"] = bool(ev.get("is_error", False))
                    yield ev

                # ★재실행이 만든 새 도구 호출을 누적해 ledger·trace 를 갱신한다.
                # 안 하면 다음 라운드 평가가 라운드 1의 stale 원장으로 새 응답을
                # 판정 → 실제로 작업해 놓고도 "원장에 없으니 안 했다 = 조작"이라는
                # 거짓 양성이 난다(재실행 루프가 영원히 통과 못 함).
                # 1차 소스 = 방금 흘려보낸 스트림의 tool_start/tool_result — 프로바이더
                # 계약이라 전 프로바이더가 방출하고, 이 스레드에서 직접 관측한 값이다.
                # thread_context 델타는 폴백 — claude_code 는 도구가 CLI 서브프로세스에서
                # 돌아 threading.local 에 안 잡히므로 델타가 항상 빈다(2026-08-30 실측:
                # 재실행의 self:edit·self:patch 가 원장에 누락 → 실제 적용된 수리를
                # "미수행"으로 뒤집는 거짓 판정). 델타 커서는 소스와 무관하게 전진시켜
                # 같은 호출이 뒤 라운드에 이중 적재되지 않게 한다.
                # ★옛 `get_last_tool_calls()` 폴백은 제거했다(2026-08-22): 그 속성은
                # provider 의 **논스트림** 래퍼만 채우는데 재실행이 스트리밍으로 바뀌어
                # 영영 안 채워진다 — 남겨 두면 델타가 빈 라운드에서 *이전 논스트림
                # 호출의 잔여*를 이번 라운드 원장으로 오적재한다(빈손보다 나쁜 거짓 원장).
                # 누적은 응답이 비어도(503 등) 수행한다 — 도구는 실제로 돌았고 세계는
                # 이미 바뀌었으므로, 원장은 응답 채택 여부가 아니라 사실을 따른다.
                _all_tc = _tc_calls()
                _tc_new = _all_tc[_tc_seen:]
                _tc_seen = len(_all_tc)
                _new_calls = _stream_calls if _stream_calls else _tc_new
                if _new_calls:
                    if trace_source and isinstance(trace_source[0], dict):
                        trace_source = list(trace_source) + list(_new_calls)
                    else:
                        trace_source = list(_new_calls)
                    tool_results_str = serialize_tool_trace(trace_source)
                    action_ledger = build_action_ledger(trace_source)
                    _trace_dicts = trace_source

                # 재실행 결과가 비어있으면 (503 등) 이전 응답 유지
                if retry_response and retry_response.strip():
                    response = retry_response
                    self._log(f"[GoalEval] 재실행 완료: {len(response)}자 "
                              f"(도구 {len(_new_calls)}회 원장 누적)")
                else:
                    self._log(f"[GoalEval] 재실행 결과 비어있음, 이전 응답 유지 ({len(response)}자, "
                              f"도구 {len(_new_calls)}회는 원장에 누적)")
            except Exception as e:
                self._log(f"[GoalEval] 재실행 실패: {e}")
                return initial_response

        return response
