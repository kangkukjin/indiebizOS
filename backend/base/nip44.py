"""NIP-44 v2 암호화 (ChaCha20 + HKDF-SHA256 + HMAC-SHA256).

NIP-04(AES-CBC)를 대체하는 현대 Nostr DM 암호화 1차 빌딩블록.
NIP-17(gift-wrap)이 이 모듈 위에 올라간다.

스펙: https://github.com/nostr-protocol/nips/blob/master/44.md
- 공유비밀: secp256k1 ECDH의 X좌표 32바이트 (pynostr.compute_shared_secret 재사용 — 표준 검증 완료)
- 대화키: hkdf_extract(salt="nip44-v2", ikm=shared_x)
- 메시지키: hkdf_expand(대화키, info=nonce32, L=76) → chacha_key32 | chacha_nonce12 | hmac_key32
- payload: base64( version(0x02) | nonce(32) | ciphertext | mac(32) )

암호 코드이므로 backend/test_nip44_vectors.py 로 공식 테스트 벡터를 통과해야 한다.
"""
import base64
import hashlib
import hmac
import math
import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms

VERSION = 2
_SALT = b"nip44-v2"


# ---------- HKDF (RFC 5869, SHA-256) ----------

def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    okm = b""
    t = b""
    i = 0
    while len(okm) < length:
        i += 1
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]


# ---------- ChaCha20 (RFC 7539, counter=0, 12바이트 nonce) ----------

def _chacha20(key: bytes, nonce12: bytes, data: bytes) -> bytes:
    # cryptography의 ChaCha20은 16바이트 nonce = 4바이트 카운터(LE) + 12바이트 nonce.
    # NIP-44는 카운터 0부터 시작.
    full_nonce = (0).to_bytes(4, "little") + nonce12
    cipher = Cipher(algorithms.ChaCha20(key, full_nonce), mode=None)
    return cipher.encryptor().update(data)


# ---------- 패딩 ----------

def _calc_padded_len(unpadded_len: int) -> int:
    if unpadded_len <= 0:
        raise ValueError("패딩: 길이는 1 이상이어야 함")
    if unpadded_len <= 32:
        return 32
    next_power = 1 << (math.floor(math.log2(unpadded_len - 1)) + 1)
    chunk = 32 if next_power <= 256 else next_power // 8
    return chunk * (math.floor((unpadded_len - 1) / chunk) + 1)


def _pad(plaintext: str) -> bytes:
    unpadded = plaintext.encode("utf-8")
    n = len(unpadded)
    if n < 1 or n > 65535:
        raise ValueError(f"평문 길이 범위 위반: {n} (1~65535)")
    prefix = n.to_bytes(2, "big")
    padded_len = _calc_padded_len(n)
    suffix = b"\x00" * (padded_len - n)
    return prefix + unpadded + suffix


def _unpad(padded: bytes) -> str:
    if len(padded) < 2:
        raise ValueError("언패딩: 데이터 너무 짧음")
    n = int.from_bytes(padded[:2], "big")
    plaintext = padded[2:2 + n]
    if n < 1 or n > 65535 or len(plaintext) != n:
        raise ValueError("언패딩: 길이 불일치")
    if len(padded) != 2 + _calc_padded_len(n):
        raise ValueError("언패딩: 패딩 길이 불일치")
    return plaintext.decode("utf-8")


# ---------- 대화키 ----------

def get_conversation_key(private_key_hex: str, public_key_hex: str) -> bytes:
    """ECDH X좌표(shared secret) → HKDF-extract(salt='nip44-v2') = 대화키 32바이트."""
    from pynostr.key import PrivateKey
    shared_x = PrivateKey.from_hex(private_key_hex).compute_shared_secret(public_key_hex)
    return _hkdf_extract(_SALT, shared_x)


def _message_keys(conversation_key: bytes, nonce: bytes):
    if len(conversation_key) != 32:
        raise ValueError("대화키는 32바이트")
    if len(nonce) != 32:
        raise ValueError("nonce는 32바이트")
    keys = _hkdf_expand(conversation_key, nonce, 76)
    return keys[0:32], keys[32:44], keys[44:76]  # chacha_key, chacha_nonce, hmac_key


# ---------- 암/복호 ----------

def encrypt(plaintext: str, conversation_key: bytes, nonce: bytes = None) -> str:
    """평문 → NIP-44 v2 payload(base64). nonce 미지정 시 무작위 32바이트."""
    if nonce is None:
        nonce = secrets.token_bytes(32)
    chacha_key, chacha_nonce, hmac_key = _message_keys(conversation_key, nonce)
    padded = _pad(plaintext)
    ciphertext = _chacha20(chacha_key, chacha_nonce, padded)
    mac = hmac.new(hmac_key, nonce + ciphertext, hashlib.sha256).digest()  # aad=nonce
    return base64.b64encode(bytes([VERSION]) + nonce + ciphertext + mac).decode()


def decrypt(payload: str, conversation_key: bytes) -> str:
    """NIP-44 v2 payload → 평문. MAC 불일치/버전 불일치 시 예외."""
    if not payload or payload[0] == "#":
        raise ValueError("지원하지 않는 payload(버전 #)")
    data = base64.b64decode(payload)
    if len(data) < 1 + 32 + 32:
        raise ValueError("payload 너무 짧음")
    version = data[0]
    if version != VERSION:
        raise ValueError(f"지원하지 않는 NIP-44 버전: {version}")
    nonce = data[1:33]
    mac = data[-32:]
    ciphertext = data[33:-32]
    chacha_key, chacha_nonce, hmac_key = _message_keys(conversation_key, nonce)
    expected_mac = hmac.new(hmac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("MAC 검증 실패")
    padded = _chacha20(chacha_key, chacha_nonce, ciphertext)
    return _unpad(padded)
