"""
korean_utils.py - 한국어 텍스트 정규화 유틸리티

IBL의 discover, RAG 등 여러 모듈에서 공통으로 사용하는
한국어 조사 제거 및 복합어 분리 기능.
"""

import re
from typing import List

# 한국어 조사 목록 (길이 역순으로 정렬하여 "에서"를 "에"보다 먼저 매칭)
_KO_PARTICLES = sorted([
    '에서', '으로', '에게', '한테', '께서', '부터', '까지', '처럼', '만큼',
    '이라', '라고', '이나', '에는',
    '이라는', '에서는', '으로는', '에서의', '으로의',
    '하는', '되는', '하고', '해서', '해줘', '할까', '인지',
    '이랑', '하면', '와는',
    '을', '를', '이', '가', '은', '는', '의', '로', '와', '과',
    '도', '에', '서', '다', '요', '나', '랑', '만', '야',
], key=len, reverse=True)


def strip_particle(word: str) -> str:
    """단일 단어에서 한국어 조사/어미 제거.

    "건강기록에서" → "건강기록"
    "결과를"       → "결과"
    """
    for p in _KO_PARTICLES:
        if word.endswith(p) and len(word) > len(p) + 1:
            return word[:-len(p)]
    return word


def split_compound(word: str) -> List[str]:
    """한글 복합어를 가능한 모든 위치에서 2글자 이상으로 분리.

    "건강기록"   → ["건강", "기록"]
    "혈액검사"   → ["혈액", "검사"]
    "동영상제작" → ["동영상", "제작", "동영", "상제작"]  (2글자 미만 제외)
    "검사"       → []  (4글자 미만이면 분리 안 함)

    모든 분할 위치에서 양쪽 모두 2글자 이상인 조합만 반환.
    """
    if len(word) < 4:
        return []
    if not all('\uac00' <= c <= '\ud7a3' for c in word):
        return []
    parts = set()
    for i in range(2, len(word) - 1):  # 양쪽 최소 2글자
        left, right = word[:i], word[i:]
        if len(left) >= 2 and len(right) >= 2:
            parts.add(left)
            parts.add(right)
    return list(parts)


def normalize_korean_tokens(raw_tokens: List[str]) -> List[str]:
    """한국어 토큰 정규화: 조사 제거 + 복합어 분리

    ["건강기록에서", "결과를", "혈액검사"]
    → ["건강기록", "건강", "기록", "결과", "혈액검사", "혈액", "검사"]
    """
    result = set()
    for token in raw_tokens:
        stripped = strip_particle(token)
        result.add(stripped)
        for part in split_compound(stripped):
            result.add(part)
    return list(result)


def tokenize_korean(text: str) -> List[str]:
    """텍스트를 한국어 정규화된 토큰 리스트로 변환.

    "혈액검사 결과를 건강기록에서 찾아줘"
    → ["혈액검사", "혈액", "검사", "결과", "건강기록", "건강", "기록", "찾아줘"]
    """
    safe = re.sub(r'[^\w\s가-힣]', ' ', text.lower())
    raw_tokens = [t for t in safe.split() if len(t) >= 2]
    return normalize_korean_tokens(raw_tokens)
