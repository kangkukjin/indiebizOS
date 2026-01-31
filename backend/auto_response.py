"""
auto_response.py - 자동응답 서비스 V3 (Tool Use 통합)

메시지 수신 → AI(도구 포함) → [필요시 검색] → 응답
판단과 응답을 한 번의 AI 호출로 처리합니다.
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
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"
AUTORESPONSE_PROMPT_PATH = DATA_PATH / "common_prompts" / "base_prompt_autoresponse.md"


# =============================================================================
# 도구 정의
# =============================================================================

BUSINESS_TOOLS = [
    {
        "name": "search_business_items",
        "description": "비즈니스 데이터베이스에서 상품/서비스 검색. 상대방 요청과 관련된 아이템을 찾을 때 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "검색할 비즈니스 카테고리명 (예: 팔아요, 할수있습니다, 구합니다, 나눕니다, 빌려줍니다)"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "검색 키워드 목록 (예: ['세탁기', '수리'])"
                }
            },
            "required": ["category"]
        }
    },
    {
        "name": "no_response_needed",
        "description": "응답이 필요하지 않을 때 호출. 스팸, 광고, 개인적 대화 등 자동응답이 부적절한 경우 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "응답하지 않는 이유 (예: 스팸 메시지, 개인적 대화)"
                }
            },
            "required": ["reason"]
        }
    },
    {
        "name": "send_response",
        "description": "응답 메시지를 발신자에게 즉시 전송합니다. 검색 후 응답을 작성했으면 반드시 이 도구로 발송하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "응답 메시지 제목"
                },
                "body": {
                    "type": "string",
                    "description": "응답 메시지 본문"
                }
            },
            "required": ["subject", "body"]
        }
    }
]

# OpenAI 형식 도구 정의
BUSINESS_TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "search_business_items",
            "description": "비즈니스 데이터베이스에서 상품/서비스 검색. 상대방 요청과 관련된 아이템을 찾을 때 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "검색할 비즈니스 카테고리명 (예: 팔아요, 할수있습니다, 구합니다, 나눕니다, 빌려줍니다)"
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "검색 키워드 목록 (예: ['세탁기', '수리'])"
                    }
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "no_response_needed",
            "description": "응답이 필요하지 않을 때 호출. 스팸, 광고, 개인적 대화 등 자동응답이 부적절한 경우 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "응답하지 않는 이유 (예: 스팸 메시지, 개인적 대화)"
                    }
                },
                "required": ["reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_response",
            "description": "응답 메시지를 발신자에게 즉시 전송합니다. 검색 후 응답을 작성했으면 반드시 이 도구로 발송하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "응답 메시지 제목"
                    },
                    "body": {
                        "type": "string",
                        "description": "응답 메시지 본문"
                    }
                },
                "required": ["subject", "body"]
            }
        }
    }
]

# Google 형식 도구 정의
BUSINESS_TOOLS_GOOGLE = [
    {
        "name": "search_business_items",
        "description": "비즈니스 데이터베이스에서 상품/서비스 검색. 상대방 요청과 관련된 아이템을 찾을 때 사용합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "검색할 비즈니스 카테고리명 (예: 팔아요, 할수있습니다, 구합니다, 나눕니다, 빌려줍니다)"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "검색 키워드 목록 (예: ['세탁기', '수리'])"
                }
            },
            "required": ["category"]
        }
    },
    {
        "name": "no_response_needed",
        "description": "응답이 필요하지 않을 때 호출. 스팸, 광고, 개인적 대화 등 자동응답이 부적절한 경우 사용합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "응답하지 않는 이유 (예: 스팸 메시지, 개인적 대화)"
                }
            },
            "required": ["reason"]
        }
    },
    {
        "name": "send_response",
        "description": "응답 메시지를 발신자에게 즉시 전송합니다. 검색 후 응답을 작성했으면 반드시 이 도구로 발송하세요.",
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "응답 메시지 제목"
                },
                "body": {
                    "type": "string",
                    "description": "응답 메시지 본문"
                }
            },
            "required": ["subject", "body"]
        }
    }
]


class AutoResponseService:
    """자동응답 서비스 V3 - Tool Use 통합"""

    def __init__(self, log_callback: Callable[[str], None] = None):
        self._log_callback = log_callback or print
        self._processed_messages: Dict[str, float] = {}
        self._running = False
        self._check_interval = 10
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # 현재 처리 중인 메시지 컨텍스트 (send_response 도구에서 사용)
        self._current_message_context: Optional[Dict] = None
        self._response_sent: bool = False

    def _log(self, message: str):
        self._log_callback(f"[AutoResponse] {message}")

    def _get_business_manager(self):
        from business_manager import BusinessManager
        return BusinessManager()

    def _load_system_ai_config(self) -> dict:
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

    def _load_system_prompt(self) -> str:
        if AUTORESPONSE_PROMPT_PATH.exists():
            try:
                return AUTORESPONSE_PROMPT_PATH.read_text(encoding='utf-8')
            except:
                pass
        return """당신은 IndieBizOS의 비즈니스 매칭 에이전트입니다.
외부에서 들어온 메시지에 친근하고 전문적으로 응답합니다.
검색 결과에 없는 정보를 지어내지 마세요."""

    def start(self):
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
        self._log("자동응답 서비스 V3 시작 (Tool Use 통합)")

    def stop(self):
        if not self._running:
            return

        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._log("자동응답 서비스 중지")

    def _run_loop(self):
        while self._running and not self._stop_event.is_set():
            try:
                self._check_unreplied_messages()
            except Exception as e:
                self._log(f"처리 오류: {e}")
            self._stop_event.wait(timeout=self._check_interval)

    def _check_unreplied_messages(self):
        try:
            bm = self._get_business_manager()
            messages = bm.get_messages(unreplied_only=True, limit=10)

            for msg in messages:
                msg_key = f"{msg['id']}-{msg['message_time']}"
                if msg_key in self._processed_messages:
                    continue
                if msg.get('is_from_user') == 1:
                    continue

                self._process_message(msg)
                self._processed_messages[msg_key] = time.time()

            self._cleanup_processed_cache()

        except Exception as e:
            self._log(f"미응답 메시지 확인 오류: {e}")

    def _process_message(self, message: dict):
        """메시지 처리 - Tool Use로 판단, 검색, 발송을 한번에"""
        try:
            self._log(f"새 메시지 처리: {message.get('subject', '제목없음')[:30]}")

            bm = self._get_business_manager()

            # 이웃 정보 조회
            neighbor = None
            if message.get('neighbor_id'):
                neighbor = bm.get_neighbor(message['neighbor_id'])
            if not neighbor:
                neighbor = {'id': message.get('neighbor_id'), 'name': '알 수 없음', 'info_level': 0}

            # 무한 루프 방지
            if self._should_skip_response(message, neighbor):
                self._log("무한 루프 방지로 응답 스킵")
                bm.mark_message_replied(message['id'])
                return

            # 현재 메시지 컨텍스트 설정 (send_response 도구에서 사용)
            self._current_message_context = {
                'message': message,
                'neighbor': neighbor
            }
            self._response_sent = False

            # 컨텍스트 수집
            context = self._collect_context(message, neighbor)

            # AI 호출 (Tool Use 포함) - AI가 send_response 도구로 직접 발송
            result = self._call_ai_with_tools(context)

            if result.get('no_response'):
                self._log(f"응답 불필요: {result.get('reason', '')}")

            # send_response 도구가 호출되었으면 이미 발송됨
            if self._response_sent:
                self._log("응답 발송 완료 (send_response 도구)")

            bm.mark_message_replied(message['id'])

            # 컨텍스트 정리
            self._current_message_context = None

        except Exception as e:
            self._log(f"메시지 처리 오류: {e}")
            self._current_message_context = None
            try:
                bm = self._get_business_manager()
                bm.mark_message_replied(message['id'])
            except:
                pass

    def _should_skip_response(self, message: dict, neighbor: dict) -> bool:
        if message.get('is_from_user') == 1:
            return True

        subject = message.get('subject', '') or ''
        if 'agent:' in subject.lower() or '자동응답' in subject:
            return True

        try:
            bm = self._get_business_manager()
            recent = bm.get_messages(neighbor_id=neighbor.get('id'), limit=10)
            auto_count = sum(1 for m in recent
                           if m.get('is_from_user') == 1 and
                           ('agent:' in (m.get('subject') or '').lower()))
            if auto_count >= 5:
                return True
        except:
            pass

        return False

    def _collect_context(self, message: dict, neighbor: dict) -> dict:
        bm = self._get_business_manager()
        info_level = neighbor.get('info_level', 0)

        # 대화 기록
        conversation_history = []
        if neighbor.get('id'):
            try:
                messages = bm.get_messages(neighbor_id=neighbor['id'], limit=10)
                two_weeks_ago = (datetime.now() - timedelta(days=14)).isoformat()
                conversation_history = [m for m in messages if m.get('message_time', '') > two_weeks_ago][:4]
                conversation_history = sorted(conversation_history, key=lambda x: x.get('message_time', ''))
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

        # 비즈니스 목록 (카테고리 목록으로 제공)
        business_list = []
        try:
            businesses = bm.get_businesses()
            business_list = [{'id': b['id'], 'name': b['name'], 'description': b.get('description', '')} for b in businesses]
        except:
            pass

        return {
            'message': message,
            'neighbor': neighbor,
            'conversation_history': conversation_history,
            'work_guideline': work_guideline,
            'business_doc': business_doc,
            'business_list': business_list
        }

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """도구 실행"""
        bm = self._get_business_manager()

        if tool_name == "search_business_items":
            category = tool_input.get('category', '')
            keywords = tool_input.get('keywords', [])
            items = self._search_business_items(bm, category, keywords)

            if not items:
                return f"[{category}] 검색 결과: 해당 카테고리에 매칭되는 아이템이 없습니다."

            result_lines = [f"[{category}] 검색 결과 ({len(items)}개):"]
            for item in items:
                result_lines.append(f"- {item.get('title', '제목없음')}: {(item.get('details') or '상세정보 없음')[:100]}")
            return '\n'.join(result_lines)

        elif tool_name == "no_response_needed":
            return "__NO_RESPONSE__:" + tool_input.get('reason', '응답 불필요')

        elif tool_name == "send_response":
            return self._execute_send_response(tool_input)

        return "알 수 없는 도구"

    def _execute_send_response(self, tool_input: dict) -> str:
        """send_response 도구 실행 - 즉시 발송"""
        if not self._current_message_context:
            return "오류: 메시지 컨텍스트가 없습니다."

        message = self._current_message_context['message']
        neighbor = self._current_message_context['neighbor']

        subject = tool_input.get('subject', '자동응답')
        body = tool_input.get('body', '')

        if not body:
            return "오류: 본문이 비어있습니다."

        contact_type = message.get('contact_type', '')
        contact_value = message.get('contact_value', '')
        original_subject = message.get('subject', '')

        # 제목 포맷
        formatted_subject = f"(IN)agent: {subject}"

        try:
            # channel_poller를 통해 발송
            from channel_poller import get_channel_poller
            poller = get_channel_poller()

            # 응답 제목에 Re: 추가
            reply_subject = f"Re: {original_subject}" if original_subject else formatted_subject

            poller._send_response(contact_type, contact_value, reply_subject, body)

            # DB에 발송 기록 저장 (sent 상태로)
            bm = self._get_business_manager()
            bm.create_message(
                content=body,
                contact_type=contact_type,
                contact_value=contact_value,
                subject=formatted_subject,
                neighbor_id=message.get('neighbor_id'),
                is_from_user=1,
                status='sent'
            )

            self._response_sent = True
            self._log(f"응답 즉시 발송: {contact_type} → {contact_value[:30]}...")

            return "__RESPONSE_SENT__"

        except Exception as e:
            self._log(f"응답 발송 실패: {e}")
            return f"발송 실패: {e}"

    def _search_business_items(self, bm, category: str, keywords: List[str]) -> List[dict]:
        """비즈니스 아이템 검색"""
        try:
            businesses = bm.get_businesses(search=category)
            items = []

            for business in businesses[:3]:
                business_items = bm.get_business_items(business['id'])

                for item in business_items:
                    title = (item.get('title') or '').lower()
                    details = (item.get('details') or '').lower()

                    if not keywords:
                        items.append({
                            'title': item.get('title'),
                            'details': item.get('details'),
                            'business_name': business.get('name')
                        })
                    else:
                        for kw in keywords:
                            if kw.lower() in title or kw.lower() in details:
                                items.append({
                                    'title': item.get('title'),
                                    'details': item.get('details'),
                                    'business_name': business.get('name')
                                })
                                break

            return items[:5]

        except Exception as e:
            self._log(f"비즈니스 검색 오류: {e}")
            return []

    def _build_user_prompt(self, context: dict) -> str:
        """사용자 프롬프트 생성"""
        message = context['message']
        neighbor = context['neighbor']
        work_guideline = context.get('work_guideline') or '근무지침이 설정되지 않았습니다.'
        business_doc = context.get('business_doc') or '비즈니스 문서가 없습니다.'
        conversation_history = context.get('conversation_history', [])
        business_list = context.get('business_list', [])

        # 대화 기록 포맷
        history_text = '이전 대화 없음'
        if conversation_history:
            history_lines = []
            for msg in conversation_history:
                direction = '받은 메시지' if msg.get('is_from_user') == 0 else '보낸 메시지'
                history_lines.append(f"[{msg.get('message_time', '')}] {direction}: {msg.get('subject', '제목 없음')}")
            history_text = '\n'.join(history_lines)

        # 비즈니스 목록 포맷
        business_list_text = '등록된 비즈니스 없음'
        if business_list:
            business_lines = [f"- {b['name']}: {b.get('description', '')}" for b in business_list]
            business_list_text = '\n'.join(business_lines)

        return f"""<context>
<work_guideline>
{work_guideline}
</work_guideline>

<business_document>
{business_doc}
</business_document>

<available_categories>
{business_list_text}
</available_categories>

<conversation_history>
{history_text}
</conversation_history>
</context>

<incoming_message>
발신자: {neighbor.get('name', '알 수 없음')}
제목: {message.get('subject', '제목 없음')}
내용: {message.get('content', '내용 없음')}
</incoming_message>

<instructions>
위 메시지를 분석하고 적절히 처리하세요.

1. 스팸, 광고, 개인적 대화 등 자동응답이 부적절하면 → no_response_needed 도구 호출
2. 비즈니스 문의라면 → search_business_items로 검색 → send_response로 발송
3. 단순 인사/감사면 → 검색 없이 send_response로 발송

중요: 응답을 작성했으면 반드시 send_response 도구로 발송하세요.

응답 원칙:
- 친근하지만 전문적인 어조
- 검색 결과에 없는 정보 지어내지 않기
- 핵심부터 답변하고 다음 단계 제안으로 마무리
</instructions>"""

    def _call_ai_with_tools(self, context: dict) -> dict:
        """AI 호출 (Tool Use 포함)"""
        config = self._load_system_ai_config()

        if not config.get("enabled") or not config.get("apiKey"):
            return {'no_response': True, 'reason': 'AI 비활성화'}

        provider = config.get("provider", "anthropic")
        model = config.get("model", "claude-sonnet-4-20250514")
        api_key = config.get("apiKey", "")

        system_prompt = self._load_system_prompt()
        user_prompt = self._build_user_prompt(context)

        try:
            if provider == "anthropic":
                return self._call_anthropic_with_tools(user_prompt, api_key, model, system_prompt)
            elif provider == "openai":
                return self._call_openai_with_tools(user_prompt, api_key, model, system_prompt)
            elif provider == "google":
                return self._call_google_with_tools(user_prompt, api_key, model, system_prompt)
            else:
                self._log(f"지원하지 않는 프로바이더: {provider}")
                return {'no_response': True, 'reason': f'미지원 프로바이더: {provider}'}

        except Exception as e:
            self._log(f"AI 호출 오류: {e}")
            return {'no_response': True, 'reason': str(e)}

    def _call_anthropic_with_tools(self, prompt: str, api_key: str, model: str, system_prompt: str) -> dict:
        """Anthropic API 호출 (Tool Use)"""
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        messages = [{"role": "user", "content": prompt}]

        # 첫 번째 호출
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=system_prompt,
            tools=BUSINESS_TOOLS,
            messages=messages
        )

        # Tool Use 루프
        while response.stop_reason == "tool_use":
            # 도구 호출 처리
            tool_results = []
            assistant_content = response.content

            for block in assistant_content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    self._log(f"도구 호출: {tool_name}")
                    result = self._execute_tool(tool_name, tool_input)

                    # no_response 체크
                    if result.startswith("__NO_RESPONSE__:"):
                        reason = result.replace("__NO_RESPONSE__:", "")
                        return {'no_response': True, 'reason': reason}

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result
                    })

            # 메시지 히스토리 업데이트
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

            # 다음 호출
            response = client.messages.create(
                model=model,
                max_tokens=1500,
                system=system_prompt,
                tools=BUSINESS_TOOLS,
                messages=messages
            )

        # 최종 텍스트 응답 추출
        final_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                final_text += block.text

        return {'response': self._parse_response(final_text)}

    def _call_openai_with_tools(self, prompt: str, api_key: str, model: str, system_prompt: str) -> dict:
        """OpenAI API 호출 (Tool Use)"""
        import openai

        client = openai.OpenAI(api_key=api_key)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        # 첫 번째 호출
        response = client.chat.completions.create(
            model=model,
            max_tokens=1500,
            messages=messages,
            tools=BUSINESS_TOOLS_OPENAI
        )

        # Tool Use 루프
        while response.choices[0].finish_reason == "tool_calls":
            assistant_message = response.choices[0].message
            messages.append(assistant_message)

            tool_calls = assistant_message.tool_calls
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                tool_input = json.loads(tool_call.function.arguments)

                self._log(f"도구 호출: {tool_name}")
                result = self._execute_tool(tool_name, tool_input)

                # no_response 체크
                if result.startswith("__NO_RESPONSE__:"):
                    reason = result.replace("__NO_RESPONSE__:", "")
                    return {'no_response': True, 'reason': reason}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            # 다음 호출
            response = client.chat.completions.create(
                model=model,
                max_tokens=1500,
                messages=messages,
                tools=BUSINESS_TOOLS_OPENAI
            )

        final_text = response.choices[0].message.content or ""
        return {'response': self._parse_response(final_text)}

    def _call_google_with_tools(self, prompt: str, api_key: str, model: str, system_prompt: str) -> dict:
        """Google API 호출 (Tool Use)"""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Google 도구 형식으로 변환
        tools = [types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=tool['name'],
                description=tool['description'],
                parameters=tool['parameters']
            ) for tool in BUSINESS_TOOLS_GOOGLE
        ])]

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=tools
        )

        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]

        # 첫 번째 호출
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )

        # Tool Use 루프
        while response.candidates[0].content.parts:
            has_function_call = False
            function_responses = []

            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    has_function_call = True
                    fc = part.function_call
                    tool_name = fc.name
                    tool_input = dict(fc.args) if fc.args else {}

                    self._log(f"도구 호출: {tool_name}")
                    result = self._execute_tool(tool_name, tool_input)

                    # no_response 체크
                    if result.startswith("__NO_RESPONSE__:"):
                        reason = result.replace("__NO_RESPONSE__:", "")
                        return {'no_response': True, 'reason': reason}

                    function_responses.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_name,
                            response={"result": result}
                        )
                    ))

            if not has_function_call:
                break

            # 대화 히스토리 업데이트
            contents.append(response.candidates[0].content)
            contents.append(types.Content(role="user", parts=function_responses))

            # 다음 호출
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )

        # 최종 텍스트 추출
        final_text = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
                final_text += part.text

        return {'response': self._parse_response(final_text)}

    def _parse_response(self, ai_response: str) -> dict:
        """AI 응답 파싱"""
        subject_match = re.search(r'제목[:：]\s*(.+)', ai_response)
        subject = subject_match.group(1).strip() if subject_match else None

        body_match = re.search(r'본문[:：]\s*([\s\S]+)', ai_response)
        body = body_match.group(1).strip() if body_match else ai_response

        body = re.sub(r'\n{3,}', '\n\n', body).strip()

        return {
            'subject': f"(IN)agent: {subject}" if subject else "(IN)agent: 자동응답",
            'body': body
        }

    def _cleanup_processed_cache(self):
        one_hour_ago = time.time() - 3600
        self._processed_messages = {k: v for k, v in self._processed_messages.items() if v > one_hour_ago}


# 싱글톤 인스턴스
_auto_response_instance: Optional[AutoResponseService] = None


def get_auto_response_service(log_callback: Callable[[str], None] = None) -> AutoResponseService:
    global _auto_response_instance
    if _auto_response_instance is None:
        _auto_response_instance = AutoResponseService(log_callback)
    return _auto_response_instance
