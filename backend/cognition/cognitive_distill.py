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

            from memory_evidence import (durable_source_units, grounded_fact)
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
타인의 제안을 사용자가 명시적으로 채택했다면 인용 내용과 사용자의 채택 발화를 함께 선택한다.
(이름, 중요한 날짜, 사용자 선호, 사용자가 확정한 결정사항)
문체·존대·접속사·요청 형식은 탈락 사유가 아니다. 요청형의 지속 선호도 의미와 적용 범위를 읽는다.
eligible은 내용 유무만 뜻한다. 타인의 인용·전달문은 직접 채택 근거가 없으면 사용자 사실이 아니다. AI의 답변·권고·도구 관측은
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
말인지 문맥에서 판단하라. 접속사나 대명사만으로 보류하지 마라. 실제로 앞 문맥이 필요한 단위는, 대상이 담긴 앞
단위를 source_ids 에 **함께** 골라라(여러 id 는 한 기억으로 이어 붙는다). 같은 메시지 안에 대상이
없으면(이전 턴·AI 답변에만 있으면) 확인할 수 없으면 보류한다. 없는 지시 대상을 추측하지 마라.
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
        """구판 큐 호환 입구: AI 답변만으로 공간 관측을 발명하지 않는다.

        현재 쓰기는 tool_calls를 가진 unified_distill.prepare/apply_forage 한 경로다.
        옛 큐에는 실제 관측 신원/범위가 없어 별도 모델 호출과 저장을 생략한다.
        """
        return {"status": "skipped", "reason": "unified_observation_required"}

    def _after_response(self, user_message: str, response: str, *,  # noqa: C901
                        tool_calls=None, hippo_score: float = None, top_code: str = None,
                        write_experience: bool = True, write_deep: bool = True,
                        write_forage: bool = True, assume_forage: bool = False,
                        guides_used=None, turn_tokens: int = None, turn_cost=None, presented=None,
                        distill_job=None, deep_confirmed=None):
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
        if distill_job is not None:
            from unified_distill import run
            import distill_ledger as ledger
            ledger.create(distill_job)
            key = distill_job["job_key"]
            try:
                return run(distill_job)
            finally:
                state = ledger.read(key)
                confirmed = [r["id"] for name, r in state["receipts"].items()
                             if name.startswith("deep:") and r.get("status") == "same" and r.get("id")]
                log(f"[통합증류] 상태={state['status']} — 종류별 선별·생략 사유는 증류 원장에 보존")
                ledger.once(key, "feedback", lambda: self._after_response(
                    user_message, response, tool_calls=tool_calls, hippo_score=hippo_score,
                    top_code=top_code, write_experience=False, write_deep=False, write_forage=False,
                    guides_used=guides_used, turn_tokens=turn_tokens, turn_cost=turn_cost,
                    presented=presented, deep_confirmed=confirmed))
                if tool_calls:
                    from ibl_usage_rag import record_recall_outcome
                    ledger.once(key, "recall_outcome", lambda: record_recall_outcome(
                        top_code, hippo_score, tool_calls, turn_tokens=turn_tokens))
        from thread_context import get_goal_eval_outcome
        evaluation = get_goal_eval_outcome()  # 경험 증류가 소비하기 전에 기억용 상태를 보존한다.
        # 제시→사용 결합(2026-09-18): 심층기억은 증류가 SAME/UPDATE 로 다시 만난 항목만 used_at 을 올린다 —
        # 그 전후를 대조해 '확인됨'을 가른다. 값이 없으면(옛 큐 행·다른 진입점) 결합은 조용히 비운다.
        import associative_recall as _ar
        _deep = next((p for p in (presented or []) if p.get("source") == "recalled_memory"), None)
        _deep_db = (_deep or {}).get("join", {}).get("db", "")
        _deep_before = _ar.deep_used_at(_deep_db, (_deep or {}).get("ids") or [])
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
        if not write_deep and deep_confirmed is None:
            log("[심층메모리] 주인이 직접 한 말이 아닌 턴(에이전트·예약·미선언) 또는 표면 제외 — 생략")
        elif write_deep:
            try:
                self._distill_deep_memory(user_message, response)
            except Exception as e:
                log(f"[심층메모리] 오류 (무시): {e}")
        # 3) 포식 기억 증류(냄새지도).
        if write_forage:
            try:
                self._distill_forage_memory(user_message, response, assume_forage=assume_forage)
            except Exception as e:
                log(f"[포식기억] 오류 (무시): {e}")
        # 4) 가이드 되먹임 — 쓴 놈이 고친다. 가이드는 7종 기억 중 유일하게 *쓰는 쪽*이
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
        # 5) 증류 후 활용 확인 — 턴 종료 관측에 같은 recall_id로 합류한다. 보고는 사용 집합을 합치며 점수는 고치지 않는다.
        if presented:
            try:
                _deep_after = _ar.deep_used_at(_deep_db, (_deep or {}).get("ids") or [])
                touched = [i for i, u in _deep_after.items() if u and u != _deep_before.get(i)]
                touched = list(set(touched) | set(deep_confirmed or []))
                _ar.record_usage(presented, tool_calls=tool_calls, response=response, deep_touched=touched)
            except Exception as e:
                log(f"[연상:사용] 오류 (무시): {e}")

    def _after_response_async(self, user_message: str, response: str, *,
                              tool_calls=None, hippo_score: float = None, top_code: str = None,
                              turn_tokens: int = None,
                              write_deep: bool = False, presented=None, model_descriptor=None,
                              write_experience=True, write_forage=True):
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
        큐 적재에 실패하면 원문 에피소드는 보존하고 오류를 남긴다. 무기록 저장으로 강등하지 않는다.
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
            # 심층기억은 주인이 직접 한 말에서만 자란다 — 진입점이 선언한 발화자 축(fail-closed).
            "write_deep": bool(write_deep),
            "write_experience": bool(write_experience), "write_forage": bool(write_forage),
            "presented": presented,   # 제시→사용 결합 키(2026-09-18) — 워커에서 record_usage
        }
        from supervision_bus import current as current_supervisor
        supervisor = current_supervisor()
        if supervisor:
            import time
            payload["turn_cost"] = supervisor.store.cost_summary(time.monotonic() - supervisor.started)
            payload["turn_cost"]["request_intent"] = supervisor.request_intent
            supervisor.log("cost.summary", role="harness", cost=payload["turn_cost"])
            print("[감독비용] " + json.dumps(payload["turn_cost"], ensure_ascii=False))
        from thread_context import in_rehearsal
        if in_rehearsal():
            # 리허설은 삶이 아니다 — 비용 요약까지만 남기고 경험·심층·포식 기억에는 올리지 않는다.
            (getattr(self, "_log", None) or print)("[기억] 리허설 턴 — 증류 큐에 적재하지 않음")
            return
        ctx = contextvars.copy_context()
        ep = EpisodeLogger.current()
        from unified_distill import snapshot
        payload = snapshot(self, payload, ident, descriptor=model_descriptor, episode=ep)
        try:
            from distill_queue import DistillQueue
            DistillQueue.get().enqueue(self, payload, ident=ident, ctx=ctx, ep=ep)
            return
        except Exception as e:
            print(f"[증류큐] 적재 실패 — 기억 저장 생략, 원문 원장 보존: {type(e).__name__}: {e}")
            from episode_logger import record_trajectory_event
            record_trajectory_event("distillation.enqueue_failed", {"job_key": payload["job_key"],
                                                                     "reason": type(e).__name__})
