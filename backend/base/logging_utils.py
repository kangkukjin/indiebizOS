"""
logging_utils.py - 로깅 유틸리티
IndieBiz OS Core

구조화된 로깅과 민감 정보 마스킹을 제공합니다.
"""

import logging
import re
from typing import Any, Optional
from functools import wraps
import os

# ============ 로깅 설정 ============

# 로그 레벨 (환경변수로 설정 가능)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# 프로덕션 모드 (민감 정보 마스킹 활성화)
PRODUCTION_MODE = os.environ.get("PRODUCTION_MODE", "false").lower() == "true"

# 로거 생성
def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 생성"""
    logger = logging.getLogger(f"indiebiz.{name}")

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    return logger


# ============ 민감 정보 마스킹 ============

# 마스킹할 패턴 정의
SENSITIVE_PATTERNS = [
    # API 키
    (r'(sk-[a-zA-Z0-9]{20,})', r'sk-****'),
    (r'(api[_-]?key["\s:=]+)["\']?([a-zA-Z0-9_-]{20,})["\']?', r'\1****'),

    # 이메일
    (r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'****@\2'),

    # 전화번호 (한국)
    (r'(010[-\s]?\d{4})[-\s]?\d{4}', r'\1-****'),

    # 비밀번호 필드
    (r'(password["\s:=]+)["\']?[^"\s,}]+["\']?', r'\1****'),
    (r'(secret["\s:=]+)["\']?[^"\s,}]+["\']?', r'\1****'),

    # 토큰
    (r'(token["\s:=]+)["\']?([a-zA-Z0-9_.-]{20,})["\']?', r'\1****'),

    # Nostr 개인키
    (r'(nsec1[a-z0-9]{58})', r'nsec1****'),
    (r'(private_key["\s:=]+)["\']?([a-f0-9]{64})["\']?', r'\1****'),
]

def mask_sensitive(text: str) -> str:
    """
    민감 정보 마스킹

    Args:
        text: 마스킹할 텍스트

    Returns:
        마스킹된 텍스트
    """
    if not PRODUCTION_MODE:
        return text

    if not isinstance(text, str):
        text = str(text)

    for pattern, replacement in SENSITIVE_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


# ============ 비밀(secret) 마스킹 — 영속 로그용, 항상 적용 ============
# mask_sensitive 와 별개: 저건 PRODUCTION_MODE 게이트 + PII(이메일·전화)까지 가리는
# 콘솔 로그용이고, 이건 DB 등 디스크에 영속되는 로그에서 자격증명만 무조건 가린다.
# (에피소드 로그에 [self:read]로 읽은 설정 파일의 apiKey 가 평문 박제된 사고의 재발 방지)

# 필드명 기반: "apiKey": "...", api_key=..., authKey: ... 등 — 값 전체를 가림
_SECRET_FIELD_RE = re.compile(
    r'("?(?:api[_-]?key|auth[_-]?key|access[_-]?token|refresh[_-]?token|'
    r'client[_-]?secret|private[_-]?key|token|secret|password|passwd)"?\s*[:=]\s*)'
    r'(["\']?)([^"\'\s,}{\]\[]{8,})\2',
    re.IGNORECASE,
)

# 값 형식 기반: 필드명 없이도 형태만으로 자격증명임이 확실한 토큰들
_SECRET_TOKEN_RES = [re.compile(p) for p in (
    r'AIza[0-9A-Za-z_-]{35}',                       # Google API 키
    r'sk-[A-Za-z0-9_-]{20,}',                       # OpenAI/Anthropic 류
    r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}',    # GitHub 토큰
    r'github_pat_[A-Za-z0-9_]{20,}',
    r'xox[baprs]-[A-Za-z0-9-]{10,}',                # Slack
    r'ya29\.[0-9A-Za-z_-]{20,}',                    # Google OAuth
    r'AKIA[0-9A-Z]{16}',                            # AWS Access Key ID
    r'nsec1[a-z0-9]{58}',                           # Nostr 개인키
    r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',  # JWT
    r'vc[apsu]_[A-Za-z0-9]{20,}',                   # Vercel (vcp_ 개인/vca_/vcs_)
    r'npm_[A-Za-z0-9]{30,}',                        # npm
    r'hf_[A-Za-z0-9]{30,}',                         # HuggingFace
    r'glpat-[A-Za-z0-9_-]{16,}',                    # GitLab PAT
    r'dop_v1_[a-f0-9]{40,}',                        # DigitalOcean
    r'[sr]k_(?:live|test)_[A-Za-z0-9]{20,}',        # Stripe
    r'\b\d{8,10}:AA[A-Za-z0-9_-]{30,}',              # Telegram 봇 토큰
)]

# ─── 근접 규칙: 이름 옆에 붙은 '값처럼 생긴 것' ────────────────────────────────
# ★왜 접두 목록만으로는 못 막나(2026-08-30, ep2426 실측): 새는 자리는 `key=value` 도
# 벤더 접두도 아니었다. `echo "token set: ${VERCEL_TOKEN:+yes}${VERCEL_TOKEN:-no}"` —
# `:-` 는 변수가 있을 때 **값을 내놓는다**. 그래서 "token set: yes<60자토큰>" 이 그대로
# 박제됐다. 벤더 목록은 다음 벤더에서 또 샌다(=손으로 고른 스윕). 그래서 부류로 막는다:
# 자격증명 낱말 근처의 고엔트로피 덩어리는 문장 모양과 무관하게 가린다.
_SECRET_NEAR_RE = re.compile(
    r'(?i)\b(?:token|secret|api[_-]?key|apikey|password|passwd|credential|bearer)\b'
    r'[^\n]{0,24}?([A-Za-z0-9_\-]{24,})'
)


def _looks_like_credential(blob: str) -> bool:
    """영문+숫자가 섞이고 엔트로피가 높은 덩어리인가 — 경로·문장·id 오탐을 줄인다."""
    if not (re.search(r'[A-Za-z]', blob) and re.search(r'\d', blob)):
        return False
    from collections import Counter
    import math
    n = len(blob)
    ent = -sum((v / n) * math.log2(v / n) for v in Counter(blob).values())
    return ent >= 3.5


def mask_secrets(text: str) -> str:
    """디스크에 영속될 텍스트에서 자격증명을 마스킹한다. PRODUCTION_MODE 무관 항상 적용.

    세 층이다: ①필드명 매칭(값 전체 ****) ②벤더 접두 형식 매칭 ③이름 근접 +
    고엔트로피 매칭. ②③은 식별용 접두 4자만 남긴다."""
    if not text:
        return text
    if not isinstance(text, str):
        text = str(text)
    text = _SECRET_FIELD_RE.sub(r'\1\2****\2', text)
    for token_re in _SECRET_TOKEN_RES:
        text = token_re.sub(lambda m: m.group(0)[:4] + '****', text)

    def _near(m):
        blob = m.group(1)
        if not _looks_like_credential(blob):
            return m.group(0)
        return m.group(0).replace(blob, blob[:4] + '****')

    return _SECRET_NEAR_RE.sub(_near, text)


def truncate_content(content: str, max_length: int = 100) -> str:
    """
    긴 내용 자르기 (로그용)

    Args:
        content: 자를 내용
        max_length: 최대 길이

    Returns:
        잘린 내용
    """
    if not content:
        return ""

    content = str(content)
    if len(content) <= max_length:
        return content

    return content[:max_length] + f"... ({len(content)} chars)"


# ============ 로그 헬퍼 ============

def safe_log(logger: logging.Logger, level: str, message: str, **kwargs):
    """
    안전한 로깅 (민감 정보 마스킹 적용)

    Args:
        logger: 로거 인스턴스
        level: 로그 레벨 (debug, info, warning, error)
        message: 로그 메시지
        **kwargs: 추가 컨텍스트 (마스킹 적용됨)
    """
    # 메시지 마스킹
    masked_message = mask_sensitive(message)

    # kwargs 마스킹
    masked_kwargs = {}
    for key, value in kwargs.items():
        if value is not None:
            masked_kwargs[key] = mask_sensitive(str(value))

    # 컨텍스트 포맷팅
    if masked_kwargs:
        context = " | ".join(f"{k}={v}" for k, v in masked_kwargs.items())
        full_message = f"{masked_message} | {context}"
    else:
        full_message = masked_message

    # 로그 출력
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(full_message)


# ============ 로그 데코레이터 ============

def log_function_call(logger: logging.Logger):
    """
    함수 호출 로깅 데코레이터

    사용법:
        @log_function_call(get_logger("module"))
        def my_function(arg1, arg2):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__

            # 인자 로깅 (민감 정보 마스킹)
            args_str = truncate_content(str(args), 50) if args else ""
            kwargs_str = truncate_content(str(kwargs), 50) if kwargs else ""

            logger.debug(f"{func_name} 호출 | args={mask_sensitive(args_str)} kwargs={mask_sensitive(kwargs_str)}")

            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func_name} 완료")
                return result
            except Exception as e:
                logger.error(f"{func_name} 실패: {mask_sensitive(str(e))}")
                raise

        return wrapper
    return decorator


# ============ 레거시 print 대체 ============

class SafePrint:
    """
    print 대체용 안전한 출력 클래스

    사용법:
        from logging_utils import safe_print
        safe_print("[모듈] 메시지", sensitive_data)
    """

    def __init__(self):
        self._logger = get_logger("print")

    def __call__(self, *args, **kwargs):
        """print() 호출 대체"""
        message = " ".join(str(arg) for arg in args)
        masked = mask_sensitive(message)

        # 원본 print도 호출 (개발 환경에서는 유용)
        if not PRODUCTION_MODE:
            print(masked)
        else:
            self._logger.info(masked)


# 싱글톤 인스턴스
safe_print = SafePrint()


# ============ 사용 예시 ============

if __name__ == "__main__":
    # 테스트
    logger = get_logger("test")

    # 민감 정보 마스킹 테스트
    test_data = """
    API Key: sk-1234567890abcdefghijklmnop
    Email: user@example.com
    Phone: 010-1234-5678
    Password: mypassword123
    Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
    """

    print("=== 원본 ===")
    print(test_data)

    print("\n=== 마스킹 (PRODUCTION_MODE=true) ===")
    # 임시로 프로덕션 모드 활성화
    import logging_utils
    logging_utils.PRODUCTION_MODE = True
    print(mask_sensitive(test_data))
