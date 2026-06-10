"""NIP-17 비공개 다이렉트 메시지 (NIP-59 gift-wrap 기반).

NIP-44 v2(nip44.py) 위에 올라가는 현대 Nostr DM. 3겹 구조:
  rumor(kind 14, 미서명 DM)
    → seal(kind 13, NIP-44로 암호화, 발신자 서명)
      → gift wrap(kind 1059, 임시키로 NIP-44 암호화·서명, #p=수신자)

수신자만 gift wrap을 풀 수 있고, 풀어야 발신자를 알 수 있어 메타데이터가 보호된다.
타임스탬프는 과거 2일 내 무작위로 흩뿌려 타이밍 누출을 막는다.

스펙: NIP-17 (https://github.com/nostr-protocol/nips/blob/master/17.md)
     NIP-59 (https://github.com/nostr-protocol/nips/blob/master/59.md)
"""
import json
import secrets
import time

import nip44
from pynostr.event import Event
from pynostr.key import PrivateKey

KIND_DM = 14
KIND_SEAL = 13
KIND_GIFT_WRAP = 1059
_TWO_DAYS = 2 * 24 * 3600


def _random_past_timestamp() -> int:
    """현재로부터 과거 2일 내 무작위 시각 (타이밍 누출 방지)."""
    return int(time.time()) - secrets.randbelow(_TWO_DAYS + 1)


def _make_rumor(sender_pub_hex: str, recipient_pub_hex: str,
                message: str, extra_tags=None) -> dict:
    """kind 14 rumor (미서명 이벤트, id만 계산)."""
    tags = [["p", recipient_pub_hex]]
    if extra_tags:
        tags.extend(extra_tags)
    rumor = Event(content=message, pubkey=sender_pub_hex, kind=KIND_DM,
                  tags=tags, created_at=int(time.time()))
    rumor.compute_id()
    d = rumor.to_dict()
    d.pop("sig", None)  # rumor는 서명하지 않는다
    return d


def wrap_dm(sender_priv_hex: str, recipient_pub_hex: str,
            message: str, extra_tags=None) -> dict:
    """평문 DM → 수신자에게 보낼 gift wrap(kind 1059) 이벤트 dict.

    이 dict를 수신자의 DM relay(kind:10050)들로 발행하면 된다.
    """
    sender_priv = PrivateKey.from_hex(sender_priv_hex)
    sender_pub_hex = sender_priv.public_key.hex()

    # 1) rumor (kind 14, 미서명)
    rumor = _make_rumor(sender_pub_hex, recipient_pub_hex, message, extra_tags)

    # 2) seal (kind 13): rumor를 발신자→수신자 NIP-44로 암호화, 발신자 서명
    seal_ck = nip44.get_conversation_key(sender_priv_hex, recipient_pub_hex)
    seal = Event(content=nip44.encrypt(json.dumps(rumor), seal_ck),
                 pubkey=sender_pub_hex, kind=KIND_SEAL, tags=[],
                 created_at=_random_past_timestamp())
    seal.sign(sender_priv_hex)
    seal_dict = seal.to_dict()

    # 3) gift wrap (kind 1059): 일회용 임시키로 seal을 NIP-44 암호화·서명, #p=수신자
    ephemeral = PrivateKey()
    eph_priv_hex = ephemeral.hex()
    wrap_ck = nip44.get_conversation_key(eph_priv_hex, recipient_pub_hex)
    wrap = Event(content=nip44.encrypt(json.dumps(seal_dict), wrap_ck),
                 pubkey=ephemeral.public_key.hex(), kind=KIND_GIFT_WRAP,
                 tags=[["p", recipient_pub_hex]],
                 created_at=_random_past_timestamp())
    wrap.sign(eph_priv_hex)
    return wrap.to_dict()


def unwrap_dm(recipient_priv_hex: str, giftwrap: dict) -> dict:
    """수신한 gift wrap(kind 1059) → {sender, content, created_at, rumor}.

    발신자 진위 검증 포함: rumor의 pubkey와 seal의 서명자가 일치해야 한다.
    """
    if giftwrap.get("kind") != KIND_GIFT_WRAP:
        raise ValueError(f"gift wrap(kind 1059)이 아님: kind={giftwrap.get('kind')}")

    # 1) gift wrap 복호 (수신자 ↔ 임시키)
    wrap_ck = nip44.get_conversation_key(recipient_priv_hex, giftwrap["pubkey"])
    seal = json.loads(nip44.decrypt(giftwrap["content"], wrap_ck))
    if seal.get("kind") != KIND_SEAL:
        raise ValueError(f"seal(kind 13)이 아님: kind={seal.get('kind')}")

    # 2) seal 복호 (수신자 ↔ 발신자)
    seal_pub = seal["pubkey"]
    seal_ck = nip44.get_conversation_key(recipient_priv_hex, seal_pub)
    rumor = json.loads(nip44.decrypt(seal["content"], seal_ck))

    # 3) 발신자 위조 방지: rumor.pubkey == seal 서명자
    if rumor.get("pubkey") != seal_pub:
        raise ValueError("발신자 위조 감지: rumor.pubkey != seal.pubkey")

    return {
        "sender": seal_pub,
        "content": rumor.get("content"),
        "created_at": rumor.get("created_at"),
        "rumor": rumor,
    }
