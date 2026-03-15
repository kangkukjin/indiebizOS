"""
ibl_usage_generator.py - IBL 합성 용례 생성기
IndieBiz OS Core

ibl_nodes.yaml의 321개 액션 스펙을 기반으로 (자연어 → IBL) 쌍을 자동 생성.
3단계: 단일 액션 → 파이프라인 → 복합 시나리오.

사용법:
  python ibl_usage_generator.py                    # Stage 1+2 (AI 불필요)
  python ibl_usage_generator.py --stages 1,2,3     # 전체 (Stage 3은 AI 필요)
  python ibl_usage_generator.py --stats             # 현재 DB 통계
"""

import sys
import os
import yaml
import json
import random
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# backend를 path에 추가
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


# =============================================================================
# 예시 타겟 값 (target_key별 현실적인 값)
# =============================================================================

_EXAMPLE_TARGETS = {
    "query": ["AI 뉴스", "삼성전자", "부동산 시세", "반도체 산업", "금리 전망"],
    "url": ["https://example.com/article", "https://naver.com"],
    "symbol": ["삼성전자", "AAPL", "005930", "MSFT", "SPY"],
    "keyword": ["임대차보호법", "인공지능", "반도체"],
    "path": ["보고서.md", "분석결과.txt", "~/Documents/memo.md"],
    "code": ["print('hello world')", "import pandas as pd"],
    "corp_name": ["삼성전자", "LG에너지솔루션", "현대자동차"],
    "ticker": ["AAPL", "GOOGL", "TSLA"],
    "city": ["서울", "부산", "도쿄"],
    "message": ["안녕하세요, 분석 결과를 보내드립니다.", "회의 자료 전달합니다."],
    "action": ["검색", "열기", "저장"],
    "content": ["오늘의 뉴스 요약입니다.", "보고서 내용"],
    "agent_id": ["투자/투자컨설팅", "컨텐츠/컨텐츠", "정보센터/정보수집"],
    "name": ["뉴스 브리핑", "주가 모니터링", "일일 리포트"],
}

# target_key가 없는 경우 description에서 추출할 힌트
_DESC_HINTS = {
    "검색": "AI 뉴스",
    "조회": "삼성전자",
    "전송": "안녕하세요",
    "열기": "https://example.com",
    "저장": "결과.md",
    "실행": "작업",
    "관리": "목록",
    "생성": "보고서",
    "삭제": "항목",
}


# =============================================================================
# Stage 1: 단일 액션 (규칙 기반)
# =============================================================================

def _get_primary_param_value(action_config: dict) -> tuple:
    """액션 설정에서 주요 파라미터의 (key, value) 생성

    Returns:
        (param_key, param_value) 또는 ("", "") if 없음
    """
    target_key = action_config.get('target_key', '')
    description = action_config.get('description', '')

    # 1. target_key로 매칭
    if target_key and target_key in _EXAMPLE_TARGETS:
        return (target_key, random.choice(_EXAMPLE_TARGETS[target_key]))

    # 2. description에서 힌트
    if target_key:
        for hint, default_target in _DESC_HINTS.items():
            if hint in description:
                return (target_key, default_target)
        return (target_key, "")

    return ("", "")


def _make_intent_from_description(description: str, node: str) -> str:
    """액션 description을 자연어 의도로 변환"""
    # 괄호 내용 제거 (Phase 표시, 구현 세부사항 등)
    import re
    clean = re.sub(r'\([^)]*\)', '', description).strip()
    clean = re.sub(r'（[^）]*）', '', clean).strip()

    # 간결화
    if len(clean) > 40:
        clean = clean[:40].rsplit(' ', 1)[0]

    return clean


def generate_stage1(nodes_data: dict) -> List[Dict]:
    """Stage 1: 각 액션에서 규칙 기반으로 단일 용례 생성"""
    examples = []
    nodes = nodes_data.get('nodes', {})

    for node_name, node_config in nodes.items():
        actions = node_config.get('actions', {})
        for action_name, action_config in actions.items():
            if not isinstance(action_config, dict):
                continue

            # stub은 건너뛰기
            if action_config.get('router') == 'stub':
                continue

            description = action_config.get('description', action_name)
            param_key, param_val = _get_primary_param_value(action_config)
            intent = _make_intent_from_description(description, node_name)

            # IBL 코드 생성 (params-only 문법)
            if param_key and param_val:
                ibl_code = f'[{node_name}:{action_name}]{{{param_key}: "{param_val}"}}'
            else:
                ibl_code = f'[{node_name}:{action_name}]'

            examples.append({
                'intent': intent,
                'ibl_code': ibl_code,
                'nodes': node_name,
                'category': 'single',
                'difficulty': 1,
                'source': 'synthetic',
                'tags': f'{node_name},{action_name}',
            })

    return examples


def generate_for_package(package_id: str) -> int:
    """특정 패키지의 새 액션에 대해서만 용례 생성 및 DB 저장.

    패키지 설치 직후 호출되어, 새로 등록된 액션의 기본 용례를 즉시 생성.
    이미 동일 intent가 존재하면 스킵 (중복 방지).

    Args:
        package_id: 설치된 패키지 ID (예: "real-estate")

    Returns:
        추가된 용례 수
    """
    from runtime_utils import get_base_path

    # 1. 패키지의 ibl_actions.yaml에서 등록된 액션 목록 확인
    pkg_path = get_base_path() / "data" / "packages" / "installed" / "tools" / package_id
    actions_file = pkg_path / "ibl_actions.yaml"
    if not actions_file.exists():
        return 0

    with open(actions_file, 'r', encoding='utf-8') as f:
        pkg_def = yaml.safe_load(f) or {}

    # 패키지 정의에서 노드:액션 추출
    target_actions = {}  # {(node, action): action_config}

    if 'actions' in pkg_def and 'node' in pkg_def:
        # 단일 노드 형식
        node_name = pkg_def['node']
        for action_name, action_config in pkg_def.get('actions', {}).items():
            if isinstance(action_config, dict):
                target_actions[(node_name, action_name)] = action_config
    elif 'nodes' in pkg_def:
        # 복수 노드 형식
        for node_name, node_def in pkg_def['nodes'].items():
            for action_name, action_config in node_def.get('actions', {}).items():
                if isinstance(action_config, dict):
                    target_actions[(node_name, action_name)] = action_config

    if not target_actions:
        return 0

    # 2. 해당 액션들에 대해 Stage 1 용례 생성
    examples = []
    for (node_name, action_name), action_config in target_actions.items():
        if action_config.get('router') == 'stub':
            continue

        description = action_config.get('description', action_name)
        param_key, param_val = _get_primary_param_value(action_config)
        intent = _make_intent_from_description(description, node_name)

        # IBL 코드 생성 (params-only 문법)
        if param_key and param_val:
            ibl_code = f'[{node_name}:{action_name}]{{{param_key}: "{param_val}"}}'
        else:
            ibl_code = f'[{node_name}:{action_name}]'

        examples.append({
            'intent': intent,
            'ibl_code': ibl_code,
            'nodes': node_name,
            'category': 'single',
            'difficulty': 1,
            'source': 'synthetic',
            'tags': f'{node_name},{action_name},{package_id}',
        })

    if not examples:
        return 0

    # 3. DB에 추가 (중복 체크: 동일 intent 또는 동일 ibl_code가 있으면 스킵)
    from ibl_usage_db import IBLUsageDB, DB_PATH
    import sqlite3 as _sqlite3
    db = IBLUsageDB()

    # 기존 intent/ibl_code 집합 로드
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    existing = set()
    for row in conn.execute("SELECT LOWER(intent) as i, ibl_code as c FROM ibl_examples").fetchall():
        existing.add(row['i'])
        existing.add(row['c'])
    conn.close()

    added = 0
    for ex in examples:
        # 중복 스킵
        if ex['intent'].lower() in existing or ex['ibl_code'] in existing:
            continue
        try:
            example_id = db.add_example(**ex)
            if example_id:
                added += 1
                existing.add(ex['intent'].lower())
                existing.add(ex['ibl_code'])
        except Exception:
            pass

    if added > 0:
        print(f"[IBL Generator] {package_id}: {added}개 용례 자동 생성")

    return added


# =============================================================================
# Stage 2: 파이프라인 (템플릿 기반)
# =============================================================================

# (의도, IBL 코드, 노드들, 카테고리)
_PIPELINE_TEMPLATES = [
    # 검색 → 저장
    (
        "AI 뉴스를 검색해서 파일로 저장해줘",
        '[sense:search]{query: "AI 뉴스"} >> [self:local_save]{path: "ai_news.md"}',
        "sense,self", "pipeline"
    ),
    (
        "부동산 뉴스 검색해서 마크다운으로 저장",
        '[sense:search_news]{query: "부동산"} >> [self:local_save]{path: "부동산뉴스.md"}',
        "sense,self", "pipeline"
    ),
    (
        "반도체 관련 뉴스 찾아서 저장해줘",
        '[sense:search_news]{query: "반도체"} >> [self:local_save]{path: "반도체뉴스.md"}',
        "sense,self", "pipeline"
    ),
    # 병렬 검색
    (
        "삼성전자랑 SK하이닉스 주가 동시에 확인해줘",
        '[sense:price]{symbol: "삼성전자"} & [sense:price]{symbol: "SK하이닉스"}',
        "sense", "pipeline"
    ),
    (
        "애플이랑 마이크로소프트 주가 비교해줘",
        '[sense:price]{symbol: "AAPL"} & [sense:price]{symbol: "MSFT"}',
        "sense", "pipeline"
    ),
    (
        "AI 뉴스랑 부동산 뉴스 동시에 검색해줘",
        '[sense:search]{query: "AI 뉴스"} & [sense:search]{query: "부동산 뉴스"}',
        "sense", "pipeline"
    ),
    (
        "서울이랑 부산 날씨 같이 알려줘",
        '[sense:weather]{city: "서울"} & [sense:weather]{city: "부산"}',
        "sense", "pipeline"
    ),
    # 검색 → 에이전트 분석
    (
        "AI 뉴스 검색해서 투자 에이전트한테 분석 요청해줘",
        '[sense:search]{query: "AI 뉴스"} >> [others:ask_sync]{agent_id: "투자/투자컨설팅", message: "이 뉴스를 투자 관점에서 분석해주세요"}',
        "sense,others", "pipeline"
    ),
    # 검색 → 메신저 전송
    (
        "오늘 뉴스 검색해서 텔레그램으로 보내줘",
        '[sense:search_news]{query: "오늘 뉴스"} >> [others:channel_send]{channel: "telegram"}',
        "sense,others", "pipeline"
    ),
    # Fallback 패턴
    (
        "삼성전자 주가 조회하되, 실패하면 종목 검색으로 찾아봐",
        '[sense:price]{symbol: "삼성전자"} ?? [sense:search_stock]{query: "삼성전자"}',
        "sense", "pipeline"
    ),
    # 크롤링 → 저장
    (
        "이 웹페이지 내용 크롤링해서 파일로 저장해줘",
        '[sense:crawl]{url: "https://example.com/article"} >> [self:local_save]{path: "crawled.md"}',
        "sense,self", "pipeline"
    ),
    # 검색 → 시각화
    (
        "삼성전자 주가 조회해서 차트로 그려줘",
        '[sense:price]{symbol: "삼성전자"} >> [engines:create]{name: "삼성전자 주가 차트", type: "chart"}',
        "sense,engines", "pipeline"
    ),
    # 유튜브 → 저장
    (
        "유튜브 영상 자막 추출해서 파일로 저장해줘",
        '[sense:video_transcript]{url: "https://youtube.com/watch?v=example"} >> [self:local_save]{path: "transcript.md"}',
        "sense,self", "pipeline"
    ),
    # 복합 병렬 → 저장
    (
        "AI 뉴스랑 부동산 뉴스 동시에 찾아서 브리핑 파일로 만들어줘",
        '[sense:search]{query: "AI 뉴스"} & [sense:search]{query: "부동산 뉴스"} >> [self:local_save]{path: "briefing.md"}',
        "sense,self", "pipeline"
    ),
    # 3단 파이프라인
    (
        "삼성전자 뉴스 검색 후 분석 에이전트에게 보내고 결과 저장해줘",
        '[sense:search_news]{query: "삼성전자"} >> [others:ask_sync]{agent_id: "투자/투자컨설팅", message: "분석해줘"} >> [self:local_save]{path: "분석결과.md"}',
        "sense,others,self", "complex"
    ),
    # 블로그 검색 → 저장
    (
        "블로그에서 AI 관련 글 찾아서 정리해줘",
        '[self:rag_search]{query: "AI 인공지능"} >> [self:local_save]{path: "blog_ai.md"}',
        "self", "pipeline"
    ),
    # 법률 검색
    (
        "임대차보호법 관련 법령 검색해줘",
        '[sense:search_laws]{keyword: "임대차보호법"}',
        "sense", "single"
    ),
    # 사진 검색
    (
        "여행 사진 검색해줘",
        '[self:search_photos]{keyword: "여행"}',
        "self", "single"
    ),
    # 포지 콘텐츠 생성
    (
        "AI 트렌드 발표 슬라이드 만들어줘",
        '[engines:create]{name: "AI 트렌드 2024", type: "slide"}',
        "engines", "single"
    ),
    (
        "배경음악 작곡해줘",
        '[engines:create]{name: "편안한 피아노 음악", type: "music"}',
        "engines", "single"
    ),
    # 인터페이스
    (
        "구글 홈페이지 열어줘",
        '[limbs:navigate]{url: "https://google.com"}',
        "limbs", "single"
    ),
    (
        "화면 스크린샷 찍어줘",
        '[limbs:browser_snapshot]{}',
        "limbs", "single"
    ),
    # 스트림
    (
        "재즈 음악 틀어줘",
        '[limbs:play]{query: "jazz music"}',
        "limbs", "single"
    ),
    (
        "라디오 KBS 클래식 FM 틀어줘",
        '[limbs:radio_play]{station: "KBS 클래식FM"}',
        "limbs", "single"
    ),
    # 메신저
    (
        "이메일로 보고서 보내줘",
        '[others:channel_send]{channel: "report@example.com", type: "email", subject: "보고서"}',
        "others", "single"
    ),
    # 투자 병렬
    (
        "한국과 미국 시장 주요 종목 동시 확인",
        '[sense:price]{symbol: "005930"} & [sense:price]{symbol: "AAPL"} & [sense:price]{symbol: "SPY"}',
        "sense", "pipeline"
    ),
    # 웹사이트 생성
    (
        "카페 홈페이지 만들어줘",
        '[engines:create_site]{name: "카페 홈페이지", type: "website"}',
        "engines", "single"
    ),
    # 건강 기록
    (
        "오늘 운동 기록 저장해줘",
        '[sense:save_health]{name: "운동", type: "exercise", duration: "30분"}',
        "sense", "single"
    ),
    # 시스템 도구
    (
        "할일 목록 만들어줘",
        '[self:todo]{name: "프로젝트 진행상황 정리"}',
        "self", "single"
    ),
    (
        "현재 시간 알려줘",
        '[self:time]{}',
        "self", "single"
    ),
    # 검색 + Fallback + 저장
    (
        "뉴스 검색 시도하고, 안 되면 종합 검색하고, 결과 저장",
        '[sense:search_news]{query: "AI"} ?? [sense:search]{query: "AI 뉴스"} >> [self:local_save]{path: "news.md"}',
        "sense,self", "complex"
    ),
    # 워크플로우 관련
    (
        "저장된 워크플로우 목록 보여줘",
        '[self:list_workflows]{}',
        "self", "single"
    ),
    (
        "뉴스 브리핑 워크플로우 실행해줘",
        '[self:run]{name: "news_briefing"}',
        "self", "single"
    ),
    # 통계 (KOSIS)
    (
        "인구 통계 검색해줘",
        '[sense:search_statistics]{query: "인구"}',
        "sense", "single"
    ),
    # 쇼핑
    (
        "노트북 가격 비교해줘",
        '[sense:compare_prices]{query: "맥북 프로 14인치"}',
        "sense", "single"
    ),
    # 위치 서비스
    (
        "강남역 근처 맛집 찾아줘",
        '[sense:restaurant]{city: "강남역"}',
        "sense", "single"
    ),
    (
        "서울에서 부산까지 길찾기",
        '[sense:directions]{start: "서울", destination: "부산"}',
        "sense", "single"
    ),
    # 병렬 크롤링
    (
        "네이버랑 다음 메인 동시에 크롤링해줘",
        '[sense:crawl]{url: "https://naver.com"} & [sense:crawl]{url: "https://daum.net"}',
        "sense", "pipeline"
    ),
    # 파일 관리
    (
        "데스크탑 파일 목록 보여줘",
        '[self:local_save]{path: "~/Desktop", action: "list"}',
        "self", "single"
    ),
]


def generate_stage2() -> List[Dict]:
    """Stage 2: 미리 정의된 파이프라인/복합 용례"""
    examples = []
    for intent, ibl_code, nodes, category in _PIPELINE_TEMPLATES:
        difficulty = 1 if category == 'single' else (2 if category == 'pipeline' else 3)
        examples.append({
            'intent': intent,
            'ibl_code': ibl_code,
            'nodes': nodes,
            'category': category,
            'difficulty': difficulty,
            'source': 'synthetic',
            'tags': 'template',
        })
    return examples


# =============================================================================
# Stage 3: 자연어 변형 (규칙 기반 패러프레이즈)
# =============================================================================

# 동사/어미 변형 패턴: (원형 키워드) → [변형1, 변형2, ...]
_VERB_VARIATIONS = {
    "조회": ["확인", "알려줘", "보여줘", "가져와", "찾아봐"],
    "검색": ["찾아줘", "찾아봐", "검색해줘", "서치해줘"],
    "관리": ["보여줘", "현황", "목록", "리스트"],
    "생성": ["만들어줘", "만들어", "생성해줘", "새로"],
    "저장": ["저장해줘", "기록해줘", "남겨줘", "파일로 저장"],
    "전송": ["보내줘", "전달해줘", "전송해줘"],
    "실행": ["실행해줘", "돌려줘", "시작해줘", "동작시켜"],
    "목록": ["리스트", "목록 보여줘", "뭐가 있어", "뭐 있어", "몇 개"],
    "열기": ["열어줘", "열어", "오픈해줘"],
    "삭제": ["지워줘", "삭제해줘", "제거해줘"],
}

# 명사 변형 (동의어 맵핑)
_NOUN_SYNONYMS = {
    "사이트": ["홈페이지", "웹사이트", "웹페이지", "사이트"],
    "홈페이지": ["사이트", "웹사이트", "웹페이지", "홈페이지"],
    "레지스트리": ["목록", "등록된 것", "현황", "리스트"],
    "워크플로우": ["자동화", "작업흐름", "워크플로"],
    "에이전트": ["AI", "도우미", "비서"],
    "프로젝트": ["작업", "프로젝트"],
    "파일": ["문서", "파일"],
    "스케줄": ["예약", "일정", "스케줄"],
    "스위치": ["토글", "스위치", "설정"],
    "트리거": ["트리거", "자동실행", "이벤트"],
    "API": ["API", "외부연동", "인터페이스"],
}

# 질문형 패턴
_QUESTION_TEMPLATES = [
    "{noun} {verb_var}",
    "{noun} 좀 {verb_var}",
    "{noun} {verb_var}?",
    "지금 {noun} {verb_var}",
    "현재 {noun} {verb_var}",
    "등록된 {noun} {verb_var}",
    "우리 {noun} {verb_var}",
    "{noun} 어떻게 돼?",
    "{noun} 현황 알려줘",
]


def _extract_core_parts(intent: str) -> tuple:
    """intent에서 핵심 명사와 동사 추출"""
    # 동사 키워드 찾기
    found_verb = None
    for verb_key in _VERB_VARIATIONS:
        if verb_key in intent:
            found_verb = verb_key
            break

    # 명사 키워드 찾기
    found_nouns = []
    for noun_key in _NOUN_SYNONYMS:
        if noun_key in intent:
            found_nouns.append(noun_key)

    return found_nouns, found_verb


def generate_stage3(existing_examples: List[Dict], max_per_example: int = 3) -> List[Dict]:
    """Stage 3: 기존 용례의 자연어 변형 생성 (규칙 기반)

    각 용례의 intent를 분석하여 동의어/질문형 변형을 생성.
    AI 없이 패턴 기반으로 동작하므로 빠르고 비용 없음.
    """
    variations = []

    for ex in existing_examples:
        intent = ex.get('intent', '')
        ibl_code = ex.get('ibl_code', '')

        if not intent or not ibl_code:
            continue

        nouns, verb = _extract_core_parts(intent)
        if not nouns and not verb:
            continue

        generated = set()
        generated.add(intent)  # 원본 중복 방지

        # 1) 동사 변형
        if verb and verb in _VERB_VARIATIONS:
            for verb_var in _VERB_VARIATIONS[verb]:
                new_intent = intent.replace(verb, verb_var)
                if new_intent not in generated and new_intent != intent:
                    generated.add(new_intent)

        # 2) 명사 동의어 교체
        for noun in nouns:
            if noun in _NOUN_SYNONYMS:
                for synonym in _NOUN_SYNONYMS[noun]:
                    new_intent = intent.replace(noun, synonym)
                    if new_intent not in generated and new_intent != intent:
                        generated.add(new_intent)

        # 3) 질문형 패턴 (명사+동사 조합)
        if nouns and verb and verb in _VERB_VARIATIONS:
            main_noun = nouns[0]
            for verb_var in _VERB_VARIATIONS[verb][:2]:  # 상위 2개만
                for tmpl in random.sample(_QUESTION_TEMPLATES, min(2, len(_QUESTION_TEMPLATES))):
                    new_intent = tmpl.format(noun=main_noun, verb_var=verb_var)
                    if new_intent not in generated:
                        generated.add(new_intent)

        # 원본 제거하고 max_per_example개만
        generated.discard(intent)
        selected = list(generated)[:max_per_example]

        for var_intent in selected:
            variations.append({
                'intent': var_intent,
                'ibl_code': ibl_code,
                'nodes': ex.get('nodes', ''),
                'category': ex.get('category', 'single'),
                'difficulty': ex.get('difficulty', 1),
                'source': 'synthetic_v3',
                'tags': ex.get('tags', '') + ',variation',
            })

    return variations


# =============================================================================
# 메인 실행
# =============================================================================

def load_nodes_yaml() -> dict:
    """ibl_nodes.yaml 로드"""
    yaml_path = Path(__file__).parent.parent / "data" / "ibl_nodes.yaml"
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def generate_all(stages: List[int] = None) -> Dict[str, int]:
    """전체 합성 데이터 생성 + DB 저장

    Args:
        stages: 실행할 단계 [1, 2, 3] (기본: [1, 2, 3])

    Returns:
        {stage1: N, stage2: N, stage3: N, total: N}
    """
    from ibl_usage_db import IBLUsageDB

    if stages is None:
        stages = [1, 2, 3]

    db = IBLUsageDB()
    result = {}
    base_examples = []  # Stage 1+2 (Stage 3의 입력)
    all_examples = []

    if 1 in stages:
        nodes_data = load_nodes_yaml()
        s1 = generate_stage1(nodes_data)
        result['stage1'] = len(s1)
        base_examples.extend(s1)
        all_examples.extend(s1)
        print(f"[Generator] Stage 1: {len(s1)}개 단일 액션 용례 생성")

    if 2 in stages:
        s2 = generate_stage2()
        result['stage2'] = len(s2)
        base_examples.extend(s2)
        all_examples.extend(s2)
        print(f"[Generator] Stage 2: {len(s2)}개 파이프라인/복합 용례 생성")

    if 3 in stages:
        # Stage 3: 기존 용례 기반 자연어 변형
        source = base_examples if base_examples else []
        # base_examples가 없으면 DB에서 기존 용례 로드
        if not source:
            import sqlite3
            from ibl_usage_db import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT intent, ibl_code, nodes, category, difficulty, tags FROM ibl_examples").fetchall()
            source = [dict(r) for r in rows]
            conn.close()
            print(f"[Generator] Stage 3: DB에서 {len(source)}개 기존 용례 로드")

        s3 = generate_stage3(source)
        result['stage3'] = len(s3)
        all_examples.extend(s3)
        print(f"[Generator] Stage 3: {len(s3)}개 자연어 변형 생성")

    if all_examples:
        count = db.add_examples_batch(all_examples)
        result['total'] = count
        print(f"[Generator] DB 저장 완료: 총 {count}개")
    else:
        result['total'] = 0

    return result


def print_stats():
    """현재 DB 통계 출력"""
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    stats = db.get_stats()
    print("\n=== IBL 용례 사전 통계 ===")
    print(f"총 용례: {stats['total_examples']}개")
    print(f"카테고리별: {stats['by_category']}")
    print(f"소스별: {stats['by_source']}")
    print(f"실행 로그: {stats['execution_logs']}개 (성공: {stats['successful_logs']})")
    print(f"시맨틱 검색: {'가능' if stats['semantic_available'] else '불가 (FTS5만 사용)'}")


def main():
    parser = argparse.ArgumentParser(description="IBL 합성 용례 생성기")
    parser.add_argument('--stages', type=str, default='1,2',
                        help='실행할 단계 (쉼표 구분, 예: 1,2)')
    parser.add_argument('--stats', action='store_true',
                        help='현재 DB 통계만 출력')
    parser.add_argument('--rebuild-index', action='store_true',
                        help='벡터 인덱스 재구축')
    args = parser.parse_args()

    if args.stats:
        print_stats()
        return

    if args.rebuild_index:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        result = db.rebuild_index()
        print(f"인덱스 재구축: {result}")
        return

    stages = [int(s.strip()) for s in args.stages.split(',')]
    result = generate_all(stages)
    print(f"\n결과: {result}")
    print_stats()


if __name__ == '__main__':
    main()
