# 웹 수집 구분과 본문 문맥 선택

## 문제와 범위

에피소드 3777은 날짜·링크를 얻기 위해 브라우저 DOM 평가를 다섯 번 호출했다.
3793~3795는 호텔 본문에서 시설·체크인 관련 문장을 반복 선별했고,
3801은 본문 선별 과정에서 조건식·병렬 통화 결합을 다시 작성하며 오류를 겪었다.
보존 로그의 이 사례들은 페이지 구조 관측과 출처별 문맥 선택을 공통 동작으로 제공할 근거다.
932개 보존 로그 중 실제 호출이 있는 조사 후보 256개를 검토했으나 잘린 로그가 있으므로
전체 작업의 비율이나 이번 변경의 시간 절감률로 해석하지 않는다.

사용자 지시 “그럼 구현해 봐”에 따라 기존 `sense:crawl`과 `table:filter`를 확장하고
`fn` 선정집에 한 이름을 추가했다. 검색 소스 통합·사이트 전체 탐색·변화 감시까지
확장하지 않는다. 기존 파서 문법과 노드·액션 수는 그대로다.

## 제공하는 계약

### `sense:crawl{op}`

| op | 반환 items | 쓰임 |
|---|---|---|
| content (생략 시 기본) | text·type·url·paragraph_index | 본문 읽기·문맥 발췌 |
| links | text·url·href·source_url·title·rel·link_index | 실제 링크 목적지 수집 |
| metadata | field·value·raw·source·source_url·url·title | 제목·대표주소·저자·날짜 근거 확인 |

- HTTP(S) 링크를 HTML base/최종 URL 기준으로 해소한다. 중복 링크는 유지한다.
- 메타 태그·canonical·time·JSON-LD를 본문 파싱과 별도로 관측한다.
  날짜 충돌을 덮어쓰지 않고 JSON-LD 경로·엔터티 타입/ID를 함께 남긴다.
  일반 time은 `date`, 게시/수정 의미가 명시된 것만 `published_at`/`modified_at`이다.
  ISO 파싱 가능 값만 normalized에 넣으며 시간대나 불명 날짜를 추정하지 않는다.
- 정상 링크 0건과 수집 실패를 구분한다. HTML 구조가 없는 PDF는 구조 모드 실패다.
  Playwright는 프레임마다 출처를 보존하고 누락을 `structure_errors`로 신고한다.
  Chrome 경로는 메인 DOM만 관측하므로 iframe 존재 시 부분 수집을 신고한다.
- 한 수집에서 전문과 구조 관측을 불변 source_ref에 보관한다. 캐시 v3는
  프로젝트·에이전트·URL로 분리하고 모드 간 재사용한다. refresh는 새 스냅샷이다.
  짧은 구조 전용 응답으로 본문 수집 성공을 대신하지 않는다.
- max_length는 표시 예산이다. 전문은 자르지 않는다. 문단 위치는 추출 결과의
  1부터 시작하는 행 번호이며 HTML 소스 줄번호가 아니다. 제목 행도 포함된다.
  source_ref는 원본 HTML/이미지 아카이브가 아니다.

### `table:filter{context}`와 `[fn:본문에서찾기]`

`context:{before,after,by,limit}`을 명시한 필터만 새 경로를 탄다. 일반 filter는 그대로다.
앞뒤 개수는 비음수 정수, by는 그룹 키 이름/목록, limit은 문맥을 붙일 일치 수다.

- 같은 그룹의 연속 이웃만 선택한다. 그룹 키 결측·null·실패 행에서 멈춘다.
- 겹친 문맥은 한 번만, 입력 순서와 각 행의 원래 필드를 보존한다.
- `_error` 행은 항상 반환하고 매치로 세지 않는다. limit=0에도 실패는 보인다.
- match_info는 total_matches/selected_matches/omitted_matches,
  match_indices/selected_indices/input_indices(입력 기준 1부터), failure_count를 담는다.
  문맥이 이웃의 미선택 일치 행까지 포함할 수 있으므로 selected_matches는
  출력의 모든 매치 수가 아니라 문맥 중심으로 선택한 수다.
- 상류 오류·절단 진단은 유지하고 선택 제한은 selection 범위로 신고한다.
- 이미 걸러진 문단 목록에서 사라진 이웃은 복원하지 않는다.

```ibl
$원문 = [sense:crawl]{url:"https://example.com"}
$원문 >> [fn:본문에서찾기]{패턴:"Example|domain",문맥:1,개수:5}
```

관용구는 정규식 text 필터와 URL별 문맥 인자를 특화한다. 추가 모델 호출은 없다.
실행 결과를 `$return`에 직접 연결해 일치 계수 봉투를 잃지 않는다.
단문 관용구도 수동 선정집의 always_on과 본문이 정확히 일치할 때 지도에 노출한다.
자동으로 쌓인 단문 별칭은 종전처럼 제외한다.

## 구현·경로 감사

- web/webcrawl_structure.py: 순수 HTML 구조 추출과 모드 투영.
- web/tool_webcrawl.py·webcrawl_store.py·handler.py: 단계 전달·공유 스냅샷·명시 op 분기.
- data-ops/dataops_filter_context.py: 공통 값 비교를 사용한 비파괴 문맥 선택.
- ibl_access.py·curated.json: 선정한 관용구를 모델 지도에 노출.
- 파생 파일은 build_ibl_nodes.py로 생성한다. 회원 실행 경로는 기존 member_web과
  프로젝트/에이전트 캐시·spill 범위를 그대로 사용하며 새 파일 경로 인자는 없다.
  구조 추출은 파일·모델에 접근하지 않는다. web 구현 지문은 이 감사 후 갱신했다.

## 검증·등록

- 기존 원문 보관·표시 예산·실패 단계 및 관용구 회귀와 새 구조/문맥 테스트를 실행한다.
- 충돌 날짜, 상대 URL, 정상 0건/실패, PDF, 모드 캐시·refresh·프로젝트 격리,
  프레임 출처·부분 실패, 문맥 겹침/경계/실패/계수, 실제 fn 파서 실행을 검증한다.
- `scripts/seed_web_collection_2026_09_15.py`는 기본 검증만 수행한다. `--apply`로
  새 이름만 등록하고 10개 수집 용례와 3개 관용구 호출 용례를 해마·학습 JSON에 심는다.
  등록은 기존 add_examples_batch·실행 중인 임베더를 사용하며 DB/학습 파일을 백업한다.
  입력 교재는 `data/idioms/web_collection_seeds.json`에 있다.

### 실제 실행 확인

로컬 `/ibl/execute`에서 example.com의 content·links·metadata와 등록된 fn 호출이
모두 성공했다. fn은 전체 일치 3건과 문맥 포함 4행을 반환했다. 짧은 본문 경고는 유지됐다.
IANA의 example 안내 페이지는 본문 8행·링크 31행·메타 관측 2행이었고,
세 모드의 source_ref가 같으며 후속 두 호출이 캐시를 재사용했다.
`ibl_shape_sweep --only sense:crawl`의 기본/세 op 관측 4건도 모두 성공했다.
관용구 지도에서 이름 노출을 확인했으며 인자·동반 스윕과 Android 몸 번들을 갱신했다.
백엔드는 drain 재시작으로 반영했고 중단된 사용자 실행은 없었다.

### 최종 검사 결과

- 수집·원문 보관·실패 단계·관용구 회귀 67건 통과.
- 전체 backend 검사: 4,774건 통과, 3건 실패. 새 관용구 기대 목록과
  새 테스트의 단일 러너 위임 두 건을 수정한 뒤 관련 49건을 재실행해 모두 통과.
- 남은 `test_doc_drift.py::test_t6_real_repo_clean` 실패는 작업 시작부터 있던
  별도 변경의 `data/scripts/registry.yaml`이 미추적 `압축.py·이미지변환.py`를
  가리키기 때문이다. 이번 커밋에 해당 파일들을 포함하거나 수정하지 않았다.
- 어휘 삼각 검증·파생물 신선도·backend 층 검사·Android 번들 생성 통과.
