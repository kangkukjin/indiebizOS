"""
IBL 합성 데이터 생성: LLM으로 다양한 자연어 변형 생성

기존 530개 (intent, ibl_code) 쌍에 대해 Gemini API로
비정형/구어체/다양한 표현의 자연어 변형을 생성한다.

사용법:
    cd /Users/kangkukjin/Desktop/AI/indiebizOS/backend
    python3 ibl_synthetic_generator.py
"""

import json
import os
import sqlite3
import time
import random
from pathlib import Path
from typing import List, Dict

from google import genai

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "ibl_usage.db"
OUTPUT_PATH = PROJECT_ROOT / "data" / "training" / "ibl_synthetic_data.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
client = genai.Client(api_key=GEMINI_API_KEY)

GENERATION_PROMPT = """당신은 indieBizOS라는 AI 비서 시스템의 사용자 명령어 변형을 생성하는 전문가입니다.

아래에 IBL 코드와 그에 대응하는 자연어 명령어 예시들이 있습니다.
같은 IBL 코드를 실행시킬 수 있는 **다양한 자연어 표현**을 5개 생성해주세요.

규칙:
1. 실제 한국어 사용자가 AI 비서에게 말하듯 자연스럽게
2. 반드시 구어체, 비정형 표현을 포함할 것 ("그거 해줘", "아까 그거", "좀 봐봐" 등)
3. 같은 의미지만 완전히 다른 표현을 사용할 것
4. 줄임말, 오타 포함 가능 (실제 사용 패턴 반영)
5. 너무 길지 않게 (한 문장)

IBL 코드: {ibl_code}
기존 명령어 예시:
{existing_intents}

JSON 배열로만 응답하세요. 다른 설명 없이:
["변형1", "변형2", "변형3", "변형4", "변형5"]"""


def load_examples() -> Dict[str, List[str]]:
    """DB에서 ibl_code별 intent 그룹핑"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("SELECT intent, ibl_code FROM ibl_examples ORDER BY id")
    rows = cursor.fetchall()
    conn.close()

    code_to_intents: Dict[str, List[str]] = {}
    for intent, code in rows:
        if code not in code_to_intents:
            code_to_intents[code] = []
        if intent not in code_to_intents[code]:
            code_to_intents[code].append(intent)

    print(f"[로드] {len(rows)}개 사례, {len(code_to_intents)}개 고유 IBL 코드")
    return code_to_intents


def generate_variations(ibl_code: str, existing_intents: List[str]) -> List[str]:
    """Claude API로 자연어 변형 생성"""
    intents_text = "\n".join(f"- {i}" for i in existing_intents[:5])
    prompt = GENERATION_PROMPT.format(
        ibl_code=ibl_code,
        existing_intents=intents_text
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()
        # JSON 배열 파싱 — 마크다운 코드블록 제거
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        if text.startswith("["):
            variations = json.loads(text)
            return [v for v in variations if isinstance(v, str) and len(v) > 2]
    except Exception as e:
        print(f"  [에러] {str(e)[:80]}")
    return []


def main():
    print("=" * 60)
    print("IBL 합성 데이터 생성 (Claude API)")
    print("=" * 60)

    code_to_intents = load_examples()

    # 기존 데이터가 있으면 이어서 생성
    all_synthetic = []
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            all_synthetic = json.load(f)
        existing_codes = {item['ibl_code'] for item in all_synthetic}
        print(f"[기존] {len(all_synthetic)}개 합성 데이터 로드, {len(existing_codes)}개 코드 처리 완료")
    else:
        existing_codes = set()

    # 미처리 코드만 대상
    codes_to_process = [
        (code, intents) for code, intents in code_to_intents.items()
        if code not in existing_codes
    ]
    random.shuffle(codes_to_process)

    print(f"[생성] {len(codes_to_process)}개 IBL 코드에 대해 변형 생성 시작")
    print(f"[생성] 예상 API 호출: {len(codes_to_process)}회 (Haiku)")

    generated_count = 0
    error_count = 0

    for i, (code, intents) in enumerate(codes_to_process):
        variations = generate_variations(code, intents)

        if variations:
            for v in variations:
                all_synthetic.append({
                    'intent': v,
                    'ibl_code': code,
                    'source': 'llm_synthetic'
                })
            generated_count += len(variations)
        else:
            error_count += 1

        # 진행 상황 (50개마다)
        if (i + 1) % 50 == 0 or i == len(codes_to_process) - 1:
            print(f"  [{i+1}/{len(codes_to_process)}] 생성: {generated_count}개, 에러: {error_count}개")
            # 중간 저장
            with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
                json.dump(all_synthetic, f, ensure_ascii=False, indent=2)

        # Rate limit 방지
        time.sleep(0.3)

    # 최종 저장
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_synthetic, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] 총 {len(all_synthetic)}개 합성 데이터 → {OUTPUT_PATH}")
    print(f"  신규 생성: {generated_count}개")
    print(f"  에러: {error_count}개")


if __name__ == '__main__':
    main()
