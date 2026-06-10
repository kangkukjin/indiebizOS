"""NIP-44 v2 공식 테스트 벡터 검증.

벡터: https://github.com/paulmillr/nip44 (nip44.vectors.json) — testdata/에 vendoring.
사용: python3 test_nip44_vectors.py   (기본 testdata/nip44_vectors.json)
"""
import hashlib
import json
import os
import sys

import nip44
from pynostr.key import PrivateKey


def _pub_of(sec_hex):
    return PrivateKey.from_hex(sec_hex).public_key.hex()


def run(vectors_path):
    d = json.load(open(vectors_path))
    v2 = d["v2"]
    valid = v2["valid"]
    invalid = v2["invalid"]
    passed = failed = 0
    fails = []

    def check(cond, label):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            fails.append(label)

    # 1) calc_padded_len
    for unpadded, expected in valid["calc_padded_len"]:
        check(nip44._calc_padded_len(unpadded) == expected, f"calc_padded_len({unpadded})")

    # 2) get_conversation_key
    for i, tv in enumerate(valid["get_conversation_key"]):
        try:
            ck = nip44.get_conversation_key(tv["sec1"], tv["pub2"]).hex()
            check(ck == tv["conversation_key"], f"get_conversation_key[{i}]")
        except Exception as e:
            check(False, f"get_conversation_key[{i}] 예외: {e}")

    # 3) get_message_keys
    gmk = valid["get_message_keys"]
    ck = bytes.fromhex(gmk["conversation_key"])
    for i, tv in enumerate(gmk["keys"]):
        try:
            chacha_key, chacha_nonce, hmac_key = nip44._message_keys(ck, bytes.fromhex(tv["nonce"]))
            ok = (chacha_key.hex() == tv["chacha_key"] and
                  chacha_nonce.hex() == tv["chacha_nonce"] and
                  hmac_key.hex() == tv["hmac_key"])
            check(ok, f"get_message_keys[{i}]")
        except Exception as e:
            check(False, f"get_message_keys[{i}] 예외: {e}")

    # 4) encrypt_decrypt (payload 정확 일치 + 왕복)
    for i, tv in enumerate(valid["encrypt_decrypt"]):
        try:
            ck = nip44.get_conversation_key(tv["sec1"], _pub_of(tv["sec2"]))
            check(ck.hex() == tv["conversation_key"], f"encrypt_decrypt[{i}] 대화키")
            payload = nip44.encrypt(tv["plaintext"], ck, bytes.fromhex(tv["nonce"]))
            check(payload == tv["payload"], f"encrypt_decrypt[{i}] payload")
            check(nip44.decrypt(tv["payload"], ck) == tv["plaintext"], f"encrypt_decrypt[{i}] 복호")
        except Exception as e:
            check(False, f"encrypt_decrypt[{i}] 예외: {e}")

    # 5) encrypt_decrypt_long_msg (sha256로 검증)
    for i, tv in enumerate(valid["encrypt_decrypt_long_msg"]):
        try:
            ck = bytes.fromhex(tv["conversation_key"])
            plaintext = tv["pattern"] * tv["repeat"]
            check(hashlib.sha256(plaintext.encode()).hexdigest() == tv["plaintext_sha256"],
                  f"long_msg[{i}] 평문해시")
            payload = nip44.encrypt(plaintext, ck, bytes.fromhex(tv["nonce"]))
            check(hashlib.sha256(payload.encode()).hexdigest() == tv["payload_sha256"],
                  f"long_msg[{i}] payload해시")
            check(nip44.decrypt(payload, ck) == plaintext, f"long_msg[{i}] 복호")
        except Exception as e:
            check(False, f"long_msg[{i}] 예외: {e}")

    # 6) invalid/decrypt — 반드시 예외 발생해야 통과
    for i, tv in enumerate(invalid.get("decrypt", [])):
        try:
            ck = bytes.fromhex(tv["conversation_key"])
            nip44.decrypt(tv["payload"], ck)
            check(False, f"invalid_decrypt[{i}] (예외 안 남: {tv.get('note','')})")
        except Exception:
            check(True, f"invalid_decrypt[{i}]")

    # 7) invalid/get_conversation_key — 예외 발생해야 통과
    for i, tv in enumerate(invalid.get("get_conversation_key", [])):
        try:
            nip44.get_conversation_key(tv["sec1"], tv["pub2"])
            check(False, f"invalid_conv_key[{i}] (예외 안 남)")
        except Exception:
            check(True, f"invalid_conv_key[{i}]")

    print(f"\n{'='*50}")
    print(f"통과: {passed} / 실패: {failed}")
    if fails:
        print("실패 항목:")
        for f in fails[:30]:
            print("  ✗", f)
    else:
        print("✅ 전체 공식 테스트 벡터 통과")
    return failed == 0


if __name__ == "__main__":
    default = os.path.join(os.path.dirname(__file__), "testdata", "nip44_vectors.json")
    path = sys.argv[1] if len(sys.argv) > 1 else default
    sys.exit(0 if run(path) else 1)
