"""외부 클라이언트 공개 웹 조사. 쿠키·주인 브라우저·파일·개인 관점 캐시를 사용하지 않는다."""
import http.client
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_BYTES = 2 * 1024 * 1024


def public_address(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('공개 HTTP(S) 주소만 읽을 수 있습니다')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if port not in (80, 443):
        raise ValueError('웹 표준 포트만 읽을 수 있습니다')
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('내부 네트워크 주소는 읽을 수 없습니다')
    return parsed, port, addresses[0]


def fetch_public(url):
    """검사한 IP에 직접 접속. 리다이렉트마다 재검사하며 DNS 재해석·프록시를 사용하지 않는다."""
    deadline = time.monotonic() + 45
    for _ in range(6):
        parsed, port, address = public_address(url)
        sock = socket.socket(address[0], address[1], address[2])
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=15)
        try:
            sock.settimeout(15)
            sock.connect(address[4])
            if parsed.scheme == 'https':
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
            connection.sock = sock
            path = urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
            connection.request('GET', path, headers={'User-Agent': 'IndieBiz-Client/1.0', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('리다이렉트 주소 없음')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f'공개 페이지 응답: HTTP {response.status}')
            mime = response.getheader('Content-Type', '')
            if not any(t in mime.lower() for t in ('text/', 'application/xhtml', 'application/json', 'application/xml')):  # vj-ok: HTTP Content-Type 프로토콜 이름 비교
                raise ValueError('공개 텍스트 페이지만 지원합니다')
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('공개 페이지 읽기 시간 제한')
                sock.settimeout(min(15, remaining))
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('페이지가 2MB 제한을 초과합니다')
            data = b''.join(chunks)
            return url, data, mime
        finally:
            connection.close()
            sock.close()
    raise ValueError('리다이렉트 상한 초과')


def execute(name, args):
    try:
        if name == 'search':
            if args.get('source', 'ddg') != 'ddg' or args.get('curate') or args.get('queries'):
                raise ValueError('외부사용자 검색은 source:ddg 단일 질의를 지원합니다')
            query = str(args.get('query') or '').strip()
            if not query or len(query) > 1000:
                raise ValueError('검색어는 1~1000자여야 합니다')
            requested = int(args.get('limit', args.get('count', 5)) or 5)
            if not 1 <= requested <= 10:
                raise ValueError('검색 건수는 1~10이어야 합니다')
            from ddgs import DDGS
            from contextvars import copy_context
            # 라이브러리의 전역 분산 캐시를 사용하지 않고 내부 검색 워커에도 회원 문맥을 보존한다.
            class PrivateSearch(DDGS):
                def _get_network_client(self):
                    return None

                def _get_engines(self, *a, **kw):
                    engines = super()._get_engines(*a, **kw)
                    for engine in engines:
                        original, context = engine.search, copy_context()
                        engine.search = lambda *a, _f=original, _c=context, **kw: _c.copy().run(_f, *a, **kw)
                    return engines
            search = PrivateSearch(timeout=15)
            search._proxy = None
            rows = search.text(query, max_results=requested, safesearch='moderate')
            items = [{'title': str(r.get('title', '')), 'url': str(r.get('href', '')),
                      'summary': str(r.get('body', ''))} for r in rows]
            return {'success': True, 'items': items, 'query': query,
                    'message': '검색 요약입니다. 사실 확인에는 sense:crawl로 원문을 읽으세요.'}
        if name == 'crawl_website':
            url, data, mime = fetch_public(str(args.get('url') or ''))
            from bs4 import BeautifulSoup
            page = BeautifulSoup(data, 'html.parser')
            for element in page(['script', 'style', 'nav', 'footer', 'noscript']):
                element.decompose()
            content = page.get_text('\n', strip=True)
            limit = int(args.get('max_length') or 24000)
            if not 1 <= limit <= 60000:
                raise ValueError('본문 한도는 1~60000자입니다')
            return {'success': True, 'url': url, 'title': page.title.get_text() if page.title else '',
                    'items': [{'type': 'paragraph', 'text': content[:limit]}],
                    'truncated': len(content) > limit, 'total_chars': len(content)}
        raise ValueError('외부사용자용 웹 기능이 아닙니다')
    except Exception as exc:
        # 원문·세션·시스템 경로가 섞일 수 있는 예외를 반환하거나 기록하지 않는다.
        return {'success': False, 'error_type': type(exc).__name__,
                'error': str(exc) if isinstance(exc, ValueError) else '공개 웹 조사에 실패했습니다'}
