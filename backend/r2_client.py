"""
backend/r2_client.py — Cloudflare R2 업로드(S3 호환 API, AWS SigV4 v4 서명).

R2 객체 데이터 조작(PUT/GET/DELETE)은 Cloudflare REST API 가 아니라 S3 호환 API 로만
열려 있다(공식 문서: "Object Read & Write 권한은 S3 호환 API 전용"). 그래서 cf_api
(REST) 로는 못 하고, 여기서 requests + SigV4 로 직접 서명한다(boto3 의존성 회피).

자격증명(선생님이 R2 대시보드 "Manage R2 API Tokens" 에서 발급):
  R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY  (.env)
계정 ID 는 CLOUDFLARE_ACCOUNT_ID 재사용. 엔드포인트=https://<acct>.r2.cloudflarestorage.com
region 은 R2 에서 항상 "auto".

서명 정확성은 하단 _selftest() 가 AWS 공식 SigV4 테스트 벡터로 검증(R2 없이도 확인).
"""

import os
import hmac
import hashlib
from urllib.parse import urlparse, quote


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, datestamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), datestamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def sigv4_authorization(method: str, url: str, headers_to_sign: dict, payload_hash: str,
                        access_key: str, secret_key: str, region: str, service: str,
                        amz_date: str) -> str:
    """정규 요청→string-to-sign→서명→Authorization 헤더 값. (query 서명 미포함=단순 PUT/GET.)

    headers_to_sign: 서명 대상 헤더(소문자 키). host·x-amz-date 필수, S3 는 x-amz-content-sha256 도.
    payload_hash: 본문 SHA256 hex. amz_date: 'YYYYMMDDTHHMMSSZ'.
    """
    p = urlparse(url)
    # ★이중 인코딩 금지: 호출자가 이미 quote 한 URL 을 넘기므로 p.path 를 그대로 쓴다.
    # (여기서 다시 quote 하면 %XX→%25XX 가 되어 실제 요청 경로와 어긋나 SignatureDoesNotMatch.)
    canonical_uri = p.path or "/"
    canonical_qs = ""
    signed_headers = ";".join(sorted(headers_to_sign))
    canonical_headers = "".join(f"{k}:{headers_to_sign[k]}\n" for k in sorted(headers_to_sign))
    canonical_request = "\n".join([
        method, canonical_uri, canonical_qs, canonical_headers, signed_headers, payload_hash,
    ])
    datestamp = amz_date[:8]
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    signing_key = _signing_key(secret_key, datestamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}")


# === R2 자격증명·엔드포인트 ===

def _env(name: str) -> str:
    """os.environ 우선, 없으면 .env 파일 직접 파싱(백엔드 재시작 없이 반영)."""
    v = os.environ.get(name, "")
    if v:
        return v
    for envp in (_ROOT() / ".env", _ROOT() / "backend" / ".env"):
        if envp.exists():
            try:
                for line in envp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    return ""


def _ROOT():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent


def credentials() -> dict:
    return {
        "access_key": _env("R2_ACCESS_KEY_ID"),
        "secret_key": _env("R2_SECRET_ACCESS_KEY"),
        "account_id": _env("CLOUDFLARE_ACCOUNT_ID"),
    }


def is_configured() -> bool:
    c = credentials()
    return bool(c["access_key"] and c["secret_key"] and c["account_id"])


def _now_amz() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


_CT = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    "gif": "image/gif", "json": "application/json", "mp4": "video/mp4", "webm": "video/webm",
    "mov": "video/quicktime", "m4v": "video/x-m4v", "mkv": "video/x-matroska", "html": "text/html",
}


def content_type(key: str) -> str:
    return _CT.get(key.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def put_object(bucket: str, key: str, data: bytes, ctype: str = None) -> tuple:
    """R2 에 객체 업로드. (ok: bool, msg: str) 반환. requests 필요."""
    import requests
    c = credentials()
    if not (c["access_key"] and c["secret_key"] and c["account_id"]):
        return False, "R2 자격증명 미설정 (.env: R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY)"
    host = f"{c['account_id']}.r2.cloudflarestorage.com"
    key_path = quote(key, safe="/~")
    url = f"https://{host}/{bucket}/{key_path}"
    amz_date = _now_amz()
    payload_hash = hashlib.sha256(data).hexdigest()
    ctype = ctype or content_type(key)
    sign_headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    auth = sigv4_authorization("PUT", url, sign_headers, payload_hash,
                               c["access_key"], c["secret_key"], "auto", "s3", amz_date)
    headers = {
        "Authorization": auth,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "Content-Type": ctype,
    }
    try:
        r = requests.put(url, data=data, headers=headers, timeout=60)
        if r.status_code in (200, 201):
            return True, "ok"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"업로드 오류: {e}"


def delete_object(bucket: str, key: str) -> tuple:
    """R2 객체 삭제. (ok, msg)."""
    import requests
    c = credentials()
    if not (c["access_key"] and c["secret_key"] and c["account_id"]):
        return False, "R2 자격증명 미설정"
    host = f"{c['account_id']}.r2.cloudflarestorage.com"
    url = f"https://{host}/{bucket}/{quote(key, safe='/~')}"
    amz_date = _now_amz()
    empty_hash = hashlib.sha256(b"").hexdigest()
    sign_headers = {"host": host, "x-amz-content-sha256": empty_hash, "x-amz-date": amz_date}
    auth = sigv4_authorization("DELETE", url, sign_headers, empty_hash,
                               c["access_key"], c["secret_key"], "auto", "s3", amz_date)
    try:
        r = requests.delete(url, headers={
            "Authorization": auth, "x-amz-content-sha256": empty_hash, "x-amz-date": amz_date,
        }, timeout=30)
        return (r.status_code in (200, 204), f"HTTP {r.status_code}")
    except Exception as e:
        return False, f"삭제 오류: {e}"


def get_object(bucket: str, key: str) -> tuple:
    """R2 객체 조회 — 존재 확인용. (ok, bytes_or_msg)."""
    import requests
    c = credentials()
    host = f"{c['account_id']}.r2.cloudflarestorage.com"
    url = f"https://{host}/{bucket}/{quote(key, safe='/~')}"
    amz_date = _now_amz()
    empty_hash = hashlib.sha256(b"").hexdigest()
    sign_headers = {"host": host, "x-amz-content-sha256": empty_hash, "x-amz-date": amz_date}
    auth = sigv4_authorization("GET", url, sign_headers, empty_hash,
                               c["access_key"], c["secret_key"], "auto", "s3", amz_date)
    try:
        r = requests.get(url, headers={
            "Authorization": auth, "x-amz-content-sha256": empty_hash, "x-amz-date": amz_date,
        }, timeout=30)
        return (r.status_code == 200, r.content if r.status_code == 200 else f"HTTP {r.status_code}")
    except Exception as e:
        return False, f"조회 오류: {e}"


def _selftest() -> bool:
    """AWS 공식 SigV4 테스트 벡터(get-vanilla)로 서명 로직 검증 — R2 없이도 정확성 확인."""
    access = "AKIDEXAMPLE"
    secret = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
    amz_date = "20150830T123600Z"
    url = "https://example.amazonaws.com/"
    headers = {"host": "example.amazonaws.com", "x-amz-date": amz_date}
    empty_hash = hashlib.sha256(b"").hexdigest()
    auth = sigv4_authorization("GET", url, headers, empty_hash,
                               access, secret, "us-east-1", "service", amz_date)
    expected = "5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"
    got = auth.rsplit("Signature=", 1)[-1]
    return got == expected


if __name__ == "__main__":
    print("SigV4 self-test:", "PASS" if _selftest() else "FAIL")
    print("R2 configured:", is_configured())
