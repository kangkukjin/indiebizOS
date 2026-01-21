"""
ai_judgment.py - AI 판단 서비스
kvisual-mcp의 aiJudgment.js를 Python으로 포팅

들어온 메시지를 분석하여 응답 방식을 결정합니다.
"""

import json
import re
from typing import Optional, Dict, List, Any
from pathlib import Path

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"
JUDGMENT_PROMPT_PATH = DATA_PATH / "common_prompts" / "base_prompt_judgment.md"


class AIJudgmentService:
    """AI 판단 서비스 - 메시지 분류 및 검색 키워드 추출"""

    # 비즈니스 카테고리 정의
    BUSINESS_CATEGORIES = [
        "나눕니다",      # 무료 나눔
        "구합니다",      # 필요한 것 요청
        "놉시다",        # 함께 하기
        "빌려줍니다",    # 대여 서비스
        "소개합니다",    # 인맥/서비스 소개
        "팔아요",        # 판매
        "할수있습니다",  # 서비스 제공
    ]

    def __init__(self):
        self.config = self._load_config()

    def _load_config(self) -> dict:
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

    def _load_system_prompt(self) -> str:
        """판단용 시스템 프롬프트 로드"""
        if JUDGMENT_PROMPT_PATH.exists():
            try:
                return JUDGMENT_PROMPT_PATH.read_text(encoding='utf-8')
            except:
                pass
        # 파일이 없을 경우 기본 프롬프트
        return """당신은 IndieBizOS의 메시지 분류 에이전트입니다.
들어온 메시지를 분석하여 자동응답 여부를 결정합니다.
JSON 형식만 출력하세요."""

    def judge_message(self, context: dict) -> dict:
        """
        메시지에 대한 AI 판단 수행

        Returns:
            {
                "action": "NO_RESPONSE" | "BUSINESS_RESPONSE",
                "confidence": 0.0-1.0,
                "reasoning": "판단 이유",
                "searches": [
                    {"category": "카테고리", "keywords": ["키워드"], "confidence": 0.8}
                ]
            }
        """
        if not self.config.get("enabled") or not self.config.get("apiKey"):
            return self._get_fallback_judgment(context.get('message', {}))

        try:
            system_prompt = self._load_system_prompt()
            user_prompt = self._build_judgment_prompt(context)
            ai_response = self._call_ai(user_prompt, system_prompt)
            return self._parse_judgment_response(ai_response)
        except Exception as e:
            print(f"[AIJudgment] AI 판단 오류: {e}")
            return self._get_fallback_judgment(context.get('message', {}))

    def _build_judgment_prompt(self, context: dict) -> str:
        """판단 프롬프트 생성 - CoT + Few-shot 적용"""
        message = context.get('message', {})
        neighbor = context.get('neighbor', {})
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
                sender = msg.get('contact_value', '알 수 없음') if msg.get('is_from_user') == 0 else '나'
                history_lines.append(f"[{msg.get('message_time', '')}] {direction} - {sender}: {msg.get('subject', '제목 없음')}")
            history_text = '\n'.join(history_lines)

        # 비즈니스 목록 포맷
        business_list_text = '등록된 비즈니스 없음'
        if business_list:
            business_lines = []
            for b in business_list:
                desc = f" - {b['description']}" if b.get('description') else ''
                business_lines.append(f"- {b['name']}{desc}")
            business_list_text = '\n'.join(business_lines)

        prompt = f"""<judgment_examples>
<example_1>
<incoming_message>"안녕하세요, 혹시 세탁기 수리 가능하신가요? 드럼세탁기인데 물이 안 빠져요."</incoming_message>
<thinking>
1. 의도 파악: 세탁기 수리 서비스 가능 여부 문의
2. 비즈니스 관련성: 서비스 요청 → 관련 있음
3. 검색 필요: "할수있습니다" 카테고리에서 "세탁기", "수리" 키워드 검색
</thinking>
<result>{{"action": "BUSINESS_RESPONSE", "confidence": 0.9, "reasoning": "세탁기 수리 서비스 문의", "searches": [{{"category": "할수있습니다", "keywords": ["세탁기", "수리", "가전"], "confidence": 0.9}}]}}</result>
</example_1>

<example_2>
<incoming_message>"어제 저녁에 뭐 드셨어요? 저는 삼겹살 먹었는데 맛있더라구요 ㅎㅎ"</incoming_message>
<thinking>
1. 의도 파악: 일상적인 안부/잡담
2. 비즈니스 관련성: 개인적 대화 → 관련 없음
3. 판단: 사용자가 직접 응답해야 할 개인적 내용
</thinking>
<result>{{"action": "NO_RESPONSE", "confidence": 0.95, "reasoning": "개인적 일상 대화, 비즈니스 무관", "searches": []}}</result>
</example_2>

<example_3>
<incoming_message>"올리신 자전거 아직 있나요? 관심 있습니다"</incoming_message>
<thinking>
1. 의도 파악: 판매 중인 자전거에 대한 구매 관심 표현
2. 비즈니스 관련성: 거래 문의 → 관련 있음
3. 검색 필요: "팔아요" 카테고리에서 "자전거" 검색
</thinking>
<result>{{"action": "BUSINESS_RESPONSE", "confidence": 0.9, "reasoning": "판매 물품 구매 문의", "searches": [{{"category": "팔아요", "keywords": ["자전거"], "confidence": 0.9}}]}}</result>
</example_3>

<example_4>
<incoming_message>"★긴급★ 무료 체험 이벤트! 지금 클릭하세요!"</incoming_message>
<thinking>
1. 의도 파악: 광고/홍보성 메시지
2. 비즈니스 관련성: 스팸 → 응답 불필요
</thinking>
<result>{{"action": "NO_RESPONSE", "confidence": 0.95, "reasoning": "스팸/광고 메시지", "searches": []}}</result>
</example_4>
</judgment_examples>

<current_context>
<work_guideline>
{work_guideline}
</work_guideline>

<business_document>
{business_doc}
</business_document>

<business_list>
{business_list_text}
</business_list>

<conversation_history>
{history_text}
</conversation_history>

<incoming_message>
발신자: {neighbor.get('name', '알 수 없음')}
제목: {message.get('subject', '제목 없음')}
내용: {message.get('content', '내용 없음')}
</incoming_message>
</current_context>

<judgment_instructions>
위 예시처럼 단계별로 분석하세요:
1. 의도 파악: 발신자가 원하는 것이 무엇인가?
2. 비즈니스 관련성: 우리 비즈니스와 관련이 있는가?
3. 검색 필요 여부: 위 비즈니스 목록 중 어떤 것을 검색해야 하는가?

<category_rule>
searches의 category에는 반드시 위 business_list에 있는 이름 중 하나를 선택하여 그대로 사용하세요. 목록에 없는 이름은 사용하지 마세요.
</category_rule>

<judgment_principles>
- 비즈니스 문의, 서비스 요청, 거래 관련 → BUSINESS_RESPONSE
- 개인적 대화, 사적인 내용, 스팸 → NO_RESPONSE (사용자가 직접 응답)
- 단순 인사/감사도 공식적이면 BUSINESS_RESPONSE (searches는 빈 배열)
- 비즈니스 문의이지만 목록에 해당 비즈니스가 없으면 → BUSINESS_RESPONSE + no_matching_business: true
</judgment_principles>

<output_format>
JSON만 출력하세요:
{{
  "action": "NO_RESPONSE|BUSINESS_RESPONSE",
  "confidence": 0.0-1.0,
  "reasoning": "판단 이유 (1-2문장)",
  "no_matching_business": false,
  "requested_service": "",
  "searches": [
    {{
      "category": "위 비즈니스 목록에서 선택한 이름",
      "keywords": ["키워드1", "키워드2"],
      "confidence": 0.0-1.0
    }}
  ]
}}
</output_format>

<field_descriptions>
no_matching_business:
- true: 상대방이 요청한 서비스/상품이 비즈니스 목록에 없음
- false: 매칭되는 비즈니스가 있거나, 비즈니스 문의가 아님

requested_service:
- no_matching_business가 true일 때, 상대방이 요청한 서비스/상품명을 기록 (예: "피아노 레슨", "자동차 수리")
- no_matching_business가 false이면 빈 문자열
</field_descriptions>
</judgment_instructions>"""

        return prompt

    def _call_ai(self, prompt: str, system_prompt: str = "") -> str:
        """AI API 호출"""
        provider = self.config.get("provider", "anthropic")
        model = self.config.get("model", "claude-sonnet-4-20250514")
        api_key = self.config.get("apiKey", "")

        if provider == "anthropic":
            return self._call_anthropic(prompt, api_key, model, system_prompt)
        elif provider == "openai":
            return self._call_openai(prompt, api_key, model, system_prompt)
        elif provider == "google":
            return self._call_google(prompt, api_key, model, system_prompt)
        else:
            raise ValueError(f"지원하지 않는 프로바이더: {provider}")

    def _call_anthropic(self, prompt: str, api_key: str, model: str, system_prompt: str = "") -> str:
        """Anthropic API 호출"""
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    def _call_openai(self, prompt: str, api_key: str, model: str, system_prompt: str = "") -> str:
        """OpenAI API 호출"""
        import openai
        client = openai.OpenAI(api_key=api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model=model,
            max_tokens=1000,
            messages=messages
        )
        return response.choices[0].message.content

    def _call_google(self, prompt: str, api_key: str, model: str, system_prompt: str = "") -> str:
        """Google API 호출"""
        from google import genai
        client = genai.Client(api_key=api_key)
        config = {}
        if system_prompt:
            config['system_instruction'] = system_prompt
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config if config else None
        )
        return response.text

    def _parse_judgment_response(self, response: str) -> dict:
        """AI 응답 파싱"""
        try:
            # JSON 추출
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            print(f"[AIJudgment] 응답 파싱 오류: {e}")

        # 파싱 실패 시 텍스트 기반 판단
        if 'NO_RESPONSE' in response:
            return {"action": "NO_RESPONSE", "confidence": 0.5, "reasoning": "파싱 실패", "searches": []}
        else:
            return {"action": "BUSINESS_RESPONSE", "confidence": 0.5, "reasoning": "파싱 실패", "searches": []}

    def _get_fallback_judgment(self, message: dict) -> dict:
        """폴백 판단 (AI 호출 실패 시)"""
        subject = (message.get('subject') or '').lower()
        content = (message.get('content') or '').lower()

        # 스팸 패턴
        spam_keywords = ['광고', '홍보', '무료체험', '당첨', '클릭']
        if any(kw in subject or kw in content for kw in spam_keywords):
            return {
                "action": "NO_RESPONSE",
                "confidence": 0.7,
                "reasoning": "스팸/광고로 판단",
                "searches": []
            }

        # 인사말 패턴
        greeting_keywords = ['안녕', '감사', '고마', '반갑']
        if any(kw in subject or kw in content for kw in greeting_keywords):
            return {
                "action": "BUSINESS_RESPONSE",
                "confidence": 0.7,
                "reasoning": "인사/감사 메시지",
                "searches": []
            }

        # 기본: 비즈니스 응답
        return {
            "action": "BUSINESS_RESPONSE",
            "confidence": 0.5,
            "reasoning": "기본 판단",
            "searches": []
        }


# 싱글톤 인스턴스
_judgment_instance: Optional[AIJudgmentService] = None


def get_ai_judgment_service() -> AIJudgmentService:
    """AI 판단 서비스 인스턴스 반환"""
    global _judgment_instance
    if _judgment_instance is None:
        _judgment_instance = AIJudgmentService()
    return _judgment_instance
