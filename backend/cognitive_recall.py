"""
cognitive_recall.py - 0단계 연상 회상 믹스인
IndieBiz OS Core

agent_cognitive.py 에서 분리(2026-07-17, 1500줄 규칙 모듈화). 사용자 명령이 오면
가장 먼저 도는 연상 경로 — 실행기억(해마)+관련기억(심층 메모리)+포식기억(냄새지도)+
디스크 골격을 합성한다. 회상(읽기) 전용 — 증류(쓰기)는 cognitive_distill.py 가 짝.
_FORAGE_CUES(포식 의도 게이트)는 여기 정의하고 증류 쪽도 self 로 공유한다.
"""

from typing import Optional


class CognitiveRecallMixin:
    """0단계 연상 — 해마·심층·포식·디스크골격 회상 메서드 모음."""

    def _build_execution_memory(self, user_message: str, action_hint: Optional[str] = None,
                                include_related: bool = True) -> tuple:
        """연상기억 생성 — 실행기억(해마) + 관련기억(심층 메모리)

        파이프라인의 모든 에이전트(무의식/의식/실행/평가)가 공유하는 통합 기억.
        사용자 명령 당 해마 검색은 단 1회. 호출 측은 반환된 top_score를 그대로 사용하여
        Reflex 분기, 경험 증류 판정 등에서 추가 검색을 피한다.

        Args:
            user_message: 사용자 명령
            action_hint: 마법책에서 사용자가 명시적으로 선택한 액션 ID ("sense:price" 등).
                지정되면 해마 시맨틱 검색을 건너뛰고 그 액션을 Top-1로 <execution_memory> 합성.
                잘못된 액션 ID면 자동으로 해마 검색으로 폴백.

        Returns:
            (xml: str, top_score: float, top_code: str)
            - xml: <execution_memory> + <related_memory> 결합된 문자열 (없으면 "")
            - top_score: 해마 최고 점수 (action_hint 적용 시 1.0)
            - top_code: 해마 최고 점수 항목의 ibl_code (action_hint 적용 시 "[node:action]")
        """
        try:
            exec_xml, top_score, top_code = ("", 0.0, "")
            if action_hint:
                from ibl_usage_rag import build_execution_memory_from_hint
                exec_xml, top_score, top_code = build_execution_memory_from_hint(action_hint)
                if not exec_xml:
                    print(f"[연상] action_hint='{action_hint}' 유효하지 않음 — 해마 검색으로 폴백")

            if not exec_xml:
                from ibl_usage_rag import build_execution_memory
                allowed_nodes = self.config.get("allowed_nodes")
                allowed_set = None
                if allowed_nodes:
                    from ibl_access import resolve_allowed_nodes
                    allowed_set = resolve_allowed_nodes(allowed_nodes)
                exec_xml, top_score, top_code = build_execution_memory(user_message, allowed_set)

            # 심층 메모리에서 관련기억 검색 → 연상기억 합성.
            #   ★include_related=False(포식 등): 무상태 검색을 개인 사실(심층 메모리)이 하이재킹하지
            #   않도록 관련기억 주입을 끈다 — 포식은 이미 심층 메모리에 *쓰지 않으며*(무상태), 정당한
            #   개인화는 포식기억(owner_model 웹 관습)이 담당한다. 넓은 질의가 최근 관심사로 좁혀지는
            #   필터버블 드리프트 방지. (실행기억[해마]·포식기억·디스크골격은 그대로 유지.)
            related = self._search_related_memory(user_message) if include_related else ""
            result = exec_xml
            if related:
                result = (result + "\n" + related) if result else related

            # 포식 기억(냄새지도) — ★실행기억처럼 *항상-on*. 회상은 싸고(LLM 0, DB+필터), 무관하면
            #   query 필터가 빈 결과로 자기-억제한다(비용~0). 주인모델(owner)은 query 무관 상시 노출
            #   =냄새(scent) → 명시 명령 없이도 능동 포식을 촉발. map 은 query 필터(관련 위치만).
            #   FORAGER_MULTIBODY_DESIGN §주입(THINK-게이트 폐기, 관련성=query 가 자연 게이트).
            forage = self._search_forage_memory(user_message)
            if forage:
                result = (result + "\n" + forage) if result else forage

            # 거친 디스크 골격(어디에) — ★포식 의도일 때만(상시-on 폐기, 웹랜드마크와 같은 게이트).
            #   집중 관심 폴더 아래 거친 디렉토리 트리(맥/윈도우/리눅스 각자 자기 루트). ~5천 자라
            #   파일·디스크 질의에만 값을 하고 그 외엔 무관 → _FORAGE_CUES 없으면 빈 결과(메서드 내 게이트).
            #   깊은 상세·큐레이션은 위 forager 냄새가 관련시 페이징. focus_map.py(헌법1조).
            skeleton = self._build_disk_skeleton(user_message)
            if skeleton:
                result = (result + "\n" + skeleton) if result else skeleton

            # ★웹 랜드마크(참고지도)는 여기서 bespoke 주입하던 것을 폐기 —
            #   data/guides/web_search.md(웹 검색 가이드) 안으로 접었다. 일반 에이전트는
            #   read_guide/의식 get_guide_list 로 선택적으로 읽고, 포식 표면은 forage_chat 이
            #   그 가이드를 항상 주입한다(포식=정의상 항상 웹검색). 키워드 게이트 사각지대 제거.

            if result:
                parts = []
                if "execution_memory" in result:
                    parts.append("실행기억")
                if "related_memory" in result:
                    parts.append("관련기억")
                if "forage_memory" in result:
                    parts.append("포식기억")
                if "disk_skeleton" in result:
                    parts.append("디스크골격")
                print(f"[연상] {'+'.join(parts)}: \"{user_message[:40]}\"")
            else:
                print(f"[연상] 빈 결과: \"{user_message[:40]}\"")

            return (result, top_score, top_code)
        except Exception as e:
            import traceback
            print(f"[연상] 생성 실패: {e}")
            traceback.print_exc()
            return ("", 0.0, "")

    def _search_related_memory(self, user_message: str) -> str:
        """심층 메모리에서 관련기억 검색 (top-3)

        사용자 메시지를 키워드로 심층 메모리를 검색하여
        <related_memory> XML 블록으로 반환한다.
        """
        try:
            import sys
            import os
            # memory_db 패키지 경로 추가
            mem_pkg = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..",
                "data", "packages", "installed", "tools", "memory"
            )
            if mem_pkg not in sys.path:
                sys.path.insert(0, mem_pkg)
            import memory_db

            from thread_context import get_current_agent_id
            agent_id = get_current_agent_id()
            project_path = str(self.project_path)

            # ★점수 바닥(자동 주입은 정밀도 우선): LIKE 폴백 끄고(semantic_only) 시맨틱 컷오프를
            #   0.45 로 올린다 — 키워드만 겹치는 무관 기억(예: 'kind:operator' 질의에 무의식-분류기)
            #   이 매번 3건 끌려오던 노이즈 제거. 바닥 미달이면 빈 결과 = 주입 안 함.
            results = memory_db.search(
                project_path=project_path,
                agent_id=agent_id,
                query=user_message,
                limit=3,
                semantic_only=True,
                min_score=0.45,
            )
            if not results:
                return ""

            # 전문 조회 (preview는 100자 잘림이므로)
            items = []
            for r in results:
                # last_seen은 read()가 used_at을 now로 갱신하기 전 값(search 결과)에서 취한다.
                # 마지막으로 확인된(사용되거나 만들어진) 날짜 — 에이전트가 낡음을 스스로 판단하도록.
                last_seen = (r.get("used_at") or r.get("created_at") or "")[:10]
                full = memory_db.read(project_path, agent_id, r["id"])
                if full:
                    cat = full.get("category", "")
                    kw = full.get("keywords", "")
                    content = full.get("content", "")
                    meta = f' category="{cat}"' if cat else ""
                    meta += f' keywords="{kw}"' if kw else ""
                    meta += f' last_seen="{last_seen}"' if last_seen else ""
                    items.append(f"  <memory{meta}>{content}</memory>")

            if not items:
                return ""

            xml = (
                '<related_memory note="심층 메모리에서 연상된 관련 기억입니다. 참고용. '
                'last_seen은 그 기억이 마지막으로 확인된 날짜이니, 오래된 기억은 현재와 다를 수 있음을 감안하세요.">\n'
                + "\n".join(items)
                + "\n</related_memory>"
            )
            print(f"[연상:관련기억] {len(items)}건 검색됨: \"{user_message[:40]}\"")
            print(f"[연상:관련기억] 내용:\n{xml}")
            return xml

        except Exception as e:
            print(f"[연상:관련기억] 검색 실패 (무시): {e}")
            return ""

    # 포식 의도 단서 — *이미 있는 걸 찾기* 의도 게이트(매체 무관, 싸고 너그럽게).
    #   ★공간(어느 몸: 디스크/코드/웹/책/볼륨…)은 키워드로 재유추하지 않는다 — 증류기 LLM 이
    #   명명한다(forager=AI, FORAGER_MULTIBODY_DESIGN §9 "불변 2축"). 여기 cue 는 *비용 게이트*일
    #   뿐: 비포식 잡담에 회상/증류 LLM 을 안 돌리려는 것. 매체가 늘어도 이 목록은 안 늘어난다.
    #   (회상 게이트=여기 _build_disk_skeleton, 증류 게이트=cognitive_distill 이 self 로 공유.)
    _FORAGE_CUES = (
        "찾", "검색", "어디", "뒤져", "뒤지", "파일", "사진", "자료", "폴더",
        "문서", "디스크", "볼륨", "찍은", "받은", "저장한", "예전", "지난",
        "코드", "코드베이스", "함수", "클래스", "구현", "정의", "모듈", "리포",
        "웹", "온라인", "인터넷", "구글", "논문", "기사",
        "find", "search", "where", "locate", "file", "photo", "folder",
        "document", "disk", "volume", "code", "codebase", "function",
        "implement", "module", "repo", "defined", "web", "online", "scholar", "arxiv",
    )

    def _search_forage_memory(self, user_message: str) -> str:
        """포식 기억(냄새지도) 회상 — ★실행기억처럼 항상-on(0단계 _build_execution_memory).

        회상은 싸다(LLM 0, SQLite+키워드필터). 무관하면 query 필터가 빈 결과로 자기-억제(비용~0).
        map 은 query 필터(관련 위치만), owner(주인모델)는 query 무관 상시 노출=냄새(scent)로 능동
        포식 촉발(filter_owner=False). 전 body 회상(query 가 자기-스코핑 §9). 해마 <execution_memory>·
        심층 <related_memory> 의 *공간* 짝(F2). 맥 자아 전용. 실패는 무시(파이프라인 불변).
        """
        try:
            import sys, os
            bk = os.path.dirname(os.path.abspath(__file__))
            if bk not in sys.path:
                sys.path.insert(0, bk)
            # 하드웨어 자아 게이트(누가 포식) — 폰 자아는 미디어-한정(A3 후속)
            try:
                from runtime_utils import detect_body
                hw = detect_body().get("profile") or "mac"
            except Exception:
                hw = "mac"
            if hw == "phone":
                return ""
            import forage_memory
            xml = forage_memory.recall_xml(body=None, query=user_message, limit=12,
                                           filter_owner=False)
            return xml
        except Exception as e:
            print(f"[포식기억] 회상 실패 (무시): {e}")
            return ""

    def _build_disk_skeleton(self, user_message: str = "") -> str:
        """거친 디스크 골격 회상 — 데스크탑(맥/윈도우/리눅스), *포식 의도일 때만*(웹랜드마크와 같은 게이트).

        집중 관심 폴더 아래 거친 디렉토리 트리("어디에"). focus 루트는 focus_map 이 몸별 해소 —
        focus 폴더(어휘)는 몸 독립, 생성기 바인딩만 몸별(헌법1조). 캐시(TTL)라 매 메시지 walk 없음.
        깊은 상세·큐레이션은 forager 냄새 몫. 실패는 무시(파이프라인 불변).

        ★게이트(상시-on 폐기): 디스크 골격은 ~5천 자인데 *파일·디스크 질의*에만 값을 한다 — 아키텍처
        ·대화·버그 질의엔 무관 폴더 목록을 매번 깔던 낭비(측정). _FORAGE_CUES(찾기·파일·폴더·디스크…)
        없으면 빈 결과. 웹랜드마크가 "웹 의도일 때만"인 것과 같은 의도 게이트.

        ★폰 제외(의도): 안드로이드 스코프드 스토리지라 os.walk 가 공유 스토리지에 안 먹히고
        (파일 접근은 MediaStore 경유), 폰에선 거친 디스크 지도 실익이 작다(사용자 결정). 빈 결과로
        '지원하는 척' 안 한다 — _search_forage_memory 의 폰 게이트와 같은 자리.
        """
        # 포식 의도 게이트 — 비포식(아키텍처·대화·버그) 질의엔 골격을 넣지 않는다.
        if not any(cue in (user_message or "").lower() for cue in self._FORAGE_CUES):
            return ""
        try:
            import sys, os
            bk = os.path.dirname(os.path.abspath(__file__))
            if bk not in sys.path:
                sys.path.insert(0, bk)
            try:
                from runtime_utils import detect_body
                profile = detect_body().get("profile") or "mac"
            except Exception:
                profile = "mac"
            if profile == "phone":
                return ""  # 폰 미지원(스코프드 스토리지·실익 작음)
            import focus_map
            return focus_map.build_coarse_map_xml(profile=profile)
        except Exception as e:
            print(f"[디스크골격] 생성 실패 (무시): {e}")
            return ""
