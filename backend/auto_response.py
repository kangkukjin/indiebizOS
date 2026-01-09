"""
auto_response.py - 자동응답 서비스 V2
kvisual-mcp의 자동응답 기능을 indiebizOS에 통합

시스템 AI 설정을 사용하여 수신된 메시지에 자동으로 응답합니다.
AI 판단 → 비즈니스 검색 → 응답 생성 순서로 처리합니다.
"""

import json
import re
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"


class AutoResponseService:
    """자동응답 서비스 V2 - AI 판단 + 비즈니스 검색 통합"""

    def __init__(self, log_callback: Callable[[str], None] = None):
        self._log_callback = log_callback or print
        self._processed_messages: Dict[str, float] = {}  # message_key -> timestamp
        self._running = False
        self._check_interval = 10  # 초
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _log(self, message: str):
        """로그 출력"""
        self._log_callback(f"[AutoResponse] {message}")

    def _get_business_manager(self):
        """BusinessManager 인스턴스 반환"""
        from business_manager import BusinessManager
        return BusinessManager()

    def _get_ai_judgment_service(self):
        """AI 판단 서비스 인스턴스 반환"""
        from ai_judgment import get_ai_judgment_service
        return get_ai_judgment_service()

    def _load_system_ai_config(self) -> dict:
        """시스템 AI 설정 로드"""
        if SYSTEM_AI_CONFIG_PATH.exists():
            try:
                with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "enabled": True,
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "apiKey": ""
        }

    def start(self):
        """자동응답 서비스 시작"""
        if self._running:
            return

        config = self._load_system_ai_config()
        if not config.get("enabled") or not config.get("apiKey"):
            self._log("시스템 AI가 비활성화되어 있거나 API 키가 없습니다")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log("자동응답 서비스 시작 (AI 판단 + 비즈니스 검색 활성화)")

    def stop(self):
        """자동응답 서비스 중지"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._log("자동응답 서비스 중지")

    def _run_loop(self):
        """메인 루프 - 미응답 메시지 확인 및 처리"""
        while self._running and not self._stop_event.is_set():
            try:
                self._check_unreplied_messages()
            except Exception as e:
                self._log(f"처리 오류: {e}")

            # 대기
            self._stop_event.wait(timeout=self._check_interval)

    def _check_unreplied_messages(self):
        """미응답 메시지 확인 및 처리"""
        try:
            bm = self._get_business_manager()

            # 미응답 메시지 조회 (받은 메시지 중 replied=0인 것)
            messages = bm.get_messages(unreplied_only=True, limit=10)

            for msg in messages:
                # 중복 처리 방지
                msg_key = f"{msg['id']}-{msg['message_time']}"
                if msg_key in self._processed_messages:
                    continue

                # 내가 보낸 메시지는 스킵
                if msg.get('is_from_user') == 1:
                    continue

                # 메시지 처리
                self._process_message(msg)
                self._processed_messages[msg_key] = time.time()

            # 오래된 처리 기록 정리 (1시간 이상)
            self._cleanup_processed_cache()

        except Exception as e:
            self._log(f"미응답 메시지 확인 오류: {e}")

    def _process_message(self, message: dict):
        """메시지 처리 - AI 판단 → 비즈니스 검색 → 응답 생성"""
        try:
            self._log(f"새 메시지 처리: {message.get('subject', '제목없음')[:30]}")

            bm = self._get_business_manager()

            # 1. 이웃 정보 조회
            neighbor = None
            if message.get('neighbor_id'):
                neighbor = bm.get_neighbor(message['neighbor_id'])
            if not neighbor:
                neighbor = {
                    'id': message.get('neighbor_id'),
                    'name': '알 수 없음',
                    'info_level': 0,
                    'rating': 0
                }

            # 2. 무한 루프 방지 체크
            if self._should_skip_response(message, neighbor):
                self._log("무한 루프 방지로 응답 스킵")
                bm.mark_message_replied(message['id'])
                return

            # 3. 컨텍스트 수집
            context = self._collect_context(message, neighbor)

            # 4. AI 판단
            judgment_service = self._get_ai_judgment_service()
            judgment = judgment_service.judge_message(context)
            self._log(f"AI 판단 결과: {judgment.get('action')} (confidence: {judgment.get('confidence', 0):.2f})")

            # 5. 판단에 따른 처리
            if judgment.get('action') == 'NO_RESPONSE':
                self._log(f"응답 불필요로 판단: {judgment.get('reasoning', '')}")
                bm.mark_message_replied(message['id'])
                return

            # 6. 비즈니스 검색 수행
            search_results = self._perform_business_searches(judgment.get('searches', []))

            # 7. 응답 생성
            response = self._generate_response(context, search_results)

            if response:
                # 8. 응답 저장 (pending 상태로, channel_poller가 발송)
                bm.create_message(
                    content=response['body'],
                    contact_type=message.get('contact_type', 'email'),
                    contact_value=message.get('contact_value', ''),
                    subject=response['subject'],
                    neighbor_id=message.get('neighbor_id'),
                    is_from_user=1,  # 내가 보내는 메시지
                    status='pending'
                )
                self._log(f"응답 생성 완료: {response['subject'][:30]}")

            # 9. 원본 메시지 응답 완료 표시
            bm.mark_message_replied(message['id'])

        except Exception as e:
            self._log(f"메시지 처리 오류: {e}")
            # 오류 발생해도 replied 표시하여 무한 재시도 방지
            try:
                bm.mark_message_replied(message['id'])
            except:
                pass

    def _should_skip_response(self, message: dict, neighbor: dict) -> bool:
        """무한 루프 방지 체크"""
        # 내가 보낸 메시지
        if message.get('is_from_user') == 1:
            return True

        # 자동응답 메시지에 대한 응답
        subject = message.get('subject', '') or ''
        if 'agent:' in subject.lower() or '자동응답' in subject:
            return True

        # 연속 자동응답 체크 (최근 10개 중 자동응답이 5개 이상이면 스킵)
        try:
            bm = self._get_business_manager()
            recent = bm.get_messages(neighbor_id=neighbor.get('id'), limit=10)
            auto_count = sum(1 for m in recent
                           if m.get('is_from_user') == 1 and
                           ('agent:' in (m.get('subject') or '').lower() or '자동응답' in (m.get('subject') or '')))
            if auto_count >= 5:
                return True
        except:
            pass

        return False

    def _collect_context(self, message: dict, neighbor: dict) -> dict:
        """응답 생성에 필요한 컨텍스트 수집"""
        bm = self._get_business_manager()
        info_level = neighbor.get('info_level', 0)

        # 대화 기록 (최근 4개, 2주 이내)
        conversation_history = []
        if neighbor.get('id'):
            try:
                messages = bm.get_messages(neighbor_id=neighbor['id'], limit=10)
                two_weeks_ago = (datetime.now() - timedelta(days=14)).isoformat()
                conversation_history = [m for m in messages
                                        if m.get('message_time', '') > two_weeks_ago][:4]
                # 시간순 정렬
                conversation_history = sorted(conversation_history,
                                             key=lambda x: x.get('message_time', ''))
            except:
                pass

        # 근무지침
        work_guideline = None
        try:
            guideline = bm.get_work_guideline(info_level)
            if guideline:
                work_guideline = guideline.get('content', '')
        except:
            pass

        # 비즈니스 문서
        business_doc = None
        try:
            doc = bm.get_business_document(info_level)
            if doc:
                business_doc = doc.get('content', '')
        except:
            pass

        return {
            'message': message,
            'neighbor': neighbor,
            'conversation_history': conversation_history,
            'work_guideline': work_guideline,
            'business_doc': business_doc
        }

    def _perform_business_searches(self, searches: List[dict]) -> List[dict]:
        """비즈니스 검색 수행"""
        if not searches:
            return []

        results = []
        bm = self._get_business_manager()

        for search in searches:
            category = search.get('category', '')
            keywords = search.get('keywords', [])

            items = self._search_business_items(bm, category, keywords)

            results.append({
                'category': category,
                'keywords': keywords,
                'items': items,
                'hasResults': len(items) > 0
            })

        return results

    def _search_business_items(self, bm, category: str, keywords: List[str]) -> List[dict]:
        """비즈니스 아이템 검색"""
        try:
            # 카테고리로 비즈니스 검색
            businesses = bm.get_businesses(search=category)

            items = []
            for business in businesses[:3]:  # 최대 3개 비즈니스
                business_items = bm.get_business_items(business['id'])

                # 키워드 매칭
                for item in business_items:
                    title = (item.get('title') or '').lower()
                    details = (item.get('details') or '').lower()

                    # 키워드가 없으면 모든 아이템 포함
                    if not keywords:
                        items.append({
                            'title': item.get('title'),
                            'details': item.get('details'),
                            'business_name': business.get('name')
                        })
                    else:
                        # 키워드 중 하나라도 매칭되면 포함
                        for kw in keywords:
                            if kw.lower() in title or kw.lower() in details:
                                items.append({
                                    'title': item.get('title'),
                                    'details': item.get('details'),
                                    'business_name': business.get('name')
                                })
                                break

            return items[:5]  # 최대 5개 결과

        except Exception as e:
            self._log(f"비즈니스 검색 오류: {e}")
            return []

    def _generate_response(self, context: dict, search_results: List[dict]) -> Optional[dict]:
        """AI를 사용하여 응답 생성"""
        config = self._load_system_ai_config()

        if not config.get("enabled") or not config.get("apiKey"):
            self._log("시스템 AI가 비활성화되어 있습니다")
            return None

        provider = config.get("provider", "anthropic")
        model = config.get("model", "claude-sonnet-4-20250514")
        api_key = config.get("apiKey", "")

        # 프롬프트 구성
        prompt = self._build_response_prompt(context, search_results)

        try:
            if provider == "anthropic":
                response_text = self._call_anthropic(prompt, api_key, model)
            elif provider == "openai":
                response_text = self._call_openai(prompt, api_key, model)
            elif provider == "google":
                response_text = self._call_google(prompt, api_key, model)
            else:
                self._log(f"지원하지 않는 프로바이더: {provider}")
                return None

            return self._parse_response(response_text)

        except Exception as e:
            self._log(f"AI 응답 생성 오류: {e}")
            return None

    def _build_response_prompt(self, context: dict, search_results: List[dict]) -> str:
        """응답 생성 프롬프트 구성"""
        message = context['message']
        neighbor = context['neighbor']
        work_guideline = context.get('work_guideline') or '근무지침이 설정되지 않았습니다.'
        business_doc = context.get('business_doc') or '비즈니스 문서가 없습니다.'
        conversation_history = context.get('conversation_history', [])

        # 대화 기록 포맷
        history_text = '이전 대화 없음'
        if conversation_history:
            history_lines = []
            for msg in conversation_history:
                direction = '받은 메시지' if msg.get('is_from_user') == 0 else '보낸 메시지'
                sender = msg.get('contact_value', '알 수 없음') if msg.get('is_from_user') == 0 else '나'
                history_lines.append(
                    f"[{msg.get('message_time', '')}] {direction} - {sender}:\n"
                    f"제목: {msg.get('subject', '제목 없음')}\n"
                    f"내용: {msg.get('content', '내용 없음')[:200]}"
                )
            history_text = '\n---\n'.join(history_lines)

        # 검색 결과 포맷
        search_text = self._format_search_results(search_results)

        prompt = f"""당신은 비즈니스 매칭 에이전트입니다. 다음 정보를 바탕으로 적절한 응답을 작성해주세요.

## 근무지침
{work_guideline}

## 나의 비즈니스 문서
{business_doc}

## 검색 결과
{search_text}

## 지난 대화
{history_text}

## 들어온 메시지
발신자: {neighbor.get('name', '알 수 없음')}
제목: {message.get('subject', '제목 없음')}
내용: {message.get('content', '내용 없음')}

## 응답 작성 가이드라인
1. 친근하고 전문적인 어조로 작성
2. 상대방의 요청에 직접적으로 답변
3. 검색 결과에 관련 정보가 있으면 활용
4. 검색 결과가 없어도 도움이 되는 응답 작성
5. 단순 인사나 감사에도 적절히 응답

## 응답 형식 (반드시 이 형식을 따라주세요)
제목: [응답 제목]
본문: [응답 내용]

가독성을 위해:
- 단락 사이에는 빈 줄 추가
- 리스트는 글머리 기호 사용
- 긴 문장은 적절히 나누어 작성"""

        return prompt

    def _format_search_results(self, results: List[dict]) -> str:
        """검색 결과 포맷팅"""
        if not results:
            return '검색 결과: 없음\n\n검색을 수행하지 않았거나 검색 조건이 없습니다.'

        formatted = []
        for result in results:
            header = f"[{result.get('category', '카테고리')}] - 키워드: {', '.join(result.get('keywords', []))}"

            if not result.get('items'):
                formatted.append(f"{header}\n  - 검색 결과: 해당 카테고리에 매칭되는 아이템이 없습니다.")
            else:
                items_text = '\n'.join([
                    f"  - {item.get('title', '제목없음')}: {(item.get('details') or '상세정보 없음')[:100]}"
                    for item in result['items']
                ])
                formatted.append(f"{header}\n{items_text}")

        # 전체 검색 결과 요약
        total_results = sum(len(r.get('items', [])) for r in results)
        summary = f"\n\n전체 검색 결과: {total_results}개의 아이템을 찾았습니다." if total_results > 0 else "\n\n전체 검색 결과: 모든 카테고리에서 매칭되는 아이템을 찾지 못했습니다."

        return f"검색 결과:\n\n{chr(10).join(formatted)}{summary}"

    def _call_anthropic(self, prompt: str, api_key: str, model: str) -> str:
        """Anthropic API 호출"""
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text

    def _call_openai(self, prompt: str, api_key: str, model: str) -> str:
        """OpenAI API 호출"""
        import openai

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.choices[0].message.content

    def _call_google(self, prompt: str, api_key: str, model: str) -> str:
        """Google API 호출"""
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt
        )

        return response.text

    def _parse_response(self, ai_response: str) -> dict:
        """AI 응답 파싱"""
        # 제목 추출
        subject_match = None
        subject_pattern = re.search(r'제목[:：]\s*(.+)', ai_response)
        if subject_pattern:
            subject_match = subject_pattern.group(1).strip()

        # 본문 추출
        body_pattern = re.search(r'본문[:：]\s*([\s\S]+)', ai_response)
        if body_pattern:
            body = body_pattern.group(1).strip()
        else:
            body = ai_response

        # 줄바꿈 정리
        body = re.sub(r'\n{3,}', '\n\n', body)
        body = body.strip()

        return {
            'subject': f"(IN)agent: {subject_match}" if subject_match else "(IN)agent: 자동응답",
            'body': body
        }

    def _cleanup_processed_cache(self):
        """오래된 처리 기록 정리"""
        one_hour_ago = time.time() - 3600
        self._processed_messages = {
            k: v for k, v in self._processed_messages.items()
            if v > one_hour_ago
        }


# 싱글톤 인스턴스
_auto_response_instance: Optional[AutoResponseService] = None


def get_auto_response_service(log_callback: Callable[[str], None] = None) -> AutoResponseService:
    """자동응답 서비스 인스턴스 반환"""
    global _auto_response_instance
    if _auto_response_instance is None:
        _auto_response_instance = AutoResponseService(log_callback)
    return _auto_response_instance
