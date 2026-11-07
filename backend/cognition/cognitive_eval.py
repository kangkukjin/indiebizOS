"""사용자 목표와 최종 결과를 비교하는 선택적 원샷 평가.

최종 응답·제출물 본문을 전문으로 전달하고 판정을 반환한다.
실행 기록의 재감사, 증거 회수, 평가 뒤 작업 재실행은 이 경로의 책임이 아니다.
"""

import json
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
    r"^[\s*_#>\"'`\[\(-]*(NOT[\s_-]?ACHIEVED|ACHIEVED|UNKNOWN)\b", re.IGNORECASE)
_VERDICT_WORD_RE = re.compile(r"\bNOT[\s_-]?ACHIEVED\b|\bACHIEVED\b|\bUNKNOWN\b", re.IGNORECASE)
_SEVERITY_RE = re.compile(r"SEVERITY\s*[:：]\s*([123])", re.IGNORECASE)


def parse_goal_outcome(text):
    """응답 검수 표식과 별개인 원래 목표의 관측. 누락된 옛 판정은 미확정이다."""
    result = {"goal_status": "UNKNOWN", "goal_reason": "목표 판정 근거 없음",
              "goal_evidence": [], "remaining": []}
    match = re.search(r"(?m)^GOAL_OUTCOME:\s*(\{.*\})\s*$", text or "")
    try:
        value = json.loads(match[1]) if match else None
        if (isinstance(value, dict) and value.get("status") in {"ACHIEVED", "NOT_ACHIEVED", "UNKNOWN"}
                and isinstance(value.get("reason"), str) and value["reason"].strip()
                and isinstance(value.get("evidence"), list) and all(isinstance(x, str) for x in value["evidence"])
                and isinstance(value.get("remaining"), list) and all(isinstance(x, str) for x in value["remaining"])):
            result.update(goal_status=value["status"], goal_reason=value["reason"],
                          goal_evidence=value["evidence"], remaining=value["remaining"])
    except (ValueError, TypeError):
        pass
    return result


def parse_eval_verdict(text: str) -> tuple:
    """평가자 응답에서 (achieved: bool|None, severity: int)를 관용적으로 파싱한다.

    프롬프트는 '첫 줄에 ACHIEVED/NOT_ACHIEVED만'을 지시하지만, 평가자가 에이전틱
    프로바이더(claude_code 등 도구 사용)로 돌면 최종 응답이 서사체가 되어 판정이
    서두 문장 뒤 마크다운 볼드(**ACHIEVED**)로 밀려나는 일탈이 실측됨(에피소드 812 —
    첫 줄만 보던 옛 파서가 ACHIEVED 를 NOT_ACHIEVED 로 오판해 불필요한 재실행 발동).
    지시 강화로는 못 막으므로 파서가 흡수한다:
      1차: 판정 토큰으로 시작하는 첫 줄 (장식 관통)
      2차: 본문 어디든 첫 판정 토큰 등장
      3차: 판정 토큰 부재 → None(검수 미완료). 실패로 단정해 재실행하지도 않는다.
    severity 는 NOT_ACHIEVED 일 때 본문 전체에서 SEVERITY: n 탐색 (미표기=2).
    """
    verdict = None
    for line in text.strip().split('\n'):
        m = _VERDICT_LINE_RE.match(line.strip())
        if m:
            verdict = m.group(1).upper()
            break
    if verdict is None:
        m = _VERDICT_WORD_RE.search(text)
        verdict = m.group(0).upper() if m else None
    achieved = None if verdict in {None, "UNKNOWN"} else not verdict.startswith("NOT")

    severity = 0
    if achieved is False:
        m = _SEVERITY_RE.search(text)
        severity = int(m.group(1)) if m else 2  # 미표기 시 중간값
    return achieved, severity


def parse_criterion_defects(feedback, contract):
    """새 기준·근거 없는 지적은 자동 보완으로 넘기지 않는다. 의미 판정은 기존 평가자가 맡는다."""
    match = re.search(r"(?mi)^DEFECTS:\s*(\[.*\])\s*$", feedback)
    try:
        defects = json.loads(match[1]) if match else None
    except ValueError:
        return None
    ids = {row["id"] for row in contract["criteria"]}
    if not isinstance(defects, list) or not 1 <= len(defects) <= 5:
        return None
    if any(not isinstance(row, dict) or not isinstance(row.get("criterion_id"), str) or row["criterion_id"] not in ids
           or any(not isinstance(row.get(key), str) or not row[key].strip()
                  for key in ("evidence", "repair")) for row in defects):
        return None
    return [{key: row[key] for key in ("criterion_id", "evidence", "repair")} for row in defects]


#: 평가 첨부 한 파일의 글자 상한. 넘으면 앞·뒤 발췌와 하네스가 확인한 구조 요약을 싣는다.
EVALUATION_FILE_CHARS = 60000


def _json_outline(data, depth=0):
    """큰 JSON 산출물의 뼈대 — 평가자가 전문 없이 필수 항목·건수를 확인한다."""
    if isinstance(data, dict):
        if depth >= 2:
            return f"object({len(data)}키)"
        parts = [f"{key}: {_json_outline(value, depth + 1)}" for key, value in list(data.items())[:40]]
        more = f", …외 {len(data) - 40}키" if len(data) > 40 else ""
        return "{" + ", ".join(parts) + more + "}"
    if isinstance(data, list):
        first = f" · 첫 행 {_json_outline(data[0], depth + 1)}" if data and isinstance(data[0], dict) and depth < 2 else ""
        return f"list({len(data)}행{first})"
    return type(data).__name__


def bounded_attachment(path: str, content: str, cap: int = EVALUATION_FILE_CHARS) -> str:
    """평가자에게 붙이는 산출물 본문의 크기 상한(ep4211).

    후속 처리용 JSON 828K자가 통째로 실려 평가 한 번이 40만 토큰이었다(메시지의 93%, 두 번 모두 캐시 0).
    전문 대신 앞·뒤 발췌와, JSON 이면 하네스가 직접 파싱해 확인한 구조를 싣는다. 판정에 필요한 것은
    '파싱되는가·필수 항목이 있는가·건수가 맞는가'이지 2,698행 전부가 아니다."""
    if not isinstance(content, str) or len(content) <= cap:
        return content
    head, tail = content[:cap * 2 // 3], content[-(cap // 6):]
    outline = ""
    if str(path).lower().endswith(".json"):
        try:
            outline = " 하네스 확인: JSON 파싱 성공, 구조 " + _json_outline(json.loads(content)) + "."
        except ValueError as exc:
            outline = f" 하네스 확인: JSON 파싱 실패 — {exc}."
    return (f"[전체 {len(content):,}자 중 앞 {len(head):,}자·뒤 {len(tail):,}자만 첨부.{outline} "
            f"발췌 밖 내용의 부재를 단정하지 말 것]\n{head}\n…(중략)…\n{tail}")


class CognitiveEvalMixin:
    """Goal 평가 루프 — 의식 에이전트의 달성 기준 기반 자동 평가 메서드 모음."""

    def _extract_achievement_criteria(self, consciousness_output: dict,
                                       tool_results_str: str = "") -> Optional[str]:
        """의식 에이전트 출력에서 달성 기준을 추출한다.

        1차: criteria/achievement_criteria 필드 (별도 필드)
        2차: task_framing에서 "달성 기준:" 이후 텍스트 (하위 호환)
        도구 메타데이터는 의식이 채택하지 않은 새 평가 기준으로 승격하지 않는다.
        """
        # 1차: consciousness_output의 별도 필드
        if consciousness_output:
            from supervisor_handoff import criteria_contract
            contract = criteria_contract("", consciousness_output)
            if contract["criteria"]:
                return "\n".join(row["text"] for row in contract["criteria"])
            # 2차: task_framing에서 추출 (하위 호환)
            task_framing = consciousness_output.get("task_framing", "")
            if "달성 기준:" in task_framing:
                return task_framing.split("달성 기준:")[-1].strip().rstrip(".")
            if "달성기준:" in task_framing:
                return task_framing.split("달성기준:")[-1].strip().rstrip(".")

        return None

    def _collect_created_files(self, response: str,
                                tool_calls: Optional[List[Dict[str, Any]]] = None, *,
                                exclude_paths=(), snapshots=None, full_content=False,
                                attachments=None, evidence_store=None) -> str:
        """Read final submitted files; creation provenance is not a review prerequisite."""
        from types import SimpleNamespace
        from model_result_view import evidence_store as current_store
        from supervisor_content import discover
        from evaluation_input import record
        store = evidence_store or current_store()
        controller = SimpleNamespace(store=store, project_path=getattr(self, 'project_path', None) or '.')
        files = []
        for artifact in discover(controller, response, tool_calls):
            path = artifact['path']
            if path in exclude_paths:
                continue
            if artifact.get('error'):
                files.append(f"### {path}\n원문 회수 불가: {artifact['error']}")
                continue
            content = store.read_evidence(artifact['evidence_id'], 0, None)['text']
            if snapshots is not None:
                snapshots[path] = artifact['hash']
            if attachments is not None:
                attachments.append(record(content, subject=path, source_ref=artifact['evidence_id'],
                                          revision=artifact['evidence_id'], role=artifact.get('role', 'submission')))
            files.append(f"### {path}\n{bounded_attachment(path, content)}")
        return '\n\n'.join(files)

    _VISUAL_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp", ".gif": "image/gif"}

    def _collect_visual_artifacts(self, response: str,
                                   tool_calls=None, max_images=3, evidence_store=None):
        """Preserve actual pixels in the existing evidence store, including native returns.

        Paths are observations, never proof that a capture command succeeded. Once
        registered, a call's image bytes cannot be replaced by a later file at that path.
        """
        import base64
        from pathlib import Path
        from types import SimpleNamespace
        from supervisor_content import result_paths
        images, errors, seen = [], [], set()
        store = evidence_store
        image_path = re.compile(r'(?<![^\s"\'<>`(\[={])(/[^\s"\'<>`]+\.(?:png|jpe?g|webp|gif))(?=$|[\s"\'<>`)\]},;])', re.I)

        def add(data, media, path='', observed_at=None, ref=None):
            try:
                raw = base64.b64decode(data, validate=True)
                if not raw or len(raw) > 6 * 1024 * 1024:
                    raise ValueError('이미지가 비었거나 공급자 입력 크기를 초과했습니다')
                from PIL import Image
                import io
                with Image.open(io.BytesIO(raw)) as decoded:
                    decoded.verify()
                import hashlib
                fingerprint = hashlib.sha256(raw).hexdigest()
                if fingerprint in seen:
                    return
                seen.add(fingerprint)
                value = {'base64': data, 'media_type': media, '_path': path,
                         'observed_at': observed_at, 'sha256': fingerprint}
                if store and not ref:
                    ref = store.evidence(value)['id']
                images.append({**value, '_evidence_id': ref})
            except (ValueError, TypeError, OSError) as exc:
                errors.append({'path': path, 'error': str(exc)})

        def path_image(path):
            if not isinstance(path, str) or Path(path).suffix.lower() not in self._VISUAL_EXTS:
                return
            try:
                raw = Path(path).read_bytes()
                add(base64.b64encode(raw).decode(), self._VISUAL_EXTS[Path(path).suffix.lower()], path)
            except OSError as exc:
                errors.append({'path': path, 'error': str(exc)})

        def collect(value):
            if isinstance(value, str):
                if value.lstrip().startswith(('{', '[')):
                    try:
                        collect(json.loads(value))
                        return
                    except ValueError:
                        pass
                if value.startswith('data:image/') and ';base64,' in value:
                    header, data = value.split(';base64,', 1)
                    add(data, header[5:])
                    return
                path_image(value)
                for path in image_path.findall(value):
                    path_image(path)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, dict):
                data = value.get('base64') or value.get('image_base64')
                if value.get('type') == 'image':
                    data = data or value.get('data')
                media = value.get('media_type') or value.get('mimeType') or 'image/png'
                if data:
                    add(data, media, value.get('_path', ''), value.get('observed_at'))
                for key, item in value.items():
                    if key not in {'base64', 'b64', 'image_base64', 'data'}:
                        collect(item)

        for entry in tool_calls or []:
            if not isinstance(entry, dict) or entry.get('is_error'):
                continue
            cached = entry.get('visual_evidence')
            if cached is not None and store:
                for ref in cached:
                    try:
                        page = store.read_evidence(ref['id'], 0, None)
                        if page.get('integrity') != 'verified':
                            raise ValueError('이미지 원문 무결성 확인 실패')
                        value = json.loads(page['text'])
                        add(value['base64'], value['media_type'], value.get('_path', ''),
                            value.get('observed_at'), ref['id'])
                    except (ValueError, OSError, KeyError) as exc:
                        errors.append({'evidence_id': ref['id'], 'error': str(exc)})
                continue
            start = len(images)
            collect(entry.get('result'))
            # Native image reads return pixels or a path; an arbitrary shell input
            # is never parsed to infer a screenshot that was not returned.
            name = (entry.get('name') or entry.get('tool_name') or '').rsplit('__', 1)[-1].rsplit('.', 1)[-1]
            if name in {'view_image', 'read_image', 'open_image'}:
                for key in _FILE_PATH_INPUT_KEYS:
                    path_image((entry.get('input') or {}).get(key))
            if store:
                for path in result_paths(SimpleNamespace(store=store), entry):
                    path_image(path)
                entry['visual_evidence'] = [{'id': img['_evidence_id'], 'path': img['_path']}
                                           for img in images[start:]]
        # Explicit response images are evidence candidates too. File bytes, not
        # their textual mention, are delivered; failures remain visible.
        for path in image_path.findall(response or ''):
            path_image(path)
        self.visual_evidence = [{'id': img['_evidence_id'], 'path': img['_path'],
                                 'sha256': img['sha256'], 'observed_at': img['observed_at']}
                                for img in images]
        self.visual_errors = errors
        return images if max_images is None else images[-max_images:]

    # 예약이 이보다 오래 apply_scheduled 로 남아 있으면 수행자(red_apply) 좌초로 보고
    # 주입하지 않는다 — red_report.SCHEDULED_STALE_S 와 같은 값(그쪽이 좌초 재보고를 맡는다).
    _SCHEDULED_FRESH_S = 30 * 60

    def _scheduled_repair_note(self) -> str:
        """예약은 검증 완료가 아니다. 현재 구간을 닫고 영속 인계에서 이어간다."""
        state = self._scheduled_repair_state()
        if not state:
            return ""
        return ("## 자기수리 지연 적용 상태 (기계 판독)\n"
                "격리 검증을 통과한 변경의 적용이 예약되어 있습니다. 라이브 쓰기는 현재 실행 "
                "구간이 닫힌 뒤에 진행됩니다. 이 구간에서 기다리거나 같은 파일을 다시 쓰지 마세요. "
                "예약을 증상 소멸·사용자 목표 달성으로 판정하지 마세요. 적용 후 인계가 실제 결과와 "
                "남은 기준을 검증하며, 실패 시 보존된 증거로 필요한 부분만 보완합니다.\n\n")

    def _scheduled_repair_state(self):
        """이 턴 수리 세션의 신선한 적용 예약 상태 (없으면 None) — 원장에서 기계 판독.

        평가자 주입(_scheduled_repair_note)과 재실행 주입(_scheduled_repair_agent_note)의
        공통 읽기 — 상태 출처는 수리 세션 원장 하나다."""
        try:
            import json as _json
            from datetime import datetime as _dt
            from thread_context import get_current_task_id
            from runtime_utils import get_base_path
            tid = (get_current_task_id() or "").strip()
            if not tid:
                return None
            # 키 규칙은 repair_staging.task_key 와 동일 — 정본은 그쪽(데이터 계약 복제 1줄).
            key = re.sub(r"[^A-Za-z0-9_-]", "_", tid)[:48] or "notask"
            sess_dir = get_base_path() / "data" / "system_ai_state" / "repair_sessions"
            sess_path = sess_dir / f"{key}.json"
            if not sess_path.is_file():
                return None
            sess = _json.loads(sess_path.read_text(encoding="utf-8"))
            if sess.get("status") != "apply_scheduled":
                return None
            try:
                age_s = (_dt.now() - _dt.fromisoformat(sess["scheduled_at"])).total_seconds()
                if age_s > self._SCHEDULED_FRESH_S:
                    return None   # 좌초된 옛 예약 — 이 턴의 사실이 아니다
            except Exception:
                pass
            rels = sorted(r for r in (rr.get("rel") or ""
                          for rr in (sess.get("files") or {}).values()) if r)
            verify_cmd = ""
            try:
                job = _json.loads((sess_dir / f"{key}.apply.json").read_text(encoding="utf-8"))
                verify_cmd = (job.get("verify_cmd") or "").strip()
            except Exception:
                pass
            return {"rels": rels, "worktree": sess.get("worktree") or "",
                    "verify_cmd": verify_cmd}
        except Exception:
            return None

    def _scheduled_repair_agent_note(self) -> str:
        """재실행 턴에 주입하는 **재작성 금지** 기계 판독 문단 (예약 없으면 "").

        ★왜(2026-08-31 ep2461 실측): 재실행은 새 컨텍스트다 — 자기 세션에 적용 예약분이
        대기 중인 줄 모르면, file_find·grep·git 에 안 보이는 그 파일을 '없다'고 판단해
        재작성·직접 커밋하고, 턴 종료 후 지연 적용이 그 나중 판본을 옛 초안으로 덮는다
        (last-writer-loses). patch status 에 있어도 목록에 파묻힌다 — 앞에서 들이민다."""
        state = self._scheduled_repair_state()
        if not state:
            return ""
        files_str = ", ".join(f"`{r}`" for r in state["rels"]) or "(파일 목록 미기재)"
        wt = state["worktree"]
        read_hint = (f" 내용 확인이 필요하면 격리본을 읽어라(예: `{wt}/{state['rels'][0]}`)."
                     if wt and state["rels"] else "")
        return (
            "\n\n## 자기수리 지연 적용 상태 (기계 판독 — 재작성 금지)\n"
            f"이 턴의 수리 세션에는 검증 관문을 통과하고 **적용이 예약**된 파일이 대기 중이다: "
            f"{files_str}. 이 파일들은 이미 작성·검증·예약 완료됐고, 라이브 트리와 git 에는 "
            "**턴이 닫힌 뒤에야** 나타난다 — file_find·grep·git ls-files 에 안 보이는 것이 "
            "정상이며 '없어졌다'가 아니다. **같은 경로를 재작성·직접 커밋하지 마라** — "
            f"턴 종료 후 지연 적용과 충돌해 나중 판본이 덮인다.{read_hint} "
            "피드백 보완은 예약분을 전제로 부족한 부분만 더하라.")

    @classmethod
    def _load_evaluator_prompt(cls) -> str:
        """작은 역할 파일은 매 평가에 읽어 수정·복구를 다음 판정에 반영한다."""
        prompt_path = (Path(__file__).parent.parent.parent / "data"
                       / "common_prompts" / "evaluator_prompt.md")
        try:
            return prompt_path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return "사용자 목표와 최종 결과만 비교하라. 새 요구·조사를 만들지 말고, 판정 불가면 UNKNOWN."

    def _evaluate_achievement(self, user_message: str, criteria: str,
                               response: str, created_files: str,
                               consciousness_output: dict = None,
                               tool_results_str: str = "",
                               action_ledger: str = "",
                               execution_memory: str = "",
                               visual_artifacts: list = None,
                               evaluation_context: str = "", evaluation_policy: str = "",
                               full_response: bool = False,
                               conversation_history: list = None,
                               evaluation_attachments: list = None) -> tuple:
        """사용자 목표와 최종 결과의 부합성을 한 번 비교한다.

        실행 원장·인용·내부 계획은 재조사하거나 별도 완료 조건으로 삼지 않는다.

        Returns:
            (achieved: bool|None, feedback: str, severity: int). None은 검수 미완료.
            severity: 0=N/A(achieved), 1=경미, 2=중대, 3=치명
        """
        self.goal_outcome = parse_goal_outcome("")
        self.evaluation_failure = None
        self.evaluation_retryable = False
        self.evaluation_usage = {}
        self.citation_uses = []
        # Final comparison has one input: the user's goal and the delivered result.
        # Do not turn internal plans, execution traces, or citations into more work.
        from final_evaluator import comparison_goal
        user_turns = comparison_goal(user_message, conversation_history)['user_turns']
        prompt = "## 사용자 원래 목표\n" + user_message
        if user_turns:
            prompt += "\n\n## 사용자가 명시한 이전 요청·정정\n" + json.dumps(user_turns, ensure_ascii=False)
        prompt += "\n\n## 최종 응답\n" + response
        if created_files:
            prompt += "\n\n## 최종 제출물 본문\n" + created_files
        if evaluation_context:
            try:
                context = json.loads(evaluation_context)
                errors = {k: context[k] for k in ('artifact_errors', 'visual_errors') if context.get(k)}
                if errors:
                    prompt += "\n\n## 제출물 읽기 오류\n" + json.dumps(errors, ensure_ascii=False)
            except (TypeError, ValueError):
                pass
        from final_evaluator import POLICY, FINAL_POLICY
        evaluator_system_prompt = self._load_evaluator_prompt() + "\n\n" + POLICY + FINAL_POLICY
        self.evaluation_sources = []
        self.evaluation_metrics = {'scope': 'goal_result', 'chars': len(prompt),
                                   'submission_chars': len(created_files), 'truncated': False}
        self._log(f"[GoalEval] 목표–결과 비교: prompt={len(prompt)}자, 제출물={len(created_files)}자")
        from evaluation_input import CompleteInput
        prompt = CompleteInput(prompt)

        try:
            # 기존 평가 축의 도구 없는 원샷. 별도 모델 호출을 추가하지 않는다.
            from consciousness_agent import system_ai_call, clear_oneshot_failure, oneshot_failure_details
            clear_oneshot_failure()

            eval_images = None
            if visual_artifacts:
                eval_images = [{"base64": a["base64"], "media_type": a["media_type"]}
                               for a in visual_artifacts]
            from model_call_context import capture_usage, summarize_usage
            with capture_usage() as usage:
                try:
                    eval_response = system_ai_call(prompt, system_prompt=evaluator_system_prompt,
                                                   images=eval_images, role="evaluate")
                finally:
                    self.evaluation_usage = summarize_usage(usage)
            failure = oneshot_failure_details()
            if failure:
                self.evaluation_failure = failure
                return None, "평가 전달 실패 — " + failure['kind'], 0
            if eval_response is None or not eval_response.strip():
                self.evaluation_retryable = True
                self._log("[GoalEval] AI 응답 없음 — 검수 미완료")
                return None, "평가 모델의 응답이 없어 검수를 마치지 못했습니다", 0

            self._log(f"[GoalEval] 평가 응답: {eval_response[:200]}")

            # 관용 파서 — 서두 문장·마크다운 장식 뒤로 밀린 판정도 흡수 (모듈 함수 참조)
            self.goal_outcome = parse_goal_outcome(eval_response)
            achieved, severity = parse_eval_verdict(eval_response)
            if achieved is None:
                self.evaluation_retryable = not bool(_VERDICT_WORD_RE.search(eval_response))
                return None, eval_response if _VERDICT_WORD_RE.search(eval_response) else "평가 응답 형식 오류: " + eval_response, 0
            # 결함의 의미는 검토자와 실행자가 판단한다. JSON 서식의 누락이나
            # 자유 산문이라는 이유로 모델의 판단을 지우거나 UNKNOWN으로 바꾸지 않는다.
            return achieved, eval_response, severity

        except Exception as e:
            self._log(f"[GoalEval] 평가 오류: {e}")
            self.evaluation_retryable = True
            return None, f"평가 오류로 검수를 마치지 못했습니다: {e}", 0

    def _run_goal_evaluation_stream(self, user_message: str, criteria: str,
                                    initial_response: str, history: list,
                                    consciousness_output: dict = None,
                                    max_rounds: int = 2, tool_results: list = None,
                                    tool_calls: list = None, execution_memory: str = "",
                                    cancel_check=None):
        """Compare once and preserve the delivered result; never restart execution."""
        from thread_context import set_goal_eval_outcome, clear_goal_eval_outcome, get_goal_eval_outcome
        from final_evaluator import prepare_standalone, snapshot_error
        from supervision_store import digest
        from model_result_view import evidence_store
        clear_goal_eval_outcome()
        achieved, feedback, severity = None, '평가가 실행되지 않았습니다', 0
        self.goal_outcome = parse_goal_outcome('')
        if max_rounds < 1:
            status = 'NOT_RUN'
        elif cancel_check and cancel_check():
            status, feedback = 'UNKNOWN', '사용자 중단'
            self._log('[GoalEval] 사용자 중단 — 최종 결과 보존')
        else:
            yield {'type': 'thinking', 'content': '사용자 목표와 최종 결과를 비교하고 있습니다.'}
            try:
                prepared = prepare_standalone(self, initial_response, user_message,
                    consciousness_output or {}, history=history, cancel_check=cancel_check)
                packet = prepared._evaluation_packet
                self.evaluation_store = prepared.store
                achieved, feedback, severity = self._evaluate_achievement(
                    user_message, packet['criteria'], initial_response, packet['files'],
                    visual_artifacts=packet['images'], conversation_history=history,
                    evaluation_context=json.dumps(packet['context'], ensure_ascii=False))
                if cancel_check and cancel_check():
                    achieved, feedback = None, '사용자 중단'
                    self.goal_outcome = parse_goal_outcome('')
                elif error := snapshot_error(prepared):
                    achieved, feedback = None, error
                    self.goal_outcome = parse_goal_outcome('')
                status = 'ACHIEVED' if achieved is True else 'NOT_ACHIEVED' if achieved is False else 'UNKNOWN'
            except Exception as exc:
                achieved, severity = None, 0
                status, feedback = 'UNKNOWN', f'최종 결과 비교 실패: {exc}'
                self.goal_outcome = parse_goal_outcome('')
        set_goal_eval_outcome(achieved, severity, status=status, reason=feedback,
                             method='goal_result',
                             review_status='APPROVED' if achieved is True else 'REWORK' if achieved is False else status,
                             response_hash=digest(initial_response), **self.goal_outcome)
        outcome = get_goal_eval_outcome()
        from episode_logger import record_trajectory_event
        record_trajectory_event('validation.completed', {'validator': 'goal_eval', 'final': True,
                                                         'scope': 'goal_result', **outcome})
        store = evidence_store()
        try:
            ref = store.evidence(initial_response)
            (store.directory / 'review_status.json').write_text(json.dumps({
                **outcome, 'scope': 'goal_result', 'original_goal': user_message,
                'response': {'hash': digest(initial_response), **ref}, 'validator': 'goal_eval',
                'learning': ('eligible' if achieved is True and outcome.get('goal_status') == 'ACHIEVED'
                             else 'deferred' if achieved is None else 'components_only'),
            }, ensure_ascii=False), encoding='utf-8')
        except OSError as exc:
            outcome['storage_error'] = str(exc)
            self._log(f'[GoalEval] 비교 결과 보존 실패: {exc}')
        return initial_response
