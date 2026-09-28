# 68회차 절단 생산자 전수 조사

AST로 `truncated` 키를 생성하는 dict·대입·키워드 인자를 열거했다. 단순 지역 변수와 소비자는 제외했다. 모든 신규 생산 위치는 기존 정직 표지 관문 C에서 분류·사유를 요구한다. `bounded_selection`은 명시 숫자와 실효 상한이 같고 요청 수량을 채운 경우만 selection으로 표시한다.

| 파일(tools/ 기준) | 위치 수 | 분류 | 근거 |
|---|---:|---|---|
| android/android_audio.py | 2 | preview | 미리듣기 전사 표본; 전체 전사 원장은 별도 보존 |
| browser-action/browser_snapshot.py | 1 | source | 접근성 스냅샷 문자 안전 상한; 작성자 선택 아님 |
| data-ops/envelope_scope.py | 2 | propagate | 입력 원천 표지를 승계하고 명시 변환 범위만 selection으로 분리 |
| data-ops/handler.py | 1 | propagate | 입력 봉투 표지 합성; 생성 상한 없음 |
| freelance-services/tool_freelance.py | 2 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| investment/handler.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| investment/tool_fmp.py | 1 | propagate | 다운샘플 사실; handler._attach_price_table이 원 max_points와 대조 |
| investment/tool_krx.py | 1 | propagate | 다운샘플 사실; handler._attach_price_table이 원 max_points와 대조 |
| investment/tool_yfinance.py | 1 | propagate | 다운샘플 사실; handler._attach_price_table이 원 max_points와 대조 |
| location-services/tool_place.py | 1 | bounded | 명시 limit·실효 상한·충족량 대조 |
| location-services/tool_stay.py | 3 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| media_producer/render_artifact.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| notebook/handler.py | 2 | source | 문서 본문·총 읽기 예산 상한; 완전한 원문 주장 금지 |
| photo-manager/photo_db.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| real-estate/realty_molit_common.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| real-estate/tool_apt_rent.py | 1 | propagate | 월별 수집기가 명시 cap·안전캡·오류를 나눈 truncations 승계 |
| real-estate/tool_apt_trade_range.py | 1 | propagate | 월별 수집기가 명시 cap·안전캡·오류를 나눈 truncations 승계 |
| real-estate/tool_commercial_district.py | 1 | source | 호출 경계에서 max_count를 받지 않는 고정 안전캡·페이지 오류 |
| real-estate/tool_house_rent.py | 1 | propagate | 월별 수집기가 명시 cap·안전캡·오류를 나눈 truncations 승계 |
| real-estate/tool_house_trade_range.py | 1 | propagate | 월별 수집기가 명시 cap·안전캡·오류를 나눈 truncations 승계 |
| real-estate/tool_villa_rent.py | 1 | propagate | 월별 수집기가 명시 cap·안전캡·오류를 나눈 truncations 승계 |
| real-estate/tool_villa_trade_range.py | 1 | propagate | 월별 수집기가 명시 cap·안전캡·오류를 나눈 truncations 승계 |
| study/handler.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| system_essentials/body_ops.py | 10 | bounded | 명시 limit·실효 상한·충족량 대조 |
| system_essentials/doc_read_extra.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| system_essentials/docx_edit_ops.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| system_essentials/fs_grep.py | 5 | bounded | 명시 limit 선택과 시간·크기 원천 상한을 별도 truncations로 신고 |
| system_essentials/handler.py | 3 | bounded | 파일 범위 선택과 자원 상한을 truncations로 구분; 전체 목록은 false |
| system_essentials/ledger_ops.py | 1 | selection | 작성자 limit으로 고른 원장 행; total은 모집단 유지 |
| system_essentials/member_documents.py | 1 | source | 회원 문서 본문 1백만 자 안전캡; 요청 선택 아님 |
| system_essentials/office_ops.py | 2 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| system_essentials/sqlite_ops.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| web/member_web.py | 1 | bounded | bounded_selection에서 원 요청·실효 상한·반환 건수를 대조; 기본값·미충족은 source |
| web/tool_webcrawl.py | 4 | source | 공개 크롤은 전문 저장; 내부 max_length로 자른 원문은 불완전 |

합계 34개 파일, 59곳.
