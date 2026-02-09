# Python Exec 패키지 가이드

## 사용 시점

- 수학 계산 및 통계 처리
- 데이터 처리 및 변환
- 파일 파싱 (JSON, CSV, XML 등)
- 날짜 계산 및 포맷 변환
- 차트/그래프 생성

---

## 코드 작성 규칙

- 완전한 Python 스크립트로 작성할 것
- 결과는 반드시 `print()`로 출력
- 중간 과정이 아닌 최종 결과만 출력하는 것을 권장

---

## 사용 가능 라이브러리

### 표준 라이브러리
- `json` - JSON 파싱/생성
- `datetime` - 날짜/시간 처리
- `re` - 정규표현식
- `math` - 수학 함수
- `os`, `sys`, `csv`, `collections` 등

### 설치된 외부 라이브러리
- `requests` - HTTP 요청
- `pandas` - 데이터프레임 처리
- `matplotlib` - 차트/그래프 생성
- `numpy` - 수치 계산

---

## 대용량 출력 처리

- 실행 결과가 3,000자를 초과하면 자동으로 파일에 저장됨
- 반환 형식:
  ```json
  {
    "file_path": "/path/to/output_file",
    "format": "txt",
    "preview": "처음 일부 내용...",
    "total_length": 15000
  }
  ```

---

## 다른 도구의 file_path 활용법

다른 도구가 대용량 결과를 파일로 저장한 경우, Python에서 해당 파일을 읽어 후처리할 수 있다.

```python
import json

with open("/path/to/result_file.json", "r") as f:
    data = json.load(f)

# 데이터 처리
print(len(data))
```

---

## 주의사항

- 무한 루프 작성 금지 (while True 등)
- 시스템 명령 실행이 필요하면 `run_command` 도구 사용
- 대용량 데이터는 전체를 print()하지 말고 요약만 출력
- 파일 저장 시 적절한 경로 사용
