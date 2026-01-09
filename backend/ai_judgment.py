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
            prompt = self._build_judgment_prompt(context)
            ai_response = self._call_ai(prompt)
            return self._parse_judgment_response(ai_response)
        except Exception as e:
            print(f"[AIJudgment] AI 판단 오류: {e}")
            return self._get_fallback_judgment(context.get('message', {}))

    def _build_judgment_prompt(self, context: dict) -> str:
        """판단 프롬프트 생성"""
        message = context.get('message', {})
        neighbor = context.get('neighbor', {})
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
                history_lines.append(f"[{msg.get('message_time', '')}] {direction} - {sender}: {msg.get('subject', '제목 없음')}")
            history_text = '\n'.join(history_lines)

        prompt = f"""당신은 비즈니스 매칭 에이전트입니다. 다음 정보를 바탕으로 들어온 메시지에 대한 응답 방식을 결정해주세요.

## 근무지침
{work_guideline}

## 나의 열린 비즈니스 문서
{business_doc}

## 대화 기록
{history_text}

## 들어온 메시지
발신자: {neighbor.get('name', '알 수 없음')}
제목: {message.get('subject', '제목 없음')}
내용: {message.get('content', '내용 없음')}

## 응답 결정
다음 중 하나를 선택하고 JSON 형식으로 응답해주세요:
1. NO_RESPONSE - 자동응답이 필요없는 경우 (개인적인 대화, 사적인 내용, 비즈니스와 무관한 내용, 스팸, 광고 등)
2. BUSINESS_RESPONSE - 비즈니스 관련 자동응답이 필요한 경우 (비즈니스 문의, 요청, 인사 등)

중요: 비즈니스와 관련된 내용이거나 공식적인 응답이 필요한 경우에만 BUSINESS_RESPONSE를 선택하세요.
개인적이거나 사적인 대화는 NO_RESPONSE로 분류하여 사용자가 직접 응답할 수 있도록 하세요.
BUSINESS_RESPONSE를 선택한 경우, 검색해야 할 비즈니스 카테고리와 키워드를 함께 제공해주세요.
단순 인사나 감사의 경우 searches를 빈 배열로 제공하세요.

비즈니스 카테고리:
- 나눕니다: 무료 나눔
- 구합니다: 필요한 것 요청
- 놉시다: 함께 하기
- 빌려줍니다: 대여 서비스
- 소개합니다: 인맥/서비스 소개
- 팔아요: 판매
- 할수있습니다: 서비스 제공

응답 형식 (JSON만 출력):
{{
  "action": "NO_RESPONSE|BUSINESS_RESPONSE",
  "confidence": 0.0-1.0,
  "reasoning": "판단 이유",
  "searches": [
    {{
      "category": "비즈니스 카테고리",
      "keywords": ["키워드1", "키워드2"],
      "confidence": 0.0-1.0
    }}
  ]
}}"""

        return prompt

    def _call_ai(self, prompt: str) -> str:
        """AI API 호출"""
        provider = self.config.get("provider", "anthropic")
        model = self.config.get("model", "claude-sonnet-4-20250514")
        api_key = self.config.get("apiKey", "")

        if provider == "anthropic":
            return self._call_anthropic(prompt, api_key, model)
        elif provider == "openai":
            return self._call_openai(prompt, api_key, model)
        elif provider == "google":
            return self._call_google(prompt, api_key, model)
        else:
            raise ValueError(f"지원하지 않는 프로바이더: {provider}")

    def _call_anthropic(self, prompt: str, api_key: str, model: str) -> str:
        """Anthropic API 호출"""
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    def _call_openai(self, prompt: str, api_key: str, model: str) -> str:
        """OpenAI API 호출"""
        import openai
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=1000,
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
