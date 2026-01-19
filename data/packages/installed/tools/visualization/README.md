# Visualization Tools

범용 데이터 시각화 도구 패키지입니다. 다양한 차트를 PNG, HTML, Base64 형식으로 생성합니다.

## 기능

| 도구 | 설명 | 용도 |
|------|------|------|
| `line_chart` | 라인 차트 | 시계열, 추이 (주가, 방문자, 온도) |
| `bar_chart` | 막대 차트 | 항목 비교 (매출, 지역별 가격) |
| `candlestick_chart` | 캔들스틱 | 주식/암호화폐 가격 |
| `pie_chart` | 파이/도넛 차트 | 구성비 (포트폴리오, 카테고리) |
| `scatter_plot` | 산점도 | 상관관계, 분포 |
| `heatmap` | 히트맵 | 밀도, 행렬, 상관계수 |
| `multi_chart` | 대시보드 | 여러 차트 조합 |

## 의존성 설치

```bash
pip install matplotlib plotly kaleido numpy
```

- `matplotlib`: 기본 차트 (필수)
- `plotly`: 인터랙티브 차트 (권장)
- `kaleido`: Plotly PNG 내보내기
- `numpy`: 수치 연산

## 출력 형식

- **png**: 이미지 파일 (기본)
- **html**: 인터랙티브 웹 페이지 (Plotly)
- **base64**: 인라인 이미지 데이터

## 사용 예시

### 라인 차트
```python
line_chart(
    data=[
        {"x": "2024-01", "y": 100},
        {"x": "2024-02", "y": 120},
        {"x": "2024-03", "y": 115}
    ],
    title="월별 매출",
    x_label="월",
    y_label="매출(억원)"
)
```

### 막대 차트
```python
bar_chart(
    data=[
        {"label": "서울", "value": 500},
        {"label": "부산", "value": 300},
        {"label": "대구", "value": 200}
    ],
    title="지역별 판매량",
    horizontal=True  # 가로 막대
)
```

### 캔들스틱 (주가)
```python
candlestick_chart(
    data=[
        {"date": "2024-01-01", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000},
        {"date": "2024-01-02", "open": 105, "high": 115, "low": 100, "close": 110, "volume": 1200}
    ],
    title="삼성전자 주가",
    show_volume=True,
    ma_periods=[5, 20]  # 이동평균선
)
```

### 파이 차트
```python
pie_chart(
    data=[
        {"label": "주식", "value": 60},
        {"label": "채권", "value": 30},
        {"label": "현금", "value": 10}
    ],
    title="포트폴리오 구성",
    donut=True  # 도넛 차트
)
```

### 산점도
```python
scatter_plot(
    data=[
        {"x": 10, "y": 20, "label": "A"},
        {"x": 15, "y": 25, "label": "B"},
        {"x": 20, "y": 35, "label": "C"}
    ],
    title="가격 vs 거래량",
    show_trendline=True
)
```

### 히트맵
```python
heatmap(
    data=[
        [1, 2, 3],
        [4, 5, 6],
        [7, 8, 9]
    ],
    x_labels=["A", "B", "C"],
    y_labels=["X", "Y", "Z"],
    color_scale="blues"
)
```

### 대시보드 (멀티 차트)
```python
multi_chart(
    charts=[
        {"type": "line", "data": [...], "title": "매출 추이"},
        {"type": "bar", "data": [...], "title": "지역별 비교"},
        {"type": "pie", "data": [...], "title": "구성비"}
    ],
    title="월간 리포트",
    layout="2x2"
)
```

## 파일 구조

```
visualization/
├── tool.json           # 도구 정의 (7개)
├── handler.py          # 진입점
├── tool_common.py      # 공통 유틸리티
├── tool_line.py        # 라인 차트
├── tool_bar.py         # 막대 차트
├── tool_candlestick.py # 캔들스틱
├── tool_pie.py         # 파이 차트
├── tool_scatter.py     # 산점도
├── tool_heatmap.py     # 히트맵
├── tool_multi.py       # 대시보드
├── requirements.txt
└── README.md
```

## 출력 경로

기본 출력 경로: `indiebizOS/outputs/charts/`

파일명 형식: `chart_YYYYMMDD_HHMMSS.png`

## 색상 팔레트

기본 색상:
- 파랑, 자주, 주황, 빨강, 짙은보라, 연두, 보라, 분홍빨강, 남색, 청회색

캔들스틱:
- 상승: 빨강
- 하락: 파랑

## 활용 패키지

- **investment**: 주가 차트, 재무제표 비교
- **real-estate**: 실거래가 추이, 지역별 비교
- **kosis**: 통계 데이터 시각화
- **health-record**: 건강 지표 추이
- **blog**: 방문자 통계

## 버전

- 1.0.0 (2025-01-19): 최초 릴리스
