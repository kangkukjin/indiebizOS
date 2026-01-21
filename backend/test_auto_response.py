"""
자동응답 시스템 테스트 스크립트
가상 메시지를 생성하고 자동응답 처리를 테스트합니다.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from business_manager import BusinessManager
from auto_response import AutoResponseService

def test_auto_response():
    """자동응답 테스트"""
    print("=" * 60)
    print("자동응답 시스템 테스트")
    print("=" * 60)

    bm = BusinessManager()

    # 테스트용 이웃 확인/생성
    neighbors = bm.get_neighbors(search="테스트")
    if neighbors:
        test_neighbor = neighbors[0]
        print(f"\n기존 테스트 이웃 사용: {test_neighbor['name']} (ID: {test_neighbor['id']})")
    else:
        test_neighbor = bm.create_neighbor(
            name="테스트 고객",
            info_level=1,
            rating=3
        )
        print(f"\n새 테스트 이웃 생성: {test_neighbor['name']} (ID: {test_neighbor['id']})")

        # 연락처 추가
        bm.add_contact(test_neighbor['id'], 'email', 'test@example.com')

    # 가상 메시지 생성 - 비즈니스 문의
    test_message = bm.create_message(
        content="안녕하세요, 혹시 노트북 수리 서비스 제공하시나요? 맥북 프로 화면이 깨졌는데 수리 가능한지 문의드립니다.",
        contact_type="email",
        contact_value="test@example.com",
        subject="노트북 수리 문의",
        neighbor_id=test_neighbor['id'],
        is_from_user=0,  # 외부에서 받은 메시지
        status="received"
    )

    print(f"\n테스트 메시지 생성 완료:")
    print(f"  - ID: {test_message['id']}")
    print(f"  - 제목: {test_message['subject']}")
    print(f"  - 내용: {test_message['content'][:50]}...")

    # 자동응답 서비스로 처리
    print("\n" + "-" * 60)
    print("자동응답 처리 시작...")
    print("-" * 60)

    def log_callback(msg):
        print(f"  {msg}")

    service = AutoResponseService(log_callback=log_callback)

    # 메시지 직접 처리 (서비스 시작 없이)
    service._process_message(test_message)

    print("\n" + "-" * 60)
    print("테스트 완료")
    print("-" * 60)

    # 결과 확인 - 발송된 메시지가 있는지
    recent_messages = bm.get_messages(neighbor_id=test_neighbor['id'], limit=5)

    print("\n최근 메시지 목록:")
    for msg in recent_messages:
        direction = "→ 발신" if msg.get('is_from_user') else "← 수신"
        status = msg.get('status', 'unknown')
        print(f"  {direction} [{status}] {msg.get('subject', '제목없음')[:30]}")
        if msg.get('is_from_user'):
            print(f"    내용: {msg.get('content', '')[:100]}...")

    return True


def test_spam_message():
    """스팸 메시지 테스트 - no_response_needed 호출 확인"""
    print("\n" + "=" * 60)
    print("스팸 메시지 테스트 (no_response_needed)")
    print("=" * 60)

    bm = BusinessManager()

    # 테스트용 이웃 확인
    neighbors = bm.get_neighbors(search="테스트")
    if not neighbors:
        print("테스트 이웃이 없습니다. 먼저 test_auto_response를 실행하세요.")
        return False

    test_neighbor = neighbors[0]

    # 스팸 메시지 생성
    spam_message = bm.create_message(
        content="축하합니다! 당첨되셨습니다! 지금 바로 클릭하세요! 긴급 할인 50% 무료 체험!",
        contact_type="email",
        contact_value="spam@example.com",
        subject="[긴급] 당첨 안내",
        neighbor_id=test_neighbor['id'],
        is_from_user=0,
        status="received"
    )

    print(f"\n스팸 메시지 생성: {spam_message['subject']}")

    def log_callback(msg):
        print(f"  {msg}")

    service = AutoResponseService(log_callback=log_callback)
    service._process_message(spam_message)

    print("\n스팸 테스트 완료")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="자동응답 테스트")
    parser.add_argument("--spam", action="store_true", help="스팸 메시지 테스트")
    parser.add_argument("--all", action="store_true", help="모든 테스트 실행")

    args = parser.parse_args()

    if args.spam:
        test_spam_message()
    elif args.all:
        test_auto_response()
        test_spam_message()
    else:
        test_auto_response()
