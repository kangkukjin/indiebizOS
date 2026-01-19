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
