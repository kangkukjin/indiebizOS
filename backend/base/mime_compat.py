"""임베디드 파이썬(윈도우 몸)의 mimetypes 구멍 보강 — 프로세스 전역, 부팅 시 1회.

posix 는 /etc/apache2/mime.types 같은 시스템 사전을 추가로 읽어 .md 등을 잡지만,
윈도우 임베디드 파이썬은 표준 딕셔너리+레지스트리에만 의존한다. `.md → text/markdown`
은 파이썬 3.13 에야 표준 매핑에 합류했고 윈도우 레지스트리에도 없어, 3.11 임베디드에선
guess_type 이 None → "application/octet-stream" → 브라우저가 문서를 렌더 대신
다운로드로 처리한다(v1.3.5 윈도우 실측: 창고의 비즈니스문서.md).

mimetypes 레지스트리는 프로세스 전역이므로 api.py 가 이 모듈을 임포트하는 것만으로
모든 guess_type 호출부(포털·NAS·런처·lecture·패키지)가 같은 답을 얻는다.
add_type 은 이미 매핑이 있는 플랫폼에서도 무해(멱등 덮어쓰기)라 맥·윈도우가 같은
코드로 같은 결과를 낸다 — 로케일 함정과 같은 계열의 "임베디드 환경 차이" 봉합.
"""
import mimetypes

# 표시(브라우저 열람) 친화를 우선한 보강 목록 — 텍스트 계열은 text/* 여야
# 브라우저가 열고, application/* 로 두면 정확해도 다운로드가 된다.
_EXTRA_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".toml": "text/plain",     # 공식 application/toml 은 브라우저가 다운로드해버린다
    ".log": "text/plain",
    ".webp": "image/webp",     # 3.11 표준 딕셔너리에 없음
    ".avif": "image/avif",
    ".heic": "image/heic",
    ".m4a": "audio/mp4",
}


def ensure_mime_types() -> None:
    """전역 mimetypes 레지스트리에 보강 매핑 주입 — 멱등."""
    for ext, ctype in _EXTRA_TYPES.items():
        mimetypes.add_type(ctype, ext)


ensure_mime_types()   # 임포트 = 보강 (api.py 부팅 시 한 번)
