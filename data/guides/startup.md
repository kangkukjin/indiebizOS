# 정부 창업·중소기업 지원사업 가이드

`[sense:startup]` 단일 액션으로 K-Startup(창업진흥원) + MSS(중소벤처기업부) 사업공고를 통합 검색한다. **query + source** 분기.

정부의 *공고된 지원사업*만 다룸. 민간 액셀러레이터/VC 정보나 사업화 컨설팅은 별도 영역.

---

## 핵심 분기: source

```
[sense:startup]{query:"예비창업패키지"}              # 기본 — 둘 다 통합
[sense:startup]{query:"R&D", source:"mss"}          # 중기부만
[sense:startup]{query:"창업", source:"kstartup"}    # K-Startup만
```

| source | 영역 | 특화 |
|---|---|---|
| `all` (기본) | K-Startup + MSS 통합 | 가장 넓은 커버리지 |
| `kstartup` | 창업진흥원 K-Startup | 창업 단계(예비·초기·도약) 특화 |
| `mss` | 중소벤처기업부 | R&D·수출·정책자금 포함 |

기본은 `all`. 어느 쪽에 있는지 모를 때 통합으로 먼저 보고, 결과가 너무 많거나 적으면 source로 좁힘.

---

## 파라미터

| 키 | 필수 | 설명 |
|---|---|---|
| `query` | ✓ | 키워드 (한국어). 사업명·분야·키워드 |
| `source` | (기본 all) | `all` \| `kstartup` \| `mss` |
| `count` | (기본 10, 최대 50) | 반환 건수 |

---

## 표준 워크플로우

### 1) 자연어 검색
```
[sense:startup]{query:"예비창업패키지"}
→ 양쪽 통합 결과
```

### 2) 분야별 (예: AI/딥테크)
```
[sense:startup]{query:"AI 인공지능 딥테크"}
[sense:startup]{query:"바이오 헬스케어"}
[sense:startup]{query:"콘텐츠 문화기술"}
```

### 3) 단계별 (예: 예비창업자)
```
[sense:startup]{query:"예비창업", source:"kstartup"}
```

### 4) R&D 자금 (중기부 특화)
```
[sense:startup]{query:"R&D", source:"mss", count:30}
```

### 5) 정기 모니터링 (새 공고 자동 알림)
```
[self:trigger]{op:"create", trigger_id:"weekly_startup_check",
  type:"schedule", config:{repeat:"weekly", weekdays:["mon"], time:"09:00"},
  pipeline:'[sense:startup]{query:"<관심분야>"} >> [limbs:notify_user]{message:"이번주 공고"}'
}
```

---

## 활용 패턴

### 단계 매핑
- **예비창업자**: K-Startup의 예비창업패키지, 청년창업사관학교 등 → `source:"kstartup"`, query에 단계 키워드
- **초기 창업 (3년 미만)**: K-Startup 초기창업패키지, TIPS R&D
- **성장 단계 (3-7년)**: K-Startup 도약패키지, 중기부 R&D 자금 → `source:"mss"` 비중 큼
- **수출**: MSS 수출바우처·해외진출 → `source:"mss"`

### 키워드 조합 팁
정부 공고는 **공식 명칭**으로 검색해야 매칭이 정확. 예:
- 좋음: `"예비창업패키지"`, `"TIPS"`, `"수출바우처"`
- 약함: `"창업 도와줘"`, `"돈 받을 수 있나"`

자연어 의도가 모호하면 IBL 호출 전에 사용자에게 분야·단계를 물어 키워드를 좁힐 것.

### 분석으로 연결
```
[sense:startup]{query:"AI", count:50}
  >> [engines:summarize]{focus:"마감 임박 + 지원 규모 큰 순"}
```

---

## 자주 하는 실수

- **source 오타**: 정확히 `all` / `kstartup` / `mss`. `k-startup`(X), `KOSME`(X).
- **count 너무 큼**: 50을 넘는 경우 API 측에서 잘림. 50 이하.
- **민간 인큐베이터 기대**: 이 액션은 정부 공고만. 액셀러레이터·VC는 별도 채널.
- **마감 정보 누락 가정**: 결과에 마감일 보통 포함되지만, 일부 공고는 별도 첨부에만 있을 수 있음. 상세는 원문 링크 클릭.
- **API 키 부재**: 패키지 config.json에 K-Startup/MSS API 키 설정 필요.

## 관련

- `data/packages/installed/tools/startup/` — 패키지
- 단계별 가이드: `business.md`, `local_info.md` (지역 창업지원)
- 정기 알림: `self:trigger` schedule 타입
