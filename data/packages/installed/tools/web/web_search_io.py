"""검색 수신의 시간·크기 제한과 배치의 부분 실패 보존."""
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait

SOCKET_TIMEOUT = 5
REQUEST_SECONDS = 20
BATCH_SECONDS = 45
MAX_BYTES = 5 * 1024 * 1024


def query_notes(args):
    """의심스러운 site 표기만 안내한다. 원 검색어·범위·성공 상태는 바꾸지 않는다."""
    queries = args.get("queries") or [args.get("query", "")]
    if isinstance(queries, str):
        queries = re.split(r"[,\n]", queries)
    if not isinstance(queries, (list, tuple)):
        return []
    notes = []
    for query in queries:
        if not isinstance(query, str):
            continue
        match = re.match(r"^\s*(site\d*\.[a-z0-9.-]+)(?=\s|$)", query, re.I)
        if match:
            note = {"code": "POSSIBLE_SITE_OPERATOR_TYPO", "query": query,
                    "token": match[1],
                    "hint": "이 표기는 site: 도메인 제한 연산자가 아닙니다. 도메인 제한을 의도했다면 실제 주소를 확인해 site:example.org 검색어로 고치세요. 일반 검색어라면 결과를 그대로 사용하세요. 자동 수정하지 않았습니다."}
            if match[1].lower().startswith('site.'):
                note['suggested_query'] = (query[:match.start(1)] + 'site:' +
                                           match[1][5:] + query[match.end(1):])
                note['suggestion_condition'] = 'site. 뒤의 문자열이 의도한 실제 도메인일 때만 사용'
            notes.append(note)
    return notes


def download(url):
    """연결/읽기 5초, 수신 경과 20초. 실패를 빈 데이터로 바꾸지 않는다."""
    started = time.monotonic()
    request = urllib.request.Request(url, headers={
        'User-Agent': 'IndieBiz/1.0', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(request, timeout=SOCKET_TIMEOUT) as response:
        chunks, size = [], 0
        # read1은 한 번의 버퍼/소켓 읽기만 수행해, 느린 스트림도 경과 시간을 확인한다.
        while True:
            if time.monotonic() - started >= REQUEST_SECONDS:
                raise TimeoutError('검색 응답 수신 시간 초과')
            chunk = response.read1(64 * 1024)
            if time.monotonic() - started >= REQUEST_SECONDS:
                raise TimeoutError('검색 응답 수신 시간 초과')
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('검색 응답이 5 MiB 제한을 초과했습니다')
            chunks.append(chunk)
        return b''.join(chunks), dict(response.headers), response.geturl()


def read_feed(url, parser):
    raw, headers, final_url = download(url)
    headers = {k.lower(): v for k, v in headers.items()}
    headers['content-location'] = final_url
    return parser.parse(raw, response_headers=headers)


def read_json(url):
    raw, _, _ = download(url)
    return json.loads(raw)


def fetch_sections(jobs, timeout=None):
    """입력 순서를 보존하고 미완료·예외를 섹션별 error로 반환한다."""
    if not jobs:
        return []
    if timeout is None:
        timeout = BATCH_SECONDS
    executor = ThreadPoolExecutor(max_workers=min(8, len(jobs)))
    futures = []
    try:
        futures = [executor.submit(fetch) for _, fetch in jobs]
        done, _ = wait(futures, timeout=timeout)
        results = []
        for future in futures:
            if future not in done:
                future.cancel()
                results.append({'items': [], 'error': '검색 배치 시간 초과'})
                continue
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({'items': [], 'error': f'검색 실패: {exc}'})
        return results
    finally:
        # 아직 실행 전인 요청을 회수한다. 실행 중 수신도 download의 제한으로 종료된다.
        executor.shutdown(wait=False, cancel_futures=True)
