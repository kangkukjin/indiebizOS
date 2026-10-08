# 내부 소스 열람 전 관측

12:05 KST. collect_v0 최초 성공, duck_export.text 3633자에 SQL 메뉴 전체와 검색·푸터·목차가 섞인다. declared_content main 선택인데 본문 외 문구가 포함되어 추출 모델 입력에 전달된다. duck_concurrency도 3521자에 같은 메뉴. PostgreSQL/SQLite는 body fallback. 호출/입력 원본과 source_ref를 보존함. 정확한 원인과 손실 여부는 아직 미확정; 이후 소스 열람은 진단에 한함.
