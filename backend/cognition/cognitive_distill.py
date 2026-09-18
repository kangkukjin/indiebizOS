"""
cognitive_distill.py - 턴 종료 후 메모리 증류 믹스인
IndieBiz OS Core

agent_cognitive.py 에서 분리(2026-07-17, 1500줄 규칙 모듈화). 응답이 나간 뒤의
쓰기 경로 — 심층 메모리 증류(_distill_deep_memory)·포식 기억 증류(_distill_forage_memory,
공간 헬퍼 포함)·초크포인트(_after_response). 회상(읽기)은 cognitive_recall.py 가 짝.
★_FORAGE_CUES(포식 의도 게이트)는 cognitive_recall 에 정의 — 두 믹스인이
AgentCognitiveMixin 으로 합성되므로 self 로 공유된다.
"""

import json
import re
from typing import Optional, Tuple

from cognitive_trace import _merge_keywords


def _desktop_bodies() -> set:
    """홈디스크(데스크탑) 몸 이름 집합 — 정본 = runtime_utils.DESKTOP_PROFILES.

    지연 import: 이 모듈은 backend 층 경로가 안 깔린 문맥에서도 import 될 수 있어
    (메서드들의 sys.path 방어와 같은 이유), 미가용 시에만 동결 사본으로 버틴다.
    """
    try:
        from runtime_utils import DESKTOP_PROFILES
        return DESKTOP_PROFILES
    except ImportError:
        return {"mac", "windows", "linux", "pc"}


def _home_body() -> str:
    """이 몸의 홈디스크 body 이름 = detect_body profile — 'mac' 고정은 윈도우/리눅스
    설치본에서 남의 이름이 된다. 감지 실패의 중립 폴백은 'pc'."""
    try:
        from runtime_utils import detect_body
        return detect_body().get("profile") or "pc"
    except Exception:
        return "pc"


def _principal_owner() -> bool:
    """턴의 요청 주체가 주인인가 — 기억 쓰기 초크포인트의 관문(docs/EXTERNAL_SERVICE_APP_HANDOFF.md §6-1)."""
    try:
        import principal
        return principal.is_owner()
    except Exception:
        return False


class CognitiveDistillMixin:
    """턴 종료 후 메모리 쓰기(증류) 메서드 모음."""

    # 포식 *증거* — 응답이 실제로 navigable/반구조 공간을 뒤졌나(증류 2차 비용 게이트).
    #   디스크 경로·URL·코드 구성·파일확장자를 *한 집합*으로(per-medium 분기 아님 — 매체 무관).
    _FORAGE_EVIDENCE_RE = re.compile(
        r"https?://|/[\w가-힣.\-]+/[\w가-힣.\-]+|"
        r"\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|kt|pdf|jpe?g|png|docx?|xlsx?)\b|"
        r"\b(?:def |class |import |grep)", re.IGNORECASE)
    _FORAGE_EVIDENCE_WORDS = (
        "폴더", "디렉토리", "디스크", "볼륨", "확장자", "파일명", "핸들러", "모듈",
        "출처", "검색 결과", "검색결과", "논문", "사이트", "scholar", "arxiv",
    )

    # ★자기서술 게이트(Fix 2): 시스템이 자기 인지·기억 코드를 포식할 때, 증류가 자신의
    #   사고방식(포식 기억·냄새지도·의식 에이전트·인지 파이프라인…)을 자신에게 다시 적는
    #   순환을 차단한다. 마커는 *이 시스템의 인지 기계장치 고유명*뿐 — 일반 코드 관습
    #   (IBL·build·op 분기·통화 봉투)은 포함하지 않는다(그건 값진 코드 지식이라 통과).
    #   claim+locus 결합 텍스트에 하나라도 있으면 자기서술로 보고 그 항목만 드롭.
    _SELF_COGNITION_MARKERS = (
        "포식 기억", "포식기억", "냄새지도", "forage_memory", "forage_agent",
        "foraging_system", "foraging_agent", "owner_model", "주인모델",
        "의식 에이전트", "무의식 에이전트", "무의식 분류", "인지 파이프라인",
        "인지 아키텍처", "cognitive_pipeline", "associative_recall",
        "execution_memory", "메모리 동기화", "achievement_criteria",
        "냄새(scent)", "reflex 분기", "reflex)", "증류 단계",
    )

    def _is_self_narration(self, *texts: str) -> bool:
        """포식 증류가 이 시스템의 인지·기억 사고방식을 자기 자신에게 다시 적는지 판정.

        forager 가 자기 인지 코드를 포식하면 냄새지도·의식 에이전트·증류 같은 자기 기계장치를
        서술하는 순환이 생긴다(피드백 루프). 그 서술만 걸러낸다 — 같은 코드베이스의 *일반화 가능한
        코드 관습*(핸들러 op 분기·IBL 빌드·통화 봉투)은 마커에 없어 통과한다.
        """
        blob = " ".join(t for t in texts if t).lower()
        if not blob:
            return False
        return any(mk.lower() in blob for mk in self._SELF_COGNITION_MARKERS)  # vj-ok: 내부 표식 탐지 — 코드 소유 어휘

    def _repo_root_path(self, *texts: str) -> Optional[str]:
        """포식 중인 코드 공간의 *루트 절대경로* — 응답 속 소스파일 경로의 .git 조상.

        폴백=cwd 의 git 루트. 못 찾으면 None. _repo_identity(basename)·코드 locus 정규화 공용.
        포식 *공간* 식별(하드웨어 자아 아님 — FORAGER_MULTIBODY_DESIGN §1).
        """
        import os
        def _git_root(start: str) -> Optional[str]:
            d = start
            for _ in range(10):
                if os.path.isdir(os.path.join(d, ".git")):
                    return d.rstrip("/") or None
                nd = os.path.dirname(d)
                if nd == d:
                    return None
                d = nd
            return None
        # 1) 응답 속 소스파일 절대경로 → .git 조상
        for t in texts:
            for m in re.finditer(r"(/[\w./가-힣-]+?\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|kt))\b",
                                 t or ""):
                root = _git_root(os.path.dirname(m.group(1)))
                if root:
                    return root
        # 2) 폴백 — 실행 cwd 의 git 루트
        try:
            return _git_root(os.getcwd())
        except Exception:
            return None

    def _repo_identity(self, *texts: str) -> Optional[str]:
        """코드 공간 정체(basename) — body 키 'code:<repo>' 용. _repo_root_path 의 basename."""
        import os
        root = self._repo_root_path(*texts)
        return os.path.basename(root) if root else None

    def _normalize_space(self, space: Optional[str], ai_response: str = "",
                         user_message: str = "") -> str:
        """증류기 LLM 이 명명한 공간 라벨을 body 키로 정규화(매체 무관).

        AI 가 무엇을 포식했는지 안다(forager=AI) → 키워드로 재유추하지 않고 *명명*을 받는다.
        'code'(레포명 없음)면 .git 으로 보강, 빈 값이면 *이 몸의 홈디스크*(profile — 맥이면
        'mac', 윈도우면 'windows'). 그 외엔 라벨 그대로
        (web/book:<제목>/disk:<라벨>/… 매체가 늘어도 코드 변경 0 — FORAGER_MULTIBODY_DESIGN §9).
        """
        s = (space or "").strip()
        if not s:
            return _home_body()
        # bare "code"(레포명 없음)면 .git basename 으로 보강(케이스 보존 — repo/label 은 식별자).
        if s.lower() == "code":
            repo = self._repo_identity(ai_response, user_message)
            return f"code:{repo}" if repo else "code"
        return s  # 라벨 그대로(case-sensitive 식별자: code:<repo>/disk:<label>/book:<title>)

    @staticmethod
    def _is_fs_space(body: str) -> bool:
        """파일시스템 공간인가 — 홈디스크(데스크탑 몸)·code:<repo>·disk:<label>. web/book 은 추상.

        홈디스크 이름은 'mac' 하드코딩이 아니라 몸 자기-감지의 집합(DESKTOP_PROFILES) —
        윈도우/리눅스 설치본은 'windows'/'linux' 로 찍히므로 이름 고정은 그 몸에서 샌다.
        """
        b = body or ""
        return b in _desktop_bodies() or b.startswith("code") or b.startswith("disk")

    def _resolve_fs_locus(self, loc: str, repo_root: Optional[str], body: str) -> Tuple[str, bool]:
        """파일시스템 공간 locus 를 *실존 검증*해 정규화(Fix 1). 반환 (locus, is_real).

        LLM 이 상대 슬러그·추상 개념명·라인접미사(:288)를 locus 로 줄 수 있다. 이를 무조건
        repo_root 에 join 하면 `/…/code:repo/foo` 같은 *실존하지 않는 /-접두 경로*가 생겨
        영구 "missing" 잡음이 된다(냄새지도 오염). 그래서:
          1) 후보(절대=그대로 / 상대=repo_root 결합, 라인접미사 벗겨 재시도)를 실존 검증.
          2) 실존 → 절대경로 canonical 반환(freshness 추적 정상).
          3) 미해소 → is_real=False. 호출측이 그 단언을 버린다(주소 없는 기억은 소환되지 않는다).
        """
        import os, re
        raw = (loc or "").strip()
        if not raw:
            return raw, False
        # glob 패턴·substrate 표식(__…)은 실존 대상 아님 → 추상 그대로
        if "*" in raw or raw.startswith("__"):
            return raw, False

        def _candidates(p: str):
            yield p
            m = re.search(r":\d+(?:-\d+)?$", p)  # tool.py:288 / handler.py:10-20
            if m:
                yield p[:m.start()]

        for base in _candidates(raw):
            if base.startswith("/") or base.startswith("~"):
                cand = os.path.expanduser(base)
            elif repo_root:
                cand = os.path.join(repo_root, base)
            else:
                continue  # 상대인데 repo 없음(mac) → 실존 확인 불가
            if os.path.exists(cand):
                return cand, True  # 실존 → canonical 절대경로

        # 미해소 → 거절. 옛 판은 `{body}/{꼬리}` 추상 locus 로 강등해 저장했는데, 그 별명은 어느 장소를 열어도
        #   나오지 않는 기억이 됐다(2026-09-18 재고 감사 — `code:IndieBiz OS/unknown` 부류). 주소가 없으면 적지 않는다.
        return raw, False

    def _distill_deep_memory(self, user_message: str, ai_response: str):
        """최종 응답 후 사용자 원문의 지속 가치 선별·중복 비교. 도구 초안은 입력이 아니다."""
        try:
            if not user_message or not ai_response:
                return

            import sys, os, json
            mem_pkg = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..",
                "data", "packages", "installed", "tools", "memory"
            )
            if mem_pkg not in sys.path:
                sys.path.insert(0, mem_pkg)
            import memory_db
            import memory_tree

            from thread_context import get_current_agent_id, get_current_task_id
            from consciousness_agent import oneshot_ai_call

            # 신원 = 스레드 컨텍스트 우선, 없으면 자기 자신(self.agent_id). 스레드 값만 믿으면
            # 컨텍스트 없는 호출(스크립트·백그라운드 스레드)이 agent_id=None 으로 내려가
            # memory_None.db 를 만들었다(2026-09-02 저장소 루트 실측). 둘 다 없으면 memory_db 가 거부.
            agent_id = get_current_agent_id() or getattr(self, "agent_id", None)
            project_path = str(self.project_path)

            # 기억 지도(주제 가지 목차) — 어디에 넣을지는 모델이 이 지도를 보고 정한다(2026-09-03 사용자 판정:
            #   "기억이 발생할 때마다 어디에 넣을지 판단하는 것도 AI 가 할 일"). 코드 분류기 없음.
            try:
                tree_map = memory_tree.map_text(memory_db._get_db_path(project_path, agent_id))
            except Exception:
                tree_map = ""

            # 기억은 출처를 기억한다 — 추출된 사실(claim)과 별개로 원 발화 스팬을 동봉.
            # 나중에 "이 기억이 어디서 왔나"를 대조할 수 있는 최소 단위(검증 기관 없이 기록만).
            from episode_logger import EpisodeLogger
            episode = EpisodeLogger.current()
            source_ref = json.dumps(
                {"utterance": user_message,
                 "task": get_current_task_id() or getattr(episode, "task_id", ""),
                 "episode_id": getattr(episode, "episode_id", None),
                 "recorded_at": __import__("datetime").datetime.now().isoformat(),
                 "final_response_sha256": __import__("hashlib").sha256(ai_response.encode()).hexdigest()},
                ensure_ascii=False)

            from memory_evidence import (durable_source_units, grounded_fact, select_units,
                                         unresolved_reference)
            units = durable_source_units(user_message)
            if not any(u["eligible"] for u in units):
                from episode_logger import record_trajectory_event
                record_trajectory_event("memory.distill.skipped", {"reason": "no_user_fact_candidate"})
                return

            # 1단계: 대화에서 기억할 정보 조각 추출
            # 날짜 앵커 — 없으면 경량 모델이 연도를 자기 추측으로 채워 오염된다
            # (ep2359: "8/31 예정"이 2025-08-31 로 각인. 기억은 태어나는 자리에서 절대 날짜여야 한다).
            from datetime import datetime as _dt
            today = _dt.now().strftime("%Y-%m-%d")
            extract_prompt = f"""오늘은 {today}이다.
다음 사용자 원문 단위 중 나중에 기억해둘 만한 정보를 선택하라.
사실이라는 이유만으로 저장하지 않는다. 이번 대화 밖의 향후 협업에서 어떤 판단·행동에
계속 필요한지 future_use에 구체적으로 설명할 수 있는 정보만 선택하라.
사소한 사실·작업 진행 내역·한 번의 조사 결과는 제외한다. 저장할 정보가 0건인 것이 정상이다.
사용자의 의견은 세계의 객관적 사실이 아니다. 앞으로도 적용할 지속 선호나 확정 결정일 때만
그 사용자가 그렇게 선호·결정했다는 원문으로 남긴다. 근거 없는 분석·평가는 선택하지 않는다.
content를 재작성하지 마라. 원문 단위의 source_ids만 고르면 본문은 코드가 그대로 저장한다.
사용자 메시지는 전달 경로이지 저자 증명이 아니다. 붙여 넣은 AI 답변·보고서·타인 의견을
사용자 선호로 저장하지 마라. attribution=user_candidate도 저자 확정이 아니다.
문맥에서 사용자가 직접 말한 개인 사실·선호·확정 결정임이 분명할 때만 고른다.
타인의 제안을 사용자가 명시적으로 채택했다면 사용자의 채택 선언만 선택한다.
(이름, 중요한 날짜, 사용자 선호, 사용자가 확정한 결정사항)
eligible=false인 질문·요청과 안내문 상투구는 선택하지 않는다. AI의 답변·권고·도구 관측은
에피소드와 산출물에 남아 있으므로 여기서 사용자 사실로 복제하지 않는다.
retention은 user_fact|user_preference|user_decision 중 하나이며 확신 없으면 선택하지 않는다.
과거 사건의 인원·장소·조건을 이번 사건의 사실이나 지속적 선호로 확장하지 않는다.
일시적 데이터(주가, 날씨, 환율, 시세 등)와 추론/감상은 제외.
연도를 추측하거나 상대 날짜를 재작성하지 말고 원문 그대로 선택하라. 해석 기준 시점은 source_ref.recorded_at에 별도로 남는다.

★이 시스템(IndieBiz OS) *자신의 내부 구현*(내부 DB·파일 경로·테이블·모듈 구조)은 기억 대상이
아니다 — 몸의 정본은 코드·문서가 관리하며, 여기 적히면 어휘를 우회한 접근로가 각인된다 → 제외.
(나쁜 예: "대화 DB 파일 경로: projects/X/conversations.db" — 저장 금지.)

★사용자선호 = *지속적* 성향·취향·환경만(예: "중고는 안 삼", "존댓말 선호", "라벨 프린터는 Netum POS9260 보유").
이번 한 번의 요청·지시("~찾아줘", "~해줘")나 이번 검색의 일회성 조건(용량·가격대·수량)은
선호가 아니다 → 저장하지 마라. 일회성 요청문은 선택하지 마라.
(나쁜 예: "4T나 5T 제품을 찾아줘", "이번에는 중고가 필요없어" → 이번 요청의 조건 — 제외.
좋은 예: "나는 앞으로도 중고 제품은 사지 않을 거야" → 명시적인 지속 선호의 원문.)
영상 한 편의 길이·목소리·시점·전달 위치도 이번 작업의 조건이다. 향후에도 적용하라는
근거 없이 "항상 선호한다"로 일반화하지 마라. 해당 에피소드·산출물에 이미 기록되므로 복제하지 않는다.

★저장되는 것은 네가 고른 원문 단위 그대로다. 나중에 이 조각만 따로 읽는 사람이 누구의·무엇에 관한
말인지 알 수 있어야 한다. "그·그런·그래서"처럼 앞 문장에 기대는 단위는, 가리키는 대상이 담긴 앞
단위를 source_ids 에 **함께** 골라라(여러 id 는 한 기억으로 이어 붙는다). 같은 메시지 안에 대상이
없으면(이전 턴·AI 답변에만 있으면) 고르지 마라 — 홀로 서지 못하는 조각은 기계가 거절한다.
(나쁜 예: [2] "11월 18일이니까 아직 시간은 있는데." 단독 → 무엇의 날짜인지 모른다.
좋은 예: [1,2] "아내에게 선물을 사고 싶은데 …" + "11월 18일이니까 …")

★각 조각에 **node(주제 가지)** 를 적어라 — 이 자아의 기억 지도(아래)에서 가장 알맞은 가지를 고른다.
기존 가지를 우선하고, 정말 새 주제면 새 경로("상위/하위" 꼴, 최대 3단, 한국어 명사)를 만든다.
가지는 *무엇에 관한 기억인가*(사람·장소·일·물건·주제)로 나눈다 — 종류(선호·결정)는 가지가 아니다.
한두 건짜리 가지를 만들지 마라 — 여럿이 모일 주제만 새 가지, 아니면 가장 가까운 상위 가지에 둔다.
[기억 지도]
{tree_map or "(아직 가지 없음 — 첫 가지를 만들어라)"}

JSON 배열로만 응답.
[{{"source_ids": [1], "retention": "user_fact", "future_use": "향후 어떤 판단·행동에 계속 필요한가", "keywords": "k1,k2", "category": "사용자선호|사용자정보|의사결정|중요날짜", "node": "가지/경로"}}]
정보가 없으면 빈 배열 [] 반환.

사용자 원문 단위(JSON):
{json.dumps(units, ensure_ascii=False)}"""

            result = oneshot_ai_call(
                prompt=extract_prompt,
                system_prompt="사실 정보만 추출하라. JSON 배열로만 응답.",
                role="background",
            )
            if not result:
                return

            # JSON 파싱 — 첫 JSON 값만 안전 추출(뒤에 잡담이 붙어도 유실 안 함, ep855 부류)
            from runtime_utils import parse_first_json
            facts = parse_first_json(result)
            if not isinstance(facts, list) or not facts:
                return

            saved_count = 0
            updated_count = 0

            # 2단계: 각 조각의 기존 유사 항목을 기계적으로 탐색(임베딩, 무LLM).
            #   - 유사 항목 없음 → 곧장 NEW (LLM 판정 불필요)
            #   - 유사 항목 있음 → (신규, 기존 후보) 쌍으로 모아 다음 단계에서 '한 번에' 판정
            pending = []   # [(fact, top)] — 배치 dedup 대상
            for candidate in facts[:5]:  # 최대 5개 조각
                fact = grounded_fact(candidate, units, source_ref, durable_only=True)
                if not fact:
                    continue
                # 지시 대상 관문 — 선행 문장 없이 고른 의존 조각은 저장하지 않는다(사유는 궤적에 남아 셀 수 있다).
                dangling = unresolved_reference(select_units(candidate.get("source_ids"), units))
                if dangling:
                    print(f"[심층메모리] 지시 대상 거부({dangling}): \"{fact.get('content', '')[:50]}\"")
                    try:
                        from episode_logger import record_trajectory_event
                        record_trajectory_event("memory.distill.rejected",
                                                {"reason": dangling, "text": fact.get("content", "")[:120]})
                    except Exception:
                        pass
                    continue
                content = fact.get("content", "").strip()
                if not content:
                    continue
                fact["content"] = content
                fact["keywords"] = fact.get("keywords", "").strip()
                fact["category"] = fact.get("category", "").strip()
                fact["node"] = memory_tree.norm_node(fact.get("node", ""))

                # 몸-명사 관문(저장소 계약의 앞단 거부 — 뒷단 memory_db.save 도 같은 검사로 raise).
                # 몸 내부 경로가 기억되면 어휘 우회로가 각인된다(ep2279). 조각만 버리고 배치는 계속.
                leak = memory_db.body_noun_leak(content)
                if leak:
                    print(f"[심층메모리] 몸-명사 거부: \"{content[:50]}\" "
                          f"(몸 내부 {leak} — 정본은 코드·system_docs)")
                    continue

                existing = memory_db.search(
                    project_path=project_path, agent_id=agent_id,
                    query=fact["keywords"] or content, limit=3,
                )
                top = (memory_db.read(project_path, agent_id, existing[0]["id"])
                       if existing else None)
                if top and content in top.get("content", ""):
                    continue  # 이미 담긴 사실은 모델 호출도 DB 갱신도 하지 않는다.
                if top:
                    pending.append((fact, top))
                else:
                    memory_db.save(
                        project_path=project_path, agent_id=agent_id,
                        content=content, keywords=fact["keywords"],
                        category=fact["category"], source_ref=fact["source_ref"],
                        node=fact["node"],
                    )
                    saved_count += 1
                    print(f"[심층메모리] NEW [{fact['category']}] @{fact['node'] or '뿌리'}: \"{content[:50]}\"")

            # 같은 기존 기억을 가리키는 사실을 합친다. 옛 snapshot으로 여러 번 덮지 않는다.
            grouped = {}
            for fact, top in pending:
                if top["id"] not in grouped:
                    grouped[top["id"]] = (dict(fact), top)
                else:
                    merged_fact = grouped[top["id"]][0]
                    if fact["category"] == "작업기록":
                        merged_fact["category"] = "작업기록"
                    merged_fact["content"] += "\n" + fact["content"]
                    merged_fact["source_ref"] = json.dumps({"sources": [json.loads(merged_fact["source_ref"]), json.loads(fact["source_ref"])]}, ensure_ascii=False)
                    merged_fact["keywords"] = _merge_keywords(merged_fact["keywords"], fact["keywords"])
            pending = list(grouped.values())
            # 3단계: 본문 전체를 대조하고 UPDATE는 새 사실만 반환한다.
            verdicts = []
            if pending:
                pairs_text = "\n".join(
                    f'{i+1}. 기존: {top["content"]}\n   기존 출처: {top.get("source_ref") or "미확인"}'
                    f'\n   신규 후보: {fact["content"]}\n   신규 출처: {fact["source_ref"]}'
                    for i, (fact, top) in enumerate(pending)
                )
                batch_prompt = (
                    "각 쌍의 '기존 기억'과 '신규 정보'의 관계를 판정하라.\n"
                    "SAME(이미 기존에 포함된 사실; 표현/순서가 달라도 동일) / UPDATE(새 사실만 보충) / "
                    "REPLACE(기존이 틀렸거나 옛 정보라 새 정보로 정정·대체) / "
                    "NEW(서로 다른 정보) 중 하나씩.\n\n"
                    f"{pairs_text}\n\n"
                    '본문을 다시 쓰지 마라. 신규 후보 원문 전체를 저장한다. 새 사실이 없으면 SAME. '
                    'REPLACE는 사용자가 명시적으로 기존 사실을 정정한 경우만 선택한다. '
                    '같은 주제라도 다른 사건·날짜·대상이면 NEW이며 과거 기록을 고치지 않는다. '
                    '쌍 순서대로 JSON: {"verdicts": [{"action":"SAME|UPDATE|REPLACE|NEW"}, ...]}'
                )
                resp = oneshot_ai_call(
                    prompt=batch_prompt,
                    system_prompt="기억 관계 판정기. 쌍 순서대로 verdict 배열만 JSON으로 응답.",
                    role="background",
                )
                if resp:
                    parsed = parse_first_json(resp)
                    verdicts = (parsed or {}).get("verdicts", []) if isinstance(parsed, dict) else []

            # 4단계: 원문만 적용. 판정 누락·불명은 보류한다.
            for i, (fact, top) in enumerate(pending):
                choice = verdicts[i] if i < len(verdicts) else {}
                j = str(choice.get("action", "") if isinstance(choice, dict) else choice).strip().upper()
                addition = fact["content"]
                fact_source = fact["source_ref"]
                content = fact["content"]
                keywords = fact["keywords"]
                category = fact["category"]
                if j == "SAME":
                    print(f"[심층메모리] SAME 스킵: \"{content[:50]}\"")
                elif j == "REPLACE":
                    latest = memory_db.read(project_path, agent_id, top["id"])
                    if not latest or latest["content"] != top["content"]:
                        continue
                    if fact["category"] == "작업기록":
                        continue  # 작업 응답이 사용자 사실을 정정할 권한은 없다.
                    # 정정 이력은 보존하되 현재 발화자의 증거와 섞어 현재 사실로 취급하지 않는다.
                    replacement_source = json.loads(fact_source)
                    replacement_source["superseded"] = {"content": top["content"], "source_ref": top.get("source_ref")}
                    merged_kw = _merge_keywords(top.get("keywords", ""), keywords)
                    applied = memory_db.update(project_path, agent_id, top["id"],
                                     content=addition or content, keywords=merged_kw,
                                     source_ref=json.dumps(replacement_source, ensure_ascii=False), expected_content=top["content"])
                    if applied is False:
                        continue
                    updated_count += 1
                    print(f"[심층메모리] REPLACE: \"{content[:50]}\" → 기존 ID {top['id']} 덮어씀")
                elif j == "UPDATE":
                    if not addition or addition in top["content"]:
                        print("[심층메모리] 추가 사실 없는 UPDATE 생략")
                        continue
                    source = json.loads(fact_source)
                    source["related_memory_id"] = top["id"]
                    memory_db.save(project_path=project_path, agent_id=agent_id,
                                   content=addition, keywords=keywords, category=category,
                                   source_ref=json.dumps(source, ensure_ascii=False),
                                   node=fact.get("node") or top.get("node", ""))
                    saved_count += 1
                    print(f"[심층메모리] UPDATE: 기존 ID {top['id']}에 연결한 새 사실로 분리 저장")
                elif j == "NEW":
                    memory_db.save(project_path=project_path, agent_id=agent_id,
                                   content=addition or content, keywords=keywords, category=category,
                                   source_ref=fact_source, node=fact.get("node", ""))
                    saved_count += 1
                    print(f"[심층메모리] NEW [{category}] @{fact.get('node') or '뿌리'}: \"{content[:50]}\"")
                else:
                    print("[심층메모리] 관계 판정 불명 — 중복 저장 생략")

            if saved_count or updated_count:
                print(f"[심층메모리] 저장 {saved_count}건, 업데이트 {updated_count}건: "
                      f"\"{user_message[:40]}\"")

        except json.JSONDecodeError:
            print(f"[심층메모리] JSON 파싱 실패 (무시)")
        except Exception as e:
            print(f"[심층메모리] 실패 (무시): {e}")

    def _distill_forage_memory(self, user_message: str, ai_response: str,
                               assume_forage: bool = False):
        """포식 후 자동 증류 — 냄새지도(forage_map)에 *델타만* 누적(주인모델은 2026-09-18 은퇴 — 주인 사실은 심층 증류의 일).

        assume_forage=True(포식 브라우저 등 *정의상 항상 포식*인 표면): 메시지 cue 게이트를
        건너뛴다("강남 맛집"처럼 cue 단어 없는 정당한 포식을 놓치지 않도록). 응답 증거 게이트
        (URL·경로 유무)는 유지 — 빈 검색은 여전히 스킵.

        해마/심층메모리 증류의 *공간* 짝(docs/FORAGER_MEMORY_SCHEMA.md §4.2). forage 의도
        대화에서, 미래 탐색을 싸게 만들 *일반화 가능한 공간 지식*(폴더 정체·관습·죽은가지·
        주인 신호)만 추출한다 — 날 내용·이번에 찾은 특정 파일은 저장 안 함. 기존 지도를 함께
        넘겨 *새롭거나 교정된 것*만 내도록 한다(surprise/교정). dedup 은 저장소 UNIQUE upsert 가
        기계적으로 처리(재note=강화) → 2차 판정 LLM 불필요. 실패는 무시(파이프라인 불변).

        step 5(surface 카운터-패스): 기존 라벨을 *위반*하는 이질 내용을 만나면 그 항목에
        surface 표식 → 필터버블 반대힘([[project_augmentation_over_autonomy]]).
        """
        try:
            if not user_message or not ai_response:
                return
            msg = user_message.lower()
            if not assume_forage and not any(cue in msg for cue in self._FORAGE_CUES):
                return  # 비forage 대화 — 증류 없음 (포식 표면은 assume_forage 로 우회)
            from memory_evidence import durable_source_units, select_units
            owner_units = durable_source_units(user_message)
            if owner_units and all(u["attribution"] != "user_candidate" for u in owner_units):
                # 전달된 문서·경어 수신문·인용만으로 탐색 관습·주인 정체를 추론해 저장하지 않는다.
                _bases = sorted({u.get("basis", "") for u in owner_units} - {""})
                print(f"[포식기억] 주인 귀속 보류 — 사용자 자기 진술 없음(basis={','.join(_bases)})")
                return
            import sys, os, json
            bk = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if bk not in sys.path:
                sys.path.insert(0, bk)
            # 하드웨어 자아 게이트(누가 포식) — 공간 body 와 분리(§1)
            try:
                from runtime_utils import detect_body
                hw = detect_body().get("profile") or "pc"
            except Exception:
                hw = "pc"
            if hw == "phone":
                return  # 폰 자아는 미디어-한정(A3 후속)
            # 2차 싼 게이트(매체 무관): 응답이 실제 navigable/반구조 공간을 뒤졌나(맛집·영상 검색 등 LLM 낭비 차단).
            #   디스크 경로·URL·코드 구성·확장자를 한 집합으로 — per-medium 분기 없음(§9).
            ar_l = ai_response.lower()
            if not (self._FORAGE_EVIDENCE_RE.search(ai_response)
                    or any(w in ar_l for w in self._FORAGE_EVIDENCE_WORDS)):
                return  # 포식 흔적 없음 — 증류 스킵(LLM 호출 안 함)
            import forage_memory
            from consciousness_agent import oneshot_ai_call

            # 1) 기존 지도(전 공간) 요약 → "이미 아는 것"으로 (델타만 추출하도록). body 표기로 공간 구분.
            known = forage_memory.recall(body=None, query=None, limit=40)
            known_lines = []
            for m in known.get("map", []):
                known_lines.append(f'- [{m.get("body","?")}/{m["kind"]}] {m["locus"]}: {m["claim"]}')
            known_text = "\n".join(known_lines) if known_lines else "(아직 없음)"

            # 2) 경량 LLM 으로 *일반화 가능한 공간 지식* 델타 추출 — ★공간-중립 단일 프롬프트.
            #   매체별 분기 없음: AI 가 무엇을 포식했는지 *명명*(space)한다(forager=AI, §9 불변 2축).
            extract_prompt = f"""이번 대화는 어떤 공간을 *포식*(이미 있는 걸 찾기)한 것이다 — 디스크 폴더·코드레포·웹·책·외장볼륨 중 하나.
미래의 탐색을 싸게 만들 **일반화 가능한 공간 지식**만 추출하라. 이번에 찾은 특정 항목·날 내용은 제외하고, *다음에도 쓸* 지도만:

먼저 **space**(무엇을 포식했나)를 명명하라:
- "mac"=내 홈 디스크 / "code:<레포명>"=코드레포 / "web"=웹 / "book:<제목>"=책 / "disk:<라벨>"=외장볼륨

그다음 지도(공간 종류에 맞게 자연히 채워라):
- map.identity: "이 위치 = X"(폴더/모듈/1차출처의 정체 — 예 "발표자료 폴더", "backend/=라우터", "내 논문=NYU Scholars")
- map.convention: 주인의 정리·명명·탐색 관습(예 "발표=장소+날짜", "IBL 액션=src에 정의→build로 생성", "동명이인=분야어로 좁힘")
- map.dead_branch: "여기엔 그것 없음"(+ prune_reason: 왜 아마 없나 — 폐기가능)
- map.substrate: 기질 가용성(예 "EXIF 색인 없음", "1500줄 파일제한", "이 사이트=페이월")

규칙:
- **이미 아는 것과 같으면 내지 마라**(새롭거나 교정된 것만).
- **★자기서술 금지(포식≠자기소개)**: 포식 대상이 이 시스템(IndieBiz OS) 자신의 코드라도, *자신의 인지·기억 사고방식*(포식 기억·냄새지도·의식/무의식 에이전트·인지 파이프라인·증류·해마·Reflex·execution_memory·owner_model)을 서술하는 것은 공간 지식이 아니라 자기 자신을 자신에게 다시 적는 순환이다 → 기록 금지. 코드 공간을 포식했다면 *일반화 가능한 코드 관습·구조*(예 "핸들러 op 분기=`_OP_DISPATCHERS`", "IBL 액션=src에 정의→build로 생성", "통화 봉투=message+items 분리")만 기록하라 — 그 코드가 *무엇을 하는 인지 시스템인지*를 논평하지 마라.
- **owner vs convention 경계**: 검색·탐색 *방법/기법*(예 "흔한 이름은 전공·소속 등 비식별 고유값으로 좁혀라", "동명이인 주의", "본명이 남는 공개기록 우선")은 *주인이 누구인가*가 아니다 → 그 공간의 map.convention 으로(owner 금지). owner.habit/lexicon 은 *주인 자신*에 관한 것만(예 "이력서를 docx+pdf 쌍으로 관리"=정리습관 / "Amari=甘利俊一"=어휘매핑).
- prior_class: 동질이라 싸게 재검증되면 "structural", 의미·정체 주장이면 "semantic".
- surface: *이미 아는 라벨을 위반*하는 이질 내용을 봤다면(예 "연구 폴더인 줄 알았는데 개인 투자 메모") 그 locus 를 surface 에 적고 why.
- ★간결히: map 최대 6건, 각 claim 은 한 문장. 그보다 많으면 출력이
  잘려(max_tokens) 전부 유실된다 — 가장 일반화 가능한 것만 골라라. 설명·서론 없이 JSON 만.
- 확실치 않으면 비워라. JSON 으로만 응답.

이미 아는 지도(전 공간):
{known_text[:1500]}

사용자: {user_message[:300]}
AI 답변: {ai_response[:1400]}

응답 형식(빈 배열 허용):
{{"space":"mac|code:<repo>|web|book:<title>|disk:<label>",
 "map":[{{"locus":"위치(파일시스템이면 절대경로, 웹이면 URL host/path — 주제 이름이 아니라 자리)","kind":"identity|convention|dead_branch|substrate","claim":"...","prior_class":"structural|semantic","prune_reason":"(dead_branch면)","generalizes":true}}],
 "surface":[{{"locus":"(있으면)","why":"..."}}]}}"""

            resp = oneshot_ai_call(
                prompt=extract_prompt,
                system_prompt="포식 지도 증류기. 포식한 공간을 명명하고 일반화 가능한 공간 지식 델타만 JSON으로. 특정 항목·날 내용 금지.",
                role="background",
            )
            if not resp:
                return
            from runtime_utils import parse_first_json
            data = parse_first_json(resp)
            if not isinstance(data, dict):
                print("[포식기억] JSON 추출 실패 (무시)")
                return

            # 공간 = AI 가 명명(없으면 mac). 매체가 늘어도 분기 없음 — 라벨 그대로 body 키.
            body = self._normalize_space(data.get("space"), ai_response, user_message)
            prov = {"query": user_message[:120]}
            # 파일시스템 공간(mac/code:/disk:): LLM 이 상대경로·추상 슬러그를 줄 수 있음
            #   → 실존 검증 후 정규화(Fix 1). 실존하면 절대경로(freshness 추적), 아니면
            #   web 처럼 추상 locus 로 강등(mtime 면제). web/book: 은 이미 추상 → 그대로.
            is_fs = self._is_fs_space(body)
            repo_root = self._repo_root_path(ai_response, user_message) if body.startswith("code") else None
            noted = 0
            for m in (data.get("map") or [])[:6]:
                locus, kind, claim = m.get("locus"), m.get("kind"), m.get("claim")
                if not locus or not kind or not claim:
                    continue
                # Fix 2: 자기 인지·기억 사고방식 서술은 공간 지식이 아니다 → 드롭.
                if self._is_self_narration(claim, locus):
                    print(f"[포식기억] 자기서술 드롭 map[{kind}]: \"{str(claim)[:48]}\"")
                    continue
                if is_fs:
                    locus, _real = self._resolve_fs_locus(locus, repo_root, body)
                    if not _real:
                        print(f"[포식기억] 주소 미해소 드롭 map[{kind}] {str(locus)[:60]}")
                        continue
                r = forage_memory.note_map(
                    body=body, locus=locus, kind=kind, claim=claim,
                    prior_class=m.get("prior_class") or "structural",
                    confidence=0.7, provenance=dict(prov),
                    prune_reason=m.get("prune_reason"),
                    generalizes=bool(m.get("generalizes")))
                if r.get("success"):
                    noted += 1
                    tag = " ⇧territory(빈도 결정화)" if r.get("promoted_territory") else ""
                    print(f"[포식기억] {r['action']} map[{kind}]{tag}: \"{claim[:48]}\"")
            # step 5: surface — 기존 라벨 의심 표식(이질 내용 발견).
            for s in (data.get("surface") or [])[:4]:
                why = s.get("why") or ""
                loc = s.get("locus")
                marked = []
                if loc:  # 위반된 폴더 라벨
                    for x in forage_memory.recall(query=loc, limit=5).get("map", []):   # 몸 표기는 주소에서 정해진다 — 거르지 않는다
                        if x["locus"] == loc:
                            forage_memory.mark_surface(entry_id=x["id"], table="forage_map", on=True)
                            marked.append(f"map#{x['id']}")
                if marked:
                    print(f"[포식기억] surface 표식({','.join(marked)}): \"{why[:48]}\"")

            if noted:
                print(f"[포식기억] 증류 {noted}건: \"{user_message[:40]}\"")
        except json.JSONDecodeError:
            print("[포식기억] JSON 파싱 실패 (무시)")
        except Exception as e:
            print(f"[포식기억] 증류 실패 (무시): {e}")

    def _after_response(self, user_message: str, response: str, *,  # noqa: C901
                        tool_calls=None, hippo_score: float = None, top_code: str = None,
                        write_experience: bool = True, write_deep: bool = True,
                        write_forage: bool = True, assume_forage: bool = False,
                        guides_used=None, turn_tokens: int = None, turn_cost=None):
        """턴 종료 후 메모리 쓰기 초크포인트 — 진입점마다 복붙되던 증류 배선을 한 곳으로.

        WS 채팅·에이전트 채널·포식 브라우저가 각자 복붙하던 [경험증류 + 심층메모리 + 포식기억]
        블록을 흡수한다([[architecture_entrypoint_drift_shared_boot]] 축적흡수 균열 방어). *무엇을
        쓸지*는 진입점이 플래그로 선언(forage 브라우저=forage만), *어떻게·순서·에러격리*는 여기
        한 곳. 새 메모리 종류 추가=이 메서드 한 곳 / 새 진입점=이 한 줄 호출(개별 종류 못 빠뜨림).

        입력 획득(tool_calls/hippo_score/top_code)은 진입점마다 방식이 달라(스코프 변수 vs 재계산)
        호출부에 남긴다 — 여기선 받은 값만 쓴다. 각 쓰기는 독립 try 로 격리(하나 실패가 나머지
        안 막음). response 없으면 아무것도 안 씀. 실패는 파이프라인 불변(무시).
        """
        if not response:
            return
        log = getattr(self, "_log", None) or print
        if not _principal_owner():
            log("[기억] 회원·이웃 주체의 턴 — 주인 저장소(해마·심층·포식·가이드)에 쓰지 않음(회원 로컬 회상은 2단계)")
            return
        from thread_context import get_goal_eval_outcome
        evaluation = get_goal_eval_outcome()  # 경험 증류가 소비하기 전에 기억용 상태를 보존한다.
        # 1) 경험 증류(해마) — 도구 실행이 있었을 때만. + Reflex top-1 성공률 피드백.
        if write_experience and tool_calls and (turn_cost or {}).get("request_intent") != "context_update":
            try:
                from ibl_usage_rag import distill_experience, record_recall_outcome
                distill_experience(user_message, tool_calls, hippo_score, top_code=top_code,
                                   turn_tokens=turn_tokens, turn_cost=turn_cost)
                record_recall_outcome(top_code, hippo_score, tool_calls,
                                      turn_tokens=turn_tokens)
            except Exception as e:
                log(f"[경험증류] 오류 (무시): {e}")
        # 2) 심층/의미 메모리 증류.
        memory_approved = not evaluation or (
            evaluation.get("status") not in {"UNKNOWN", "NOT_ACHIEVED"}
            and evaluation.get("achieved", True)
        )
        if not write_deep:
            log("[심층메모리] 주인이 직접 한 말이 아닌 턴(에이전트·예약·미선언) 또는 표면 제외 — 생략")
        elif memory_approved:
            try:
                self._distill_deep_memory(user_message, response)
            except Exception as e:
                log(f"[심층메모리] 오류 (무시): {e}")
        else:
            log("[심층메모리] 검수 미완료 — 장기 기억 저장 생략")
        # 3) 포식 기억 증류(냄새지도).
        if write_forage:
            try:
                self._distill_forage_memory(user_message, response, assume_forage=assume_forage)
            except Exception as e:
                log(f"[포식기억] 오류 (무시): {e}")
        # 4) 가이드 되먹임 — 쓴 놈이 고친다. 가이드는 8종 기억 중 유일하게 *쓰는 쪽*이
        #    없던 기억이라(해마=실행에서·심층=대화에서·포식=포식에서 증류되는데 가이드만
        #    사람이 손으로 쓰고 방치), 그 공백이 2026-08-17 에 81KB 수동 정리로 청구됐다.
        #    가장 좋은 감사자는 방금 그 가이드를 쓴 에이전트다 — 순찰은 추측하지만 이쪽은 안다.
        #    관찰=자동 덧붙임 / 사실오류=기계 검증 후 수정 / 방침변경=제안 큐. 상세: guide_feedback.
        if guides_used is None:
            try:
                from guide_registry import take_injected
                guides_used = take_injected()
            except Exception:
                guides_used = []
        if guides_used:
            try:
                from guide_feedback import review_used_guides
                review_used_guides(guides_used, user_message, response, tool_calls=tool_calls)
            except Exception as e:
                log(f"[가이드되먹임] 오류 (무시): {e}")

    def _after_response_async(self, user_message: str, response: str, *,
                              tool_calls=None, hippo_score: float = None, top_code: str = None,
                              turn_tokens: int = None, pursuit_packet=None,
                              write_deep: bool = False):
        """_after_response 를 **영속 큐**(distill_queue)에 적재 — 증류가 턴(스트림 종료·
        에피소드 END·총 소요 측정)을 붙잡지 않게(ep889: 실작업 4.6분에 증류 꼬리 6분) 하되,
        데몬 스레드 시절과 달리 프로세스가 죽어도 작업이 사라지지 않는다(2026-09-02: 행으로
        먼저 남기고 → 단일 워커 소비 → 실패 재시도 원장 → 종료 drain → 부팅 resume).

        컨텍스트 동반 3종(메인에서 스냅샷해 값으로 넘긴다 — threading.local 은 스레드로 안 간다):
        - thread_context: agent_id/project_id/agent_name → ident. goal_eval_outcome 은 메인에서
          읽고 *메인에서 소비(clear)* 후 payload 로 — 안 그러면 NOT_ACHIEVED 게이트가 워커에서
          안 보여 실패 실행이 해마에 증류된다(복리 출혈 방어 무력화).
        - 에피소드 버퍼(contextvars): copy_context 로 같은 _Episode 를 공유 — 워커의 증류 print 가
          버퍼에 쌓이고, 완료 시 refresh_episode 가 저장된 행에 꼬리를 재합류시킨다.
        - 경량 프로바이더 동시성: 워커가 하나라 증류끼리는 안 다투고, 분류기와는
          oneshot_ai_call 의 _oneshot_call_lock 이 직렬화.
        큐 적재 자체가 실패하면(DB 잠금 등) 옛 데몬 스레드 경로로 **강등해 실행하고 그 사실을
        말한다** — 영속은 잃어도 이번 턴의 기억은 잃지 않는다.
        """
        import contextvars
        from thread_context import (
            get_current_agent_id, get_current_project_id, get_current_agent_name,
            get_current_registry_key, get_goal_eval_outcome, clear_goal_eval_outcome,
            get_current_task_id,
        )
        from episode_logger import EpisodeLogger
        if not _principal_owner():
            # 영속 큐 워커는 주체를 복원하지 못한다(payload 에 없음) — 적재 자체를 막는다.
            clear_goal_eval_outcome()
            (getattr(self, "_log", None) or print)("[기억] 회원·이웃 주체의 턴 — 증류 큐에 적재하지 않음")
            return

        ident = {
            "registry_key": get_current_registry_key(),
            "project_id": get_current_project_id(),
            "agent_id": get_current_agent_id(),
            "agent_name": get_current_agent_name(),
        }
        _ge = get_goal_eval_outcome()
        clear_goal_eval_outcome()  # 소비는 메인 컨텍스트에서 — 다음 메시지로 안 새게(기존 계약 유지)
        try:
            from guide_registry import take_injected
            guides_used = take_injected()   # ★메인에서 스냅샷 — threading.local 은 스레드로 안 간다
        except Exception:
            guides_used = []
        payload = {
            "user_message": user_message, "response": response,
            "tool_calls": tool_calls, "hippo_score": hippo_score, "top_code": top_code,
            "guides_used": guides_used,
            "turn_tokens": turn_tokens,   # 턴 마감 시점에 읽은 값 — 증류 자체 소모는 미포함
            "goal_eval": _ge,
            "task_id": get_current_task_id(),
            "pursuit": pursuit_packet,
            # 심층기억은 주인이 직접 한 말에서만 자란다 — 진입점이 선언한 발화자 축(fail-closed).
            "write_deep": bool(write_deep),
        }
        from supervision_bus import current as current_supervisor
        supervisor = current_supervisor()
        if supervisor:
            import time
            payload["turn_cost"] = supervisor.store.cost_summary(time.monotonic() - supervisor.started)
            payload["turn_cost"]["request_intent"] = supervisor.request_intent
            supervisor.log("cost.summary", role="harness", cost=payload["turn_cost"])
            print("[감독비용] " + json.dumps(payload["turn_cost"], ensure_ascii=False))
        ctx = contextvars.copy_context()
        ep = EpisodeLogger.current()
        try:
            from distill_queue import DistillQueue
            DistillQueue.get().enqueue(self, payload, ident=ident, ctx=ctx, ep=ep)
            return
        except Exception as e:
            print(f"[증류큐] 적재 실패 — 비영속 스레드로 강등 실행: {type(e).__name__}: {e}")

        import threading
        from distill_queue import _Job, DistillQueue as _DQ

        def _run():
            try:
                _DQ._execute(_Job(None, self, payload, ident, ctx=ctx, ep=ep))
            except Exception as e:
                print(f"[증류] 백그라운드 오류 (무시): {e}")
            finally:
                EpisodeLogger.refresh_episode(ep)

        threading.Thread(target=_run, daemon=True, name="distill-after-response").start()
