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
            - xml: <execution_memory> + <memory_map> 결합된 문자열 (없으면 "")
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

            # 심층 기억의 지도(목차) → 연상기억 합성 (내용 자동 주입 아님 — 2026-09-03).
            #   ★include_related=False(포식 등): 무상태 검색을 개인 사실(심층 메모리)이 하이재킹하지
            #   않도록 관련기억 주입을 끈다 — 포식은 이미 심층 메모리에 *쓰지 않으며*(무상태), 정당한
            #   개인화는 포식기억(owner_model 웹 관습)이 담당한다. 넓은 질의가 최근 관심사로 좁혀지는
            #   필터버블 드리프트 방지. (실행기억[해마]·포식기억·디스크골격은 그대로 유지.)
            related = self._memory_map_scent() if include_related else ""
            result = exec_xml
            if related:
                result = (result + "\n" + related) if result else related

            # 포식 기억 자동 주입 폐지(2026-09-03 사용자 판정): 조사로 기억이 많아지자 "어느 기억이
            #   관련 있나"를 고르는 선택기가 AI 의 판단을 대신하게 됐다. 이제 AI 가 필요할 때
            #   [self:forage]{op:"recall", locus|query} 로 직접 본다(fragments/12_ibl_only 원칙 2,
            #   guides/disk_search §1). 영토·주인 냄새의 상시 노출도 함께 끊는다 — 어휘가 기억의 입구다.

            # 연결된 손발(게스트 PC) 프레즌스 — ★강제주입(질의 무관, 라이브일 때만).
            #   손발 별칭(p0 등)=사용자가 지은 런타임 상태라 어휘·해마가 원리적으로 모른다
            #   (ep840: "p0 시스템 상태"에 회상이 sense:self_check 로 오도 → others:agents/
            #   self:limb 탐색 우회 98초). owner 냄새와 같은 상시-노출 원리, 없으면 0토큰.
            limbs_scent = self._limb_presence_scent()
            if limbs_scent:
                result = (result + "\n" + limbs_scent) if result else limbs_scent

            # 직전 자기수리의 결말 — ★강제주입(질의 무관, 미보고분이 있을 때만).
            #   backend 수리는 자기 턴이 죽은 뒤 워치독이 판정한다 → 그 판정을 말할 입이
            #   없어 성공과 멎음이 구별되지 않았다. 미보고 판정을 주워 다음 턴이 닫는다.
            #   파일 읽기뿐(LLM 0)·없으면 빈 문자열(0토큰)·한 번만 말한다(보고 표식).
            repair = self._pending_repair_scent()
            if repair:
                result = (result + "\n" + repair) if result else repair

            # 결정 원장(사용자 판정) — ★상시 다이제스트 + 질의 일치 상세.
            #   제안·설계는 턴 *중간*에 생기므로(ep 실측: 외부 조사 턴이 노드 스코핑 기각을
            #   모르고 재제안 — 사용자 메시지엔 '스코핑'이 없었다) 키워드 게이트만으로는 못
            #   잡는다 → 활성 판정 한 줄 다이제스트는 owner 냄새처럼 상시 노출(수백 자),
            #   사유·출처 상세만 질의 게이트. 원장이 비면 0토큰.
            decisions = self._decision_scent(user_message)
            if decisions:
                result = (result + "\n" + decisions) if result else decisions

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
                if "memory_map" in result:
                    parts.append("기억지도")
                if "forage_memory" in result:
                    parts.append("포식기억")
                if "connected_limbs" in result:
                    parts.append("손발")
                if "decision_ledger" in result:
                    parts.append("결정원장")
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

    def _limb_presence_scent(self) -> str:
        """연결된 USB 손발(게스트 PC)의 이름+의미 — ★강제주입 냄새.

        별칭은 발급 때 사용자가 짓는 런타임 상태(등기부=limb_keys, 라이브=device_registry)라
        어휘 설명·해마 용례로는 알 길이 없다 → 라이브 손발이 있는 동안만 이름과 뜻을
        연상 블록에 상시 노출해 "p0 상태 알아봐"가 탐색 없이 [limbs:guestpc] 로 한 번에
        라우팅되게 한다. 레지스트리 JSON 읽기뿐(LLM 0)·손발 없으면 빈 문자열(0토큰).
        limbs 노드가 이 에이전트 어휘 밖이면 냄새도 생략(쓸 수 없는 길 안내=오도)."""
        try:
            allowed_nodes = self.config.get("allowed_nodes")
            if allowed_nodes:
                from ibl_access import resolve_allowed_nodes
                allowed = resolve_allowed_nodes(allowed_nodes)
                if allowed is not None and "limbs" not in allowed:
                    return ""
            import device_registry as dr
            import limb_keys
            live = dr.live_with_capability(limb_keys.GUEST_PC_CLASS)
            if not live:
                return ""
            rows = []
            for e in live:
                alias = e.get("alias") or e.get("device_id") or "?"
                rec = limb_keys.get_by_device(e.get("device_id") or "") or {}
                host = rec.get("last_host") or ""
                host_attr = f' host="{host}"' if host else ""
                rows.append(f'  <limb name="{alias}"{host_attr}/>')
            note = ("USB 손발(게스트 PC)이 지금 연결되어 있다. 명령에 아래 이름이 나오면 그 PC를 뜻한다 — "
                    "그 PC의 셸·파일·시스템 상태 조회는 [limbs:guestpc]{limb: \"이름\", op: shell/read/write/list/info}. "
                    "이름 언급 없는 시스템 상태는 본체([sense:host]).")
            return f"<connected_limbs note='{note}'>\n" + "\n".join(rows) + "\n</connected_limbs>"
        except Exception:
            return ""

    def _pending_repair_scent(self) -> str:
        """아직 보고되지 않은 자기수리 판정 — ★강제주입 냄새.

        RED 수리(backend/*.py)는 편집이 부른 리로드가 그 턴을 죽인 **뒤에** 결말이 난다
        (분리 워치독이 헬스체크·롤백 후 result.json 에 판정 기록). 그 판정을 사용자에게
        말할 입이 없어, 성공한 수리와 그냥 멎어버린 수리가 구별되지 않았다 — 자기수리가
        '멈춘 것처럼' 보이던 증상의 나머지 절반. 여기서 미보고 판정을 주워 다음 턴이
        말로 닫는다.

        ★주인 것만 줍는다 (2026-08-25, 사용자 확정: "수리한 에이전트가 말하도록 해야지").
        옛 게이트는 '시스템 AI 만'이었다 — 수리 주체가 시스템 AI 뿐이라는 전제였고, 그 전제는
        같은 날 그랜트 한도가 정본대로 복원되며 깨졌다(프로젝트 에이전트도 수리한다).
        게이트를 '내가 시스템 AI 인가'에서 '이 판정이 내 것인가'로 옮긴다 — 물음이 신원이
        아니라 **소유**여야 판정이 명령한 창으로 돌아간다. 남의 것을 주우면 announced 표식만
        찍고 정작 그 창에서는 영영 안 보인다(회수는 한 번뿐이므로)."""
        try:
            from runtime_utils import get_base_path
            import red_report
            return red_report.pending_scent(str(get_base_path()),
                                            owner=red_report.current_owner())
        except Exception:
            return ""

    def _decision_scent(self, user_message: str) -> str:
        """사용자 판정 원장 회상 — 상시 다이제스트+질의 상세. 실패는 무시(파이프라인 불변)."""
        try:
            import decision_ledger
            return decision_ledger.scent_xml(user_message)
        except Exception as e:
            print(f"[결정원장] 회상 실패 (무시): {e}")
            return ""

    def _memory_map_scent(self) -> str:
        """심층 기억의 **지도(목차)** 를 <memory_map> 으로 돌려준다 — 가지 이름·건수·한 줄 요약만.

        2026-09-03 사용자 판정: 평면 기억을 벡터 Top-3 로 밀어 넣던 자동 주입을 폐지하고, 주제 트리의
        목차만 항상 올린다. 단서는 질문이 아니라 지도에서 오고, 가지의 내용은 AI 가
        [self:memory]{op:"recall", node} 로 연다(포식 기억과 같은 배치 — 어휘가 기억의 입구).
        문서가 사람 손에 고쳐졌으면 먼저 색인에 반영(싼 mtime 대조). 지도가 비면 0토큰.
        """
        try:
            import sys
            import os
            mem_pkg = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..",
                "data", "packages", "installed", "tools", "memory"
            )
            if mem_pkg not in sys.path:
                sys.path.insert(0, mem_pkg)
            import memory_db
            import memory_tree

            from thread_context import get_current_agent_id
            agent_id = get_current_agent_id() or getattr(self, "agent_id", None)
            db_path = memory_db._get_db_path(str(self.project_path), agent_id)
            if not os.path.exists(db_path):
                return ""
            memory_tree.sync_all(db_path)
            text = memory_tree.map_text(db_path)
            if not text:
                return ""
            xml = (
                '<memory_map note="이 자아의 심층 기억 지도(목차) — 가지 (건수) — 요약. 내용은 실리지 않는다. '
                '사용자만 아는 사실(내 ~, 지난번 ~, 선호·결정·사람·물건)이 필요하고 관련 가지가 보이면 '
                '답하기 전에 [self:memory]{op:\"recall\", node:\"<가지>\"} 로 연다. 새로 안 사실은 save 에 node 를 붙인다.">\n'
                + text + "\n</memory_map>"
            )
            print(f"[연상:기억지도] {text.count(chr(10)) + 1}가지")
            return xml
        except Exception as e:
            print(f"[연상:기억지도] 실패 (무시): {e}")
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
        '지원하는 척' 안 한다(폰 게이트).
        """
        # 포식 의도 게이트 — 비포식(아키텍처·대화·버그) 질의엔 골격을 넣지 않는다.
        if not any(cue in (user_message or "").lower() for cue in self._FORAGE_CUES):  # vj-ok: 내부 큐 탐지 — 코드 소유 어휘
            return ""
        try:
            import sys, os
            bk = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if bk not in sys.path:
                sys.path.insert(0, bk)
            try:
                from runtime_utils import detect_body
                profile = detect_body().get("profile") or "pc"
            except Exception:
                profile = "pc"
            if profile == "phone":
                return ""  # 폰 미지원(스코프드 스토리지·실익 작음)
            import focus_map
            return focus_map.build_coarse_map_xml(profile=profile)
        except Exception as e:
            print(f"[디스크골격] 생성 실패 (무시): {e}")
            return ""
