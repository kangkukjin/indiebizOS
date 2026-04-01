"""
IBL 합성 데이터 생성 (Opus 품질 규칙 기반)

범용 규칙 기반 변형이 아닌, 액션 유형별 맞춤 변형을 생성한다.
- 구어체/비정형 표현 ("그거 해줘", "좀 봐봐")
- 의미 보존 패러프레이즈
- 맥락적 변형 (시간대, 상황 언급)
- 대명사/생략 표현
"""

import json
import sqlite3
import re
import random
from pathlib import Path
from typing import List, Dict, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "ibl_usage.db"
OUTPUT_PATH = PROJECT_ROOT / "data" / "ibl_synthetic_data.json"

random.seed(42)


# ============================================================================
# 1. 액션 유형별 변형 템플릿
# ============================================================================

# 범용 어미 변형 (모든 intent에 적용 가능)
ENDING_MAP = {
    "해줘": ["해", "해줄래", "좀 해줘", "해주세요", "해봐", "해줘요", "좀 해봐"],
    "알려줘": ["알려", "말해줘", "알려줄래", "가르쳐줘", "알려주세요"],
    "보여줘": ["보여", "보여줄래", "보여주세요", "좀 보여봐", "보자"],
    "찾아줘": ["찾아", "찾아봐", "찾아줄래", "검색해줘", "서치해줘"],
    "열어줘": ["열어", "열어봐", "오픈해줘", "띄워줘", "켜줘"],
    "확인해줘": ["확인해", "체크해줘", "봐줘", "확인 좀"],
    "저장해줘": ["저장해", "세이브해줘", "저장 좀", "저장해주세요"],
    "실행해줘": ["실행해", "돌려줘", "시작해줘", "실행 좀"],
    "조회": ["확인", "체크", "검색", "봐봐"],
}

# 범용 접두어 (자연스러운 구어체)
PREFIXES = [
    "", "좀 ", "혹시 ", "그거 ", "빨리 ", "나 ", "나한테 ",
    "지금 ", "오늘 ", "잠깐 ", "참고로 ",
]

# 범용 접미어
SUFFIXES = [
    "", " 할 수 있어?", " 가능해?", " 되나?", " 부탁해",
]

# 액션 패턴별 특화 변형
ACTION_TEMPLATES = {
    "sense:search": [
        "{query} 검색해봐", "{query} 좀 찾아봐", "{query} 관련 자료 있어?",
        "{query} 대해 알아봐줘", "{query} 뭐 나오는지 봐봐",
    ],
    "sense:search_news": [
        "{query} 뉴스 뭐 있어?", "{query} 최신 소식 알려줘", "{query} 기사 좀 찾아",
        "요즘 {query} 어떻대?", "{query} 관련 뉴스 좀",
    ],
    "sense:stock_info": [
        "{symbol} 지금 얼마야?", "{symbol} 주가 좀 봐", "{symbol} 시세 체크해봐",
        "{symbol} 오늘 어때?", "{symbol} 현재가 알려줘",
    ],
    "sense:navigate": [
        "{origin}에서 {dest}까지 어떻게 가?", "{origin}에서 {dest} 가는 길",
        "{dest} 어떻게 가지?", "{dest}까지 길 알려줘", "{dest} 네비 켜줘",
    ],
    "sense:weather": [
        "오늘 날씨 어때?", "비 와?", "우산 챙겨야 해?",
        "지금 밖에 날씨 어때?", "오늘 기온 몇 도야?",
    ],
    "sense:crawl": [
        "이 사이트 내용 좀 봐줘", "웹페이지 긁어와", "이 링크 내용 알려줘",
        "이 URL 읽어봐", "사이트 내용 가져와",
    ],
    "self:time": [
        "몇 시야", "지금 시간", "오늘 며칠이야", "날짜 좀", "시간 좀 알려줘",
        "지금 몇 시지?", "오늘 무슨 요일이야?",
    ],
    "self:discover": [
        "{query} 할 수 있는 거 뭐 있어?", "{query} 관련 기능 좀",
        "{query} 어떻게 해?", "나 {query} 하고 싶은데", "{query} 도구 뭐 있지?",
    ],
    "self:save_memory": [
        "이거 기억해둬", "이거 메모해", "저장해둬 이거",
        "나중에 쓸 거니까 기억해", "이거 잊지 마",
    ],
    "self:search_memory": [
        "예전에 {query} 관련 뭐 있었지?", "{query} 기억나?", "{query} 어디 적어뒀지?",
        "내가 전에 {query} 했던 거", "{query} 메모한 거 찾아봐",
    ],
    "self:schedule": [
        "일정 잡아줘", "스케줄 등록해", "예약해둬",
        "캘린더에 넣어줘", "달력에 추가해",
    ],
    "self:local_save": [
        "파일로 저장해", "파일 만들어줘", "이거 저장해",
        "문서로 남겨줘", "파일에 써줘",
    ],
    "limbs:os_open": [
        "이거 열어", "브라우저로 열어줘", "링크 열어봐",
        "이 사이트 켜줘", "이거 실행해",
    ],
    "limbs:play": [
        "틀어줘", "재생해줘", "들려줘", "음악 켜줘", "이거 좀 들어보자",
    ],
    "limbs:clipboard": [
        "복사해", "클립보드에 넣어", "이거 복사해줘",
        "카피해줘", "복붙할 거니까 복사해",
    ],
    "others:delegate": [
        "{agent}한테 맡겨", "{agent}에게 부탁해", "{agent}한테 시켜",
        "{agent}이 해줄 수 있을 거야", "{agent}한테 넘겨",
    ],
    "others:ask": [
        "{agent}한테 물어봐", "{agent}에게 질문해", "{agent}한테 상담해봐",
        "{agent}이 뭐라 하는지 봐", "{agent}한테 의견 구해",
    ],
    "others:list_projects": [
        "프로젝트 뭐뭐 있어?", "팀 현황 알려줘", "에이전트 누구누구 있지?",
        "프로젝트 리스트 좀", "뭐뭐 할 수 있어?",
    ],
    "sense:cctv_search": [
        "{query} CCTV 좀 봐봐", "{query} 실시간 영상 있어?", "{query} 지금 어때?",
        "{query} 카메라 보여줘", "{query} 상황 좀 봐",
    ],
    "engines:config": [
        "설정 바꿔줘", "세팅 변경해", "환경설정 좀",
        "설정값 수정해줘", "옵션 바꿔",
    ],
    "self:health_query": [
        "건강 기록 봐줘", "내 건강 상태 어때?", "최근 건강 데이터",
        "몸 상태 체크해봐", "건강 기록 있어?",
    ],
}


def extract_params(ibl_code: str) -> Dict[str, str]:
    """IBL 코드에서 파라미터 추출"""
    params = {}
    # {key: "value"} 패턴
    for match in re.finditer(r'(\w+):\s*"([^"]*)"', ibl_code):
        params[match.group(1)] = match.group(2)
    # {key: value} 숫자
    for match in re.finditer(r'(\w+):\s*(\d+)', ibl_code):
        params[match.group(1)] = match.group(2)
    return params


def extract_action(ibl_code: str) -> str:
    """IBL 코드에서 [node:action] 추출"""
    match = re.search(r'\[(\w+:\w+)\]', ibl_code)
    return match.group(1) if match else ""


def generate_for_item(ibl_code: str, existing_intents: List[str]) -> List[str]:
    """하나의 IBL 코드에 대해 합성 변형 생성"""
    action = extract_action(ibl_code)
    params = extract_params(ibl_code)
    variations = set()

    # 1. 액션 특화 템플릿 적용
    if action in ACTION_TEMPLATES:
        templates = ACTION_TEMPLATES[action]
        for tmpl in templates:
            try:
                # 파라미터 치환
                filled = tmpl
                if "{query}" in tmpl:
                    q = params.get("query", params.get("keyword", ""))
                    if q:
                        filled = tmpl.replace("{query}", q)
                    else:
                        continue
                if "{symbol}" in tmpl:
                    s = params.get("symbol", "")
                    if s:
                        filled = tmpl.replace("{symbol}", s)
                    else:
                        continue
                if "{origin}" in tmpl and "{dest}" in tmpl:
                    o = params.get("origin", "")
                    d = params.get("destination", "")
                    if o and d:
                        filled = tmpl.replace("{origin}", o).replace("{dest}", d)
                    else:
                        continue
                if "{agent}" in tmpl:
                    a = params.get("agent_id", "")
                    if a:
                        # agent_id에서 핵심 이름 추출
                        name = a.split("/")[-1] if "/" in a else a
                        filled = tmpl.replace("{agent}", name)
                    else:
                        continue
                if filled not in existing_intents:
                    variations.add(filled)
            except Exception:
                continue

    # 2. 기존 intent의 어미 변형
    for intent in existing_intents[:3]:
        for old_ending, new_endings in ENDING_MAP.items():
            if intent.endswith(old_ending):
                for new_end in random.sample(new_endings, min(2, len(new_endings))):
                    new_intent = intent[:-len(old_ending)] + new_end
                    if new_intent not in existing_intents:
                        variations.add(new_intent)
                break
            if old_ending in intent:
                for new_end in random.sample(new_endings, min(1, len(new_endings))):
                    new_intent = intent.replace(old_ending, new_end, 1)
                    if new_intent not in existing_intents:
                        variations.add(new_intent)
                break

    # 3. 접두어 추가
    for intent in existing_intents[:2]:
        prefix = random.choice(["좀 ", "혹시 ", "지금 ", "나 "])
        new_intent = prefix + intent
        if new_intent not in existing_intents and len(new_intent) < 50:
            variations.add(new_intent)

    # 4. 짧은 구어체 버전
    for intent in existing_intents[:1]:
        # 핵심 키워드만 추출하여 짧은 버전
        words = intent.replace("해줘", "").replace("알려줘", "").replace("보여줘", "").strip()
        if len(words) > 2:
            short = words + " 좀"
            if short not in existing_intents:
                variations.add(short)

    return list(variations)[:8]  # 최대 8개


def main():
    print("=" * 60)
    print("IBL 합성 데이터 생성 (Opus 품질 규칙)")
    print("=" * 60)

    # DB에서 추출
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT intent, ibl_code FROM ibl_examples ORDER BY id").fetchall()
    conn.close()

    groups: Dict[str, List[str]] = {}
    for intent, code in rows:
        if code not in groups:
            groups[code] = []
        if intent not in groups[code]:
            groups[code].append(intent)

    print(f"[데이터] {len(rows)}개 사례, {len(groups)}개 고유 IBL 코드")

    # 합성 데이터 생성
    all_synthetic = []
    total_generated = 0

    for code, intents in groups.items():
        variations = generate_for_item(code, intents)
        for v in variations:
            all_synthetic.append({
                "intent": v,
                "ibl_code": code,
                "source": "opus_synthetic"
            })
        total_generated += len(variations)

    print(f"[생성] {total_generated}개 합성 변형 생성")

    # 저장
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_synthetic, f, ensure_ascii=False, indent=2)
    print(f"[저장] {OUTPUT_PATH}")

    # 분포 확인
    action_counts = {}
    for item in all_synthetic:
        action = extract_action(item['ibl_code'])
        action_counts[action] = action_counts.get(action, 0) + 1
    top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:15]
    print("\n[분포] 상위 15개 액션:")
    for action, count in top_actions:
        print(f"  {action}: {count}개")


if __name__ == '__main__':
    main()
