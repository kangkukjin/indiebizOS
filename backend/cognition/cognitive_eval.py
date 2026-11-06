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
        """Use the shared output collection; a link alone is not a new output."""
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
            return "제공된 달성 기준만 평가하라. 새 요구를 만들지 않는다. 판정 불가면 UNKNOWN."

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
        """평가 AI로 달성 기준 충족 여부를 판단한다.

        의식의 명시적 기준만 판정한다. 실행 원장·결과는 증거이며 별도 평가 축이 아니다.

        Returns:
            (achieved: bool|None, feedback: str, severity: int). None은 검수 미완료.
            severity: 0=N/A(achieved), 1=경미, 2=중대, 3=치명
        """
        self.goal_outcome = parse_goal_outcome("")
        self.evaluation_failure = None
        self.evaluation_retryable = False
        self.evaluation_usage = {}
        self.citation_uses = []
        from evaluation_input import EvaluationPrompt, context_sections, record
        sections = []
        try:
            contract = json.loads(criteria)
        except (TypeError, ValueError):
            contract = None
        if not isinstance(contract, dict) or "criteria" not in contract:
            from supervisor_handoff import criteria_contract
            contract = criteria_contract(user_message, {"achievement_criteria": criteria})
        if not contract["criteria"]:
            return None, "의식의 달성 기준이 없어 평가하지 않았습니다", 0
        criteria = json.dumps(contract, ensure_ascii=False)
        evaluator_system_prompt = self._load_evaluator_prompt()
        if evaluation_policy:
            evaluator_system_prompt += "\n\n" + evaluation_policy

        # 메시지에는 평가 대상 데이터만
        prompt = (
            f"## 사용자 요청\n{user_message}\n\n"
            f"## 달성 기준\n{criteria}\n\n"
        )

        # 지연 적용 예약이 걸린 턴이면 그 사실을 기준 직후에 주입 — 평가자가 "증상 소멸
        # 미실측"을 미달 사유로 삼아 재실행 루프를 헛돌리지 않게 한다(ep2386 실측).
        prompt += self._scheduled_repair_note()

        if action_ledger:
            sections.append(record(action_ledger, subject="실제 실행된 액션 원장"))
        prompt += ("실행 원장·파일·도구 결과는 선택된 표시다. 생략된 액션·대상의 부재는 "
                   "미실행의 증거가 아니다. manifest의 존재는 본문 검토가 아니다. "
                   "핵심 근거가 부족하면 UNKNOWN_REASON: evidence와 필요한 판본·범위를 적는다.\n\n")

        # 규정과 독립된 사용자 정정으로 기준의 의미·충돌을 확인한다.
        from research_planning import evaluation_block
        prompt += evaluation_block(consciousness_output,
                                   getattr(self, "project_path", None)
                                   or getattr(getattr(self, "ai", None), "project_path", None))
        # 계승 규정에는 history_summary가 없고, 새 규정의 요약도 정정을 누락할 수 있다.
        from history_excerpt import conversation_excerpt
        conversation = conversation_excerpt(conversation_history)
        if conversation:
            prompt += ("## 기준 해석용 이전 대화 원문 발췌\n"
                       "사용자 조건의 변경·철회와 assistant의 제안을 구별하라. "
                       "생략된 내용은 미확인이며 새 목표를 추측하지 않는다.\n"
                       f"{conversation}\n\n")
        elif consciousness_output and consciousness_output.get("history_summary"):
            prompt += f"## 기준 해석용 이전 대화\n{consciousness_output['history_summary']}\n\n"

        if tool_results_str:
            sections.append(record(tool_results_str, subject="도구 실행 결과"))

        prompt += f"## 에이전트 응답\n{response if full_response else response[:8000]}\n\n"
        if evaluation_context:
            required_context, selected_context = context_sections(evaluation_context)
            prompt += f"## 하네스가 수집한 평가 맥락\n{required_context}\n\n"
            sections.extend(selected_context)

        if evaluation_attachments is not None:
            sections.extend(evaluation_attachments)
        elif created_files:
            sections.append(record(created_files, subject="생성된 파일 내용"))

        if visual_artifacts:
            import os as _os
            names = ", ".join(_os.path.basename(a.get("_path", "")) for a in visual_artifacts)
            prompt += (
                f"## 시각 산출물 검수 ({len(visual_artifacts)}개 첨부: {names})\n"
                "아래에 **실제 생성된 이미지**가 첨부되어 있다. 텍스트 설명이 아니라 이미지를 "
                "직접 보고 명시된 달성 기준에 해당하는 부분만 판단하라. 일반적인 미적 개선을 새 조건으로 만들지 않는다.\n\n"
            )

        # User corrections are mandatory even if the display excerpt omitted them.
        user_turns = [m for m in (conversation_history or []) if isinstance(m, dict) and m.get('role') == 'user']
        if user_turns:
            prompt += "\n## 사용자 원문·정정 (제공된 이력 전체)\n" + json.dumps(user_turns, ensure_ascii=False)
        prompt += "위 증거로 명시된 기준의 충족 여부만 판정하세요."
        store = getattr(self, 'evaluation_store', None)
        if store is not None:
            for section in sections:
                if section['source_ref'] is None:
                    ref = store.evidence(section['text'])
                    section.update(text=store.read_evidence(ref['id'], 0, None)['text'],
                                   source_ref=ref['id'], revision=ref['id'], total=ref['chars'])
                    if 'structured' in section:
                        section['structured'] = json.loads(section['text'])
        if store is not None and evaluation_context:
            from evaluation_evidence import receipt_sections
            context_value = json.loads(evaluation_context)
            receipts = receipt_sections(context_value.get('research_citations') or {}, store)
            for receipt in receipts:
                receipt['contexts'] = [c['claim_context'] for c in context_value.get('research_claims', [])
                                       if c['citation'] == receipt['subject']]
            sections.extend(receipts)
        self.evaluation_sources = [{k: r[k] for k in ('source_ref', 'revision', 'total', 'subject', 'criterion_ids')} for r in sections]
        from evaluation_input import evidence_references
        try:
            reference_context = json.loads(evaluation_context) if evaluation_context else {}
        except (ValueError, TypeError):
            reference_context = {}
        self.evaluation_references = evidence_references({'context': reference_context,
                                                          'selection_sources': self.evaluation_sources})
        prompt = EvaluationPrompt(prompt, sections, criteria, references=self.evaluation_references)

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
            self.evaluation_metrics = prompt.metrics
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
            if achieved is True and reference_context.get('research_claims'):
                from research_review import citation_uses
                try:
                    self.citation_uses, unresolved = citation_uses(eval_response,
                        reference_context['research_claims'], reference_context['research_citations']['valid'])
                except ValueError as exc:
                    self.evaluation_failure = {'kind': 'protocol', 'message': str(exc)}
                    self.goal_outcome = parse_goal_outcome('')
                    return None, str(exc), 0
                if unresolved:
                    self.citation_uses = []
                    self.goal_outcome = parse_goal_outcome('')
                    return None, ('UNKNOWN\nUNKNOWN_REASON: evidence\n실제 근거로 채택한 인용의 원문이 없습니다: '
                                  + json.dumps(unresolved, ensure_ascii=False)), 0
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
        from thread_context import set_goal_eval_outcome, clear_goal_eval_outcome, get_goal_eval_outcome
        # 이번 평가의 판정을 초기화 — 증류 게이트가 직전 메시지의 stale 판정을 보지 않도록.
        clear_goal_eval_outcome()
        response = initial_response

        def persist_review(learning):
            from model_result_view import evidence_store
            from supervision_store import digest
            try:
                store = evidence_store()
                ref = store.evidence(response)
                (store.directory / 'review_status.json').write_text(json.dumps({
                    **get_goal_eval_outcome(), 'original_goal': user_message, 'criteria': criteria,
                    'response': {'hash': digest(response), **ref}, 'learning': learning,
                    'validator': 'goal_eval'}, ensure_ascii=False), encoding='utf-8')
            except OSError as exc:
                get_goal_eval_outcome()['storage_error'] = str(exc)
                self._log(f'[GoalEval] 검수 결과 보존 실패: {exc}')

        def unreviewed(reason, *, status="UNKNOWN"):
            from supervision_store import digest
            set_goal_eval_outcome(False, 0, status=status, reason=reason, response_hash=digest(response))
            persist_review('deferred')
            return response

        def rejected(reason, feedback, severity):
            from supervision_store import digest
            set_goal_eval_outcome(False, severity, status='NOT_ACHIEVED', reason=feedback,
                                  response_hash=digest(response), **self.goal_outcome)
            persist_review('components_only')
            return response

        if max_rounds < 1:
            return unreviewed("평가 라운드가 배정되지 않았습니다", status="NOT_RUN")

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

        prepared = None
        reuse_packet = False
        for round_num in range(1, max_rounds + 1):
            if cancel_check and cancel_check():
                self._log("[GoalEval] 사용자 중단 — 현재 응답 반환")
                set_goal_eval_outcome(False, 0, status="UNKNOWN", reason="사용자 중단")
                return response

            self._log(f"[GoalEval] 라운드 {round_num}/{max_rounds} 평가 시작")
            # 평가자 호출은 50~90초 블로킹 — 들어가기 전에 상태를 흘려 화면과
            # WS 유휴 타이머를 함께 살린다(transient: thinking).
            yield {"type": "thinking",
                   "content": f"🎯 달성 기준 평가 중 (라운드 {round_num}/{max_rounds})"}
            eval_start = _time.time()

            self.goal_outcome = parse_goal_outcome("")
            # 생성된 파일 수집 (tool_calls의 file_path를 우선 활용)
            try:
                from final_evaluator import prepare_standalone, snapshot_error, POLICY, FINAL_POLICY, RESEARCH_POLICY
                if not reuse_packet:
                    prepared = prepare_standalone(self, response, user_message,
                        consciousness_output or {'achievement_criteria': criteria}, _trace_dicts, history, cancel_check,
                        previous=prepared)
                reuse_packet = False
                packet = prepared._evaluation_packet
                supplied_images = {i.get('_evidence_id') for i in packet.get('images', [])}
                for ref in packet['context'].get('visual_evidence', []):
                    ref['delivered'] = ref['id'] in supplied_images
                self.evaluation_store = prepared.store
                achieved, feedback, severity = self._evaluate_achievement(
                    user_message, packet['criteria'], response, packet['files'],
                    consciousness_output=consciousness_output, tool_results_str=tool_results_str,
                    action_ledger=action_ledger, visual_artifacts=packet['images'], conversation_history=history,
                    evaluation_context=json.dumps(packet['context'], ensure_ascii=False),
                    evaluation_policy=POLICY + FINAL_POLICY + (RESEARCH_POLICY if packet['context'].get('research_citations') else ''),
                    evaluation_attachments=packet['attachments'], full_response=True)
                packet['selection_sources'] = getattr(self, 'evaluation_sources', [])
                if achieved and (cancel_check and cancel_check() or snapshot_error(prepared)):
                    achieved, feedback, severity = None, '검수 중 결과 또는 관련 입력이 변경됐습니다', 0
            except Exception as exc:
                achieved, feedback, severity = None, f"검수 준비 또는 평가 실패: {exc}", 0

            eval_time = _time.time() - eval_start
            severity_label = {0: "-", 1: "LOW", 2: "MED", 3: "HIGH"}.get(severity, "?")
            try:
                import hashlib as _hashlib
                from episode_logger import record_trajectory_event
                # ★피드백 **전문**을 원장에 남긴다(2026-08-31 ep2461: sha256 만 남겨
                #   NOT_ACHIEVED 사유가 회수 불능이었다 — 로그의 [:200] 은 표시용 절단일
                #   뿐, 판정 근거의 정본은 여기다). 상한 초과는 표식으로 정직하게.
                _fb = feedback or ""
                record_trajectory_event("validation.completed", {
                    "validator": "goal_eval",
                    "round": round_num,
                    "review_status": "APPROVED" if achieved is True else "REWORK" if achieved is False else "UNKNOWN",
                    **getattr(self, "goal_outcome", parse_goal_outcome("")),
                    "status": "UNKNOWN" if achieved is None else "ACHIEVED" if achieved else "NOT_ACHIEVED",
                    "severity": int(severity or 0),
                    "elapsed_ms": int(eval_time * 1000),
                    "criteria": (criteria or "")[:2000],
                    "criteria_sha256": _hashlib.sha256((criteria or "").encode(
                        "utf-8", "replace")).hexdigest(),
                    "feedback_text": _fb[:8000],
                    "feedback_truncated": len(_fb) > 8000,
                    "feedback_sha256": _hashlib.sha256(_fb.encode(
                        "utf-8", "replace")).hexdigest(),
                })
            except Exception:
                pass  # 검증 기록은 관측 — 평가 결과를 바꾸지 않는다
            self._log(
                f"[GoalEval] 라운드 {round_num}: "
                f"{'UNKNOWN' if achieved is None else 'ACHIEVED' if achieved else 'NOT_ACHIEVED'} "
                f"(severity={severity_label}, {eval_time:.1f}초)"
            )

            if achieved is None:
                if (prepared and round_num < max_rounds
                        and re.search(r'UNKNOWN_REASON:\s*evidence\b', feedback or '')):
                    from evaluation_input import evidence_requests, new_evidence_requests, recover
                    parsed = evidence_requests(feedback, prepared._evaluation_packet)
                    requests = new_evidence_requests(parsed['requests'], packet.get('attachments', []))
                    if parsed['status'] in {'valid', 'normalized'} and requests:
                        try:
                            if changed := snapshot_error(prepared):
                                return unreviewed(changed)
                            packet['attachments'].extend(recover(prepared, requests))
                            reuse_packet = True
                            continue
                        except (ValueError, OSError) as exc:
                            return unreviewed(str(exc))
                return unreviewed(feedback or "판정을 확보하지 못했습니다")
            if achieved:
                set_goal_eval_outcome(True, 0, status="ACHIEVED", reason=feedback,
                                      citation_uses=getattr(self, "citation_uses", []),
                                      response_hash=__import__("hashlib").sha256(response.encode()).hexdigest(), **self.goal_outcome)
                persist_review('eligible' if self.goal_outcome.get('goal_status') == 'ACHIEVED' else 'components_only')
                return response

            # 본문은 보존하고 판정은 별도 상태로 전달한다.
            if round_num >= max_rounds:
                self._log('[GoalEval] 라운드 소진, 검수 결과와 본문 보존')
                return rejected('응답 보완을 위한 재시도 한도에 도달했습니다.', feedback, severity)

            # 원래 완료 기준으로 보완한다. 실패 횟수·심각도로 목표를 바꾸지 않는다.
            self._log(f"[GoalEval] 재실행 시작 (severity={severity_label}, 피드백 주입)")

            retry_directive = (
                "원래 전체 완료 기준과 확보한 근거·결과물을 유지하고 지적된 결함을 보완하세요. "
                "이미 완료한 작업과 외부 효과를 반복하지 마세요."
            )

            feedback_message = (
                f"[평가 피드백] 이전 응답이 달성 기준을 충족하지 못했습니다. "
                f"(심각도: {severity_label})\n\n"
                f"달성 기준: {criteria}\n\n"
                f"부족한 점:\n{feedback}\n\n"
                f"{retry_directive}"
                # 재실행은 새 컨텍스트 — 자기 세션의 적용 예약분을 모르면 그 파일을
                # '없다'고 보고 재작성해 지연 적용과 충돌한다(ep2461). 원장 기반 주입.
                f"{self._scheduled_repair_agent_note()}\n\n"
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

                from task_repair import pending_response
                if notice := pending_response():
                    return notice

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
                return rejected('검수 후 보완 실행 중 오류가 발생했습니다.', feedback, severity)

        return response
