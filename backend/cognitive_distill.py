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
        "인지 아키텍처", "cognitive_pipeline", "_build_execution_memory",
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
        return any(mk.lower() in blob for mk in self._SELF_COGNITION_MARKERS)

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
        'code'(레포명 없음)면 .git 으로 보강, 빈 값이면 'mac'(기본 디스크). 그 외엔 라벨 그대로
        (web/book:<제목>/disk:<라벨>/… 매체가 늘어도 코드 변경 0 — FORAGER_MULTIBODY_DESIGN §9).
        """
        s = (space or "").strip()
        if not s:
            return "mac"
        # bare "code"(레포명 없음)면 .git basename 으로 보강(케이스 보존 — repo/label 은 식별자).
        if s.lower() == "code":
            repo = self._repo_identity(ai_response, user_message)
            return f"code:{repo}" if repo else "code"
        return s  # 라벨 그대로(case-sensitive 식별자: code:<repo>/disk:<label>/book:<title>)

    @staticmethod
    def _is_fs_space(body: str) -> bool:
        """파일시스템 공간인가 — mac(홈디스크)·code:<repo>·disk:<label>. web/book 은 추상."""
        b = body or ""
        return b == "mac" or b.startswith("code") or b.startswith("disk")

    def _resolve_fs_locus(self, loc: str, repo_root: Optional[str], body: str) -> Tuple[str, bool]:
        """파일시스템 공간 locus 를 *실존 검증*해 정규화(Fix 1). 반환 (locus, is_real).

        LLM 이 상대 슬러그·추상 개념명·라인접미사(:288)를 locus 로 줄 수 있다. 이를 무조건
        repo_root 에 join 하면 `/…/code:repo/foo` 같은 *실존하지 않는 /-접두 경로*가 생겨
        영구 "missing" 잡음이 된다(냄새지도 오염). 그래서:
          1) 후보(절대=그대로 / 상대=repo_root 결합, 라인접미사 벗겨 재시도)를 실존 검증.
          2) 실존 → 절대경로 canonical 반환(freshness 추적 정상).
          3) 미해소 → web 처럼 *추상 locus* 로 강등(비-'/' 접두 → _stale_of·mtime 면제).
             locus 는 안정 키일 뿐, 의미는 claim 이 진다. `{body}/{tail}` 형태.
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

        # 미해소 → 추상 locus 강등(freshness 면제). 의미 있는 꼬리만 슬러그로.
        tail = raw
        m = re.search(r":\d+(?:-\d+)?$", tail)
        if m:
            tail = tail[:m.start()]
        # repo_root 하위 절대경로면 조상 경로가 노이즈 → 상대 꼬리만 남긴다(하드코딩 없음).
        if repo_root and tail.startswith(repo_root.rstrip("/") + "/"):
            tail = tail[len(repo_root.rstrip("/")) + 1:]
        # 남은 노이즈: body 의 레포/라벨 중복 세그먼트 제거(code:indiebizOS → indiebizOS)
        repo_part = body.split(":", 1)[-1] if ":" in body else body
        segs = [s for s in tail.strip("/").split("/")
                if s and s != repo_part and s != body]
        slug = "/".join(segs[-2:])[:80] if segs else "unknown"
        return f"{body}/{slug}", False

    def _distill_deep_memory(self, user_message: str, ai_response: str):
        """대화 후 심층 메모리 자동 저장.

        경량 AI로 대화에서 기억할 정보 조각을 추출하고,
        기존 심층 메모리와 비교하여 추가/업데이트한다.
        """
        try:
            if not user_message or not ai_response:
                return

            import sys, os, json
            mem_pkg = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..",
                "data", "packages", "installed", "tools", "memory"
            )
            if mem_pkg not in sys.path:
                sys.path.insert(0, mem_pkg)
            import memory_db

            from thread_context import get_current_agent_id
            from consciousness_agent import lightweight_ai_call

            agent_id = get_current_agent_id()
            project_path = str(self.project_path)

            # 1단계: 대화에서 기억할 정보 조각 추출
            extract_prompt = f"""다음 대화에서 나중에 기억해둘 만한 사실 정보를 추출하라.
(이름, 중요한 날짜, 사용자 선호, 결정사항, 작업 결과 등)
일시적 데이터(주가, 날씨, 환율, 시세 등)와 추론/감상은 제외. JSON 배열로만 응답.
[{{"content": "...", "keywords": "k1,k2", "category": "사용자선호|사용자정보|작업기록|의사결정|중요날짜"}}]
정보가 없으면 빈 배열 [] 반환.

사용자: {user_message[:500]}
AI: {ai_response[:500]}"""

            result = lightweight_ai_call(
                prompt=extract_prompt,
                system_prompt="사실 정보만 추출하라. JSON 배열로만 응답.",
                role="background",
            )
            if not result:
                return

            # JSON 파싱
            cleaned = result.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            facts = json.loads(cleaned)
            if not isinstance(facts, list) or not facts:
                return

            saved_count = 0
            updated_count = 0

            # 2단계: 각 조각의 기존 유사 항목을 기계적으로 탐색(임베딩, 무LLM).
            #   - 유사 항목 없음 → 곧장 NEW (LLM 판정 불필요)
            #   - 유사 항목 있음 → (신규, 기존 후보) 쌍으로 모아 다음 단계에서 '한 번에' 판정
            pending = []   # [(fact, top)] — 배치 dedup 대상
            for fact in facts[:5]:  # 최대 5개 조각
                content = fact.get("content", "").strip()
                if not content:
                    continue
                fact["content"] = content
                fact["keywords"] = fact.get("keywords", "").strip()
                fact["category"] = fact.get("category", "").strip()

                existing = memory_db.search(
                    project_path=project_path, agent_id=agent_id,
                    query=fact["keywords"] or content, limit=3,
                )
                top = (memory_db.read(project_path, agent_id, existing[0]["id"])
                       if existing else None)
                if top:
                    pending.append((fact, top))
                else:
                    memory_db.save(
                        project_path=project_path, agent_id=agent_id,
                        content=content, keywords=fact["keywords"],
                        category=fact["category"],
                    )
                    saved_count += 1
                    print(f"[심층메모리] NEW [{fact['category']}]: \"{content[:50]}\"")

            # 3단계: 유사쌍이 있으면 '단 한 번'의 배치 호출로 전부 판정 (조각마다 호출 X)
            verdicts = []
            if pending:
                pairs_text = "\n".join(
                    f'{i+1}. 기존: {top["content"][:200]}\n   신규: {fact["content"][:200]}'
                    for i, (fact, top) in enumerate(pending)
                )
                batch_prompt = (
                    "각 쌍의 '기존 기억'과 '신규 정보'의 관계를 판정하라.\n"
                    "SAME(완전 동일) / UPDATE(기존도 유효한데 정보 보충) / "
                    "REPLACE(기존이 틀렸거나 옛 정보라 새 정보로 정정·대체) / "
                    "NEW(서로 다른 정보) 중 하나씩.\n\n"
                    f"{pairs_text}\n\n"
                    '쌍 순서대로 JSON으로만 응답: {"verdicts": ["SAME"|"UPDATE"|"REPLACE"|"NEW", ...]}'
                )
                resp = lightweight_ai_call(
                    prompt=batch_prompt,
                    system_prompt="기억 관계 판정기. 쌍 순서대로 verdict 배열만 JSON으로 응답.",
                    role="background",
                )
                if resp:
                    rc = resp.strip()
                    if rc.startswith("```"):
                        rc = rc.split("\n", 1)[-1]
                        if rc.endswith("```"):
                            rc = rc[:-3]
                        rc = rc.strip()
                    try:
                        verdicts = (json.loads(rc) or {}).get("verdicts", [])
                    except json.JSONDecodeError:
                        verdicts = []

            # 4단계: 판정 적용 (verdict 누락/불명은 NEW로 안전 처리)
            for i, (fact, top) in enumerate(pending):
                j = (verdicts[i] if i < len(verdicts) else "NEW")
                j = str(j).strip().upper()
                content = fact["content"]
                keywords = fact["keywords"]
                category = fact["category"]
                if "SAME" in j:
                    memory_db.update(project_path, agent_id, top["id"])
                    print(f"[심층메모리] SAME 스킵: \"{content[:50]}\"")
                elif "REPLACE" in j:
                    # 정정 → 기존을 새 정보로 덮어쓰기 (옛/틀린 정보 폐기)
                    merged_kw = _merge_keywords(top.get("keywords", ""), keywords)
                    memory_db.update(project_path, agent_id, top["id"],
                                     content=content, keywords=merged_kw)
                    updated_count += 1
                    print(f"[심층메모리] REPLACE: \"{content[:50]}\" → 기존 ID {top['id']} 덮어씀")
                elif "UPDATE" in j:
                    # 보충 → 기존 내용에 덧붙임 (둘 다 유효)
                    merged = f"{top['content']}\n[보충] {content}"
                    merged_kw = _merge_keywords(top.get("keywords", ""), keywords)
                    memory_db.update(project_path, agent_id, top["id"],
                                     content=merged, keywords=merged_kw)
                    updated_count += 1
                    print(f"[심층메모리] UPDATE: \"{content[:50]}\" → 기존 ID {top['id']}")
                else:  # NEW (또는 불명)
                    memory_db.save(project_path=project_path, agent_id=agent_id,
                                   content=content, keywords=keywords, category=category)
                    saved_count += 1
                    print(f"[심층메모리] NEW [{category}]: \"{content[:50]}\"")

            if saved_count or updated_count:
                print(f"[심층메모리] 저장 {saved_count}건, 업데이트 {updated_count}건: "
                      f"\"{user_message[:40]}\"")

        except json.JSONDecodeError:
            print(f"[심층메모리] JSON 파싱 실패 (무시)")
        except Exception as e:
            print(f"[심층메모리] 실패 (무시): {e}")

    def _distill_forage_memory(self, user_message: str, ai_response: str,
                               assume_forage: bool = False):
        """포식 후 자동 증류 — 냄새지도(forage_map)+주인모델(owner_model)에 *델타만* 누적.

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
            import sys, os, json
            bk = os.path.dirname(os.path.abspath(__file__))
            if bk not in sys.path:
                sys.path.insert(0, bk)
            # 하드웨어 자아 게이트(누가 포식) — 공간 body 와 분리(§1)
            try:
                from runtime_utils import detect_body
                hw = detect_body().get("profile") or "mac"
            except Exception:
                hw = "mac"
            if hw == "phone":
                return  # 폰 자아는 미디어-한정(A3 후속)
            # 2차 싼 게이트(매체 무관): 응답이 실제 navigable/반구조 공간을 뒤졌나(맛집·영상 검색 등 LLM 낭비 차단).
            #   디스크 경로·URL·코드 구성·확장자를 한 집합으로 — per-medium 분기 없음(§9).
            ar_l = ai_response.lower()
            if not (self._FORAGE_EVIDENCE_RE.search(ai_response)
                    or any(w in ar_l for w in self._FORAGE_EVIDENCE_WORDS)):
                return  # 포식 흔적 없음 — 증류 스킵(LLM 호출 안 함)
            import forage_memory
            from consciousness_agent import lightweight_ai_call

            # 1) 기존 지도(전 공간) 요약 → "이미 아는 것"으로 (델타만 추출하도록). body 표기로 공간 구분.
            known = forage_memory.recall(body=None, query=None, limit=40)
            known_lines = []
            for m in known.get("map", []):
                known_lines.append(f'- [{m.get("body","?")}/{m["kind"]}] {m["locus"]}: {m["claim"]}')
            for o in known.get("owner", []):
                known_lines.append(f'- [owner:{o["facet"]}] {o["value"]}')
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
- owner.{{identity|domain|affiliation|signal|lexicon|habit}}: 주인이 *누구인가* 모델(정체·분야·소속·내용지문·어휘매핑·*개인 정리습관*) — ★몸 독립, 모든 공간 공유. 웹 포식이면 특히 값지다(다음 검색 중의성 해소). ⚠️owner 는 주인이 *누구인가*만 — *어떻게 검색·탐색하나*(방법·기법)는 owner 아니라 map.convention.

규칙:
- **이미 아는 것과 같으면 내지 마라**(새롭거나 교정된 것만).
- **★자기서술 금지(포식≠자기소개)**: 포식 대상이 이 시스템(IndieBiz OS) 자신의 코드라도, *자신의 인지·기억 사고방식*(포식 기억·냄새지도·의식/무의식 에이전트·인지 파이프라인·증류·해마·Reflex·execution_memory·owner_model)을 서술하는 것은 공간 지식이 아니라 자기 자신을 자신에게 다시 적는 순환이다 → 기록 금지. 코드 공간을 포식했다면 *일반화 가능한 코드 관습·구조*(예 "핸들러 op 분기=`_OP_DISPATCHERS`", "IBL 액션=src에 정의→build로 생성", "통화 봉투=message+items 분리")만 기록하라 — 그 코드가 *무엇을 하는 인지 시스템인지*를 논평하지 마라.
- **owner vs convention 경계**: 검색·탐색 *방법/기법*(예 "흔한 이름은 전공·소속 등 비식별 고유값으로 좁혀라", "동명이인 주의", "본명이 남는 공개기록 우선")은 *주인이 누구인가*가 아니다 → 그 공간의 map.convention 으로(owner 금지). owner.habit/lexicon 은 *주인 자신*에 관한 것만(예 "이력서를 docx+pdf 쌍으로 관리"=정리습관 / "Amari=甘利俊一"=어휘매핑).
- prior_class: 동질이라 싸게 재검증되면 "structural", 의미·정체 주장이면 "semantic".
- surface: *이미 아는 라벨을 위반*하는 이질 내용을 봤다면(예 "연구 폴더인 줄 알았는데 개인 투자 메모") 그 locus/owner value 를 surface 에 적고 why.
- 확실치 않으면 비워라. JSON 으로만 응답.

이미 아는 지도(전 공간):
{known_text[:1500]}

사용자: {user_message[:300]}
AI 답변: {ai_response[:1400]}

응답 형식(빈 배열 허용):
{{"space":"mac|code:<repo>|web|book:<title>|disk:<label>",
 "map":[{{"locus":"위치(파일시스템이면 절대경로)","kind":"identity|convention|dead_branch|substrate","claim":"...","prior_class":"structural|semantic","prune_reason":"(dead_branch면)","generalizes":true}}],
 "owner":[{{"facet":"domain|identity|...","value":"...","prior_class":"semantic"}}],
 "surface":[{{"locus":"(있으면)","value":"(owner면)","why":"..."}}]}}"""

            resp = lightweight_ai_call(
                prompt=extract_prompt,
                system_prompt="포식 지도 증류기. 포식한 공간을 명명하고 일반화 가능한 공간 지식 델타만 JSON으로. 특정 항목·날 내용 금지.",
                role="background",
            )
            if not resp:
                return
            rc = resp.strip()
            if rc.startswith("```"):
                rc = rc.split("\n", 1)[-1]
                if rc.endswith("```"):
                    rc = rc[:-3]
                rc = rc.strip()
            data = json.loads(rc)
            if not isinstance(data, dict):
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
            for o in (data.get("owner") or [])[:4]:
                facet, value = o.get("facet"), o.get("value")
                if not facet or not value:
                    continue
                # Fix 2: 주인모델도 인지 기계장치 서술은 드롭(정체성 "인지 외골격 구축자"
                #   같은 값은 마커에 없어 통과 — 기계장치 고유명 서술만 차단).
                if self._is_self_narration(value):
                    print(f"[포식기억] 자기서술 드롭 owner[{facet}]: \"{str(value)[:48]}\"")
                    continue
                r = forage_memory.note_owner(
                    facet=facet, value=value,
                    prior_class=o.get("prior_class") or "semantic",
                    confidence=0.65, provenance=dict(prov))
                if r.get("success"):
                    noted += 1
                    print(f"[포식기억] {r['action']} owner[{facet}]: \"{value[:48]}\"")

            # step 5: surface — 기존 라벨 의심 표식(이질 내용 발견).
            #   위반은 폴더 라벨(map)일 수도, *주인모델*(owner)일 수도 → 둘 다 독립 표식.
            for s in (data.get("surface") or [])[:4]:
                why = s.get("why") or ""
                loc, val = s.get("locus"), s.get("value")
                marked = []
                if loc:  # 위반된 폴더 라벨
                    for x in forage_memory.recall(body=body, query=loc, limit=5).get("map", []):
                        if x["locus"] == loc:
                            forage_memory.mark_surface(entry_id=x["id"], table="forage_map", on=True)
                            marked.append(f"map#{x['id']}")
                if val:  # 위반된 주인모델 라벨 — 가장 관련된 semantic 하나(구조적은 surface 무의미)
                    for o in forage_memory.recall(body=body, query=val, limit=5).get("owner", []):
                        if o.get("prior_class") == "semantic":
                            forage_memory.mark_surface(entry_id=o["id"], table="owner_model", on=True)
                            marked.append(f"owner#{o['id']}")
                            break
                if marked:
                    print(f"[포식기억] surface 표식({','.join(marked)}): \"{why[:48]}\"")

            if noted:
                print(f"[포식기억] 증류 {noted}건: \"{user_message[:40]}\"")
        except json.JSONDecodeError:
            print("[포식기억] JSON 파싱 실패 (무시)")
        except Exception as e:
            print(f"[포식기억] 증류 실패 (무시): {e}")

    def _after_response(self, user_message: str, response: str, *,
                        tool_calls=None, hippo_score: float = None, top_code: str = None,
                        write_experience: bool = True, write_deep: bool = True,
                        write_forage: bool = True, assume_forage: bool = False):
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
        # 1) 경험 증류(해마) — 도구 실행이 있었을 때만. + Reflex top-1 성공률 피드백.
        if write_experience and tool_calls:
            try:
                from ibl_usage_rag import distill_experience, record_recall_outcome
                distill_experience(user_message, tool_calls, hippo_score)
                record_recall_outcome(top_code, hippo_score, tool_calls)
            except Exception as e:
                log(f"[경험증류] 오류 (무시): {e}")
        # 2) 심층/의미 메모리 증류.
        if write_deep:
            try:
                self._distill_deep_memory(user_message, response)
            except Exception as e:
                log(f"[심층메모리] 오류 (무시): {e}")
        # 3) 포식 기억 증류(냄새지도·주인모델).
        if write_forage:
            try:
                self._distill_forage_memory(user_message, response, assume_forage=assume_forage)
            except Exception as e:
                log(f"[포식기억] 오류 (무시): {e}")
