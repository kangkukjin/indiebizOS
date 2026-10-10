# Pages 자동 변환 인수 자료

개인정보 없는 합성 시험 문서. 2026-10-10 macOS의 Apple Pages Creator Studio 15.4에서 저장했다.

- `simple.pages`: Pages의 새 문서에 한글 제목·문장, 영문 문장, 숫자를 입력해 저장. `simple.pdf`는 같은 문서를 Pages에서 내보낸 기준 PDF.
- `complex.pages`: python-docx로 합성한 제목·한영 본문·3×3 병합 표·파란 사각형 이미지·머리말·꼬리말·각주를 Pages에서 열고, 페이지에 텍스트 상자를 추가해 Pages로 저장. `complex.pdf`는 Pages가 내보낸 기준 PDF.

내용과 기대 구조는 `backend/test_document_imports_live.py`가 검사한다. 원본 Pages와 기준 PDF는 변환 결과로 덮어쓰지 않는다. 디렉터리형 패키지 시험은 이 합성 Pages ZIP의 항목을 임시 폴더로 풀어 수행한다.

ONLYOFFICE 9.3.1.10 실측: 내용·이미지·머리말·꼬리말·각주·텍스트 상자 내용과 PDF 출력은 보존. 병합 셀은 풀리고 배경색이 생겼으며 텍스트 상자의 위치와 글꼴·줄 위치가 달라졌다. 기준/변환 PDF 모두 1쪽. 셀 병합 보존 여부는 시험 결과에 별도로 출력하며 완전 호환으로 주장하지 않는다.

실행: `INDIEBIZ_OFFICE_LIVE_TEST=1 .venv/bin/python3 -m pytest backend/test_document_imports_live.py -s` (프론트엔드 빌드와 기존 로컬 ONLYOFFICE 필요).
