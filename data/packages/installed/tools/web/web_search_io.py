"""검색 수신의 시간·크기 제한과 배치의 부분 실패 보존."""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait

SOCKET_TIMEOUT = 5
REQUEST_SECONDS = 20
BATCH_SECONDS = 45
MAX_BYTES = 5 * 1024 * 1024


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
