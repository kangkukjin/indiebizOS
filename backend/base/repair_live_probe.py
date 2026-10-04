"""활성 검사에만 제공하는 운영 서버의 제한된 읽기 통로."""
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.parse import urlsplit


# GET이라도 동작을 일으키는 API가 있으므로 명시된 읽기 표면만 제공한다.
READ_PATHS = frozenset({"/health", "/xray/app", "/launcher/app"})
ENVIRONMENT_VERSION = 2


@contextmanager
def live_probe(upstream_port=8765):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in READ_PATHS or urlsplit(self.path).netloc:
                self.send_error(403)
                return
            connection = HTTPConnection("127.0.0.1", upstream_port, timeout=10)
            try:
                connection.request("GET", self.path)
                response = connection.getresponse()
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024 or 300 <= response.status < 400:
                    self.send_error(502)
                    return
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_error(503, "Live verification upstream unavailable")
            finally:
                connection.close()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def failure_kind(output, exit_code):
    if exit_code == 0:
        return None
    # 기능 assertion 실패는 모델에게 전달하되, 실행 환경 장애는 개발과 분리한다.
    signatures = ("sandbox_apply: Operation not permitted", "<urlopen error [Errno 1] Operation not permitted>",
                  "Live verification upstream unavailable", "Executable doesn't exist at")
    return "environment" if any(value in output for value in signatures) else "check"
