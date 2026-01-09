"""
channels/__init__.py - 채널 자동 로딩 및 팩토리
"""

import importlib
import os
from .base import Channel

# 채널 레지스트리 (자동 발견)
CHANNELS = {}


def _discover_channels():
    """channels/ 디렉토리의 모든 채널 자동 로드"""
    current_dir = os.path.dirname(__file__)
    
    for filename in os.listdir(current_dir):
        if filename.endswith('.py') and filename not in ['__init__.py', 'base.py']:
            module_name = filename[:-3]  # .py 제거
            
            try:
                # 동적 임포트
                module = importlib.import_module(f'.{module_name}', package='channels')
                
                # 채널 클래스 찾기 (Channel 상속받은 것)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, Channel) and 
                        attr != Channel):
                        
                        # 채널 이름 = 모듈명 (gmail.py → 'gmail')
                        CHANNELS[module_name] = attr
                        print(f"✓ 채널 로드: {module_name} ({attr.__name__})")
                        
            except Exception as e:
                print(f"✗ 채널 로드 실패 ({module_name}): {e}")


def get_channel(channel_type: str, config: dict) -> Channel:
    """
    채널 인스턴스 생성
    Args:
        channel_type: 채널 타입 ('gmail', 'nostr' 등)
        config: 채널 설정 dict
    Returns:
        Channel: 채널 인스턴스
    Raises:
        ValueError: 지원하지 않는 채널 타입
    """
    if channel_type not in CHANNELS:
        available = ', '.join(CHANNELS.keys()) if CHANNELS else '없음'
        raise ValueError(f"지원하지 않는 채널: {channel_type} (사용 가능: {available})")
    
    ChannelClass = CHANNELS[channel_type]
    return ChannelClass(config)


def list_available_channels() -> list:
    """
    사용 가능한 채널 목록 반환
    Returns:
        list: 채널 타입 리스트
    """
    return list(CHANNELS.keys())


# 프로그램 시작 시 자동 실행
_discover_channels()
