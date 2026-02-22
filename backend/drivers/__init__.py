"""
IBL 드라이버 계층

모든 정보 소스를 동일한 인터페이스로 접근한다.
각 드라이버는 프로토콜(HTTP, SQLite, ADB 등)의 차이를 감추고
execute(action, target, params) → dict 패턴을 공유한다.
"""
